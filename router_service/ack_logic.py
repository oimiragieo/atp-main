"""POC: ACK/NACK emission logic for sequencing (GAP-003).

Tracks fragment receipt per (session, stream, msg_seq) and computes:
- ack_up_to: highest contiguous fragment index seen starting at 0.
- nacks: missing fragment indices below `expected_last` once `is_last` observed.
- completed: True when all fragments [0..expected_last] have been received.

This module is not yet wired into the service; it exists to validate logic and
support incremental integration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from metrics.registry import REGISTRY

Key = tuple[str, str, int]  # (session_id, stream_id, msg_seq)


@dataclass
class _SeqState:
    received: set[int] = field(default_factory=set)
    expected_last: int | None = None
    ack_up_to: int = -1


class AckTracker:
    def __init__(self) -> None:
        self._m: dict[Key, _SeqState] = {}
        self._ack_counter = REGISTRY.counter("acks_tx")
        self._retransmit_counter = REGISTRY.counter("retransmit_requests")

    def note(
        self, session_id: str, stream_id: str, msg_seq: int, frag_seq: int, is_last: bool
    ) -> tuple[int, list[int], bool]:
        """Record a fragment and return (ack_up_to, nacks, completed).

        - ack_up_to: highest contiguous index from 0.
        - nacks: missing indices < expected_last (only after last seen).
        - completed: True when all [0..expected_last] received.
        """
        t_start = time.time()
        key: Key = (session_id, stream_id, msg_seq)
        st = self._m.setdefault(key, _SeqState())
        st.received.add(frag_seq)
        if is_last:
            st.expected_last = max(st.expected_last or 0, frag_seq)
        # advance ack_up_to contiguous
        while (st.ack_up_to + 1) in st.received:
            st.ack_up_to += 1
            # Each advance represents an ACK emission opportunity
            self._ack_counter.inc(1)
        nacks: list[int] = []
        if st.expected_last is not None:
            # Emit nacks for any missing below expected_last
            for i in range(0, st.expected_last + 1):
                if i not in st.received:
                    nacks.append(i)
            if nacks:
                self._retransmit_counter.inc(len(nacks))
        completed = st.expected_last is not None and all(i in st.received for i in range(0, st.expected_last + 1))
        if completed:
            del self._m[key]
        # tracing span (POC)
        try:
            from .tracing import get_tracer

            tracer = get_tracer()
            span_cm = tracer.start_as_current_span("ack.update") if tracer else None
        except Exception:
            span_cm = None
        if span_cm:
            span_cm.__enter__()
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("ack.session", session_id)
                span.set_attribute("ack.stream", stream_id)
                span.set_attribute("ack.msg_seq", msg_seq)
                span.set_attribute("ack.frag_seq", frag_seq)
                span.set_attribute("ack.ack_up_to", st.ack_up_to)
                span.set_attribute("ack.nacks_count", len(nacks))
                span.set_attribute("ack.completed", completed)
                span.set_attribute("ack.proc_ms", int((time.time() - t_start) * 1000))
            except Exception as _err:  # noqa: S110
                _ = _err
            span_cm.__exit__(None, None, None)
        return st.ack_up_to, nacks, completed
