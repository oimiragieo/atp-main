"""Retransmission queue & de-dup cache (GAP-003A).

Maintains a set of requested fragment indices per (session, stream, msg_seq)
and enforces a minimum re-request interval (ttl_s) to avoid bursts.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from metrics.registry import REGISTRY

from .tracing import get_tracer

logger = logging.getLogger(__name__)

Key = tuple[str, str, int]


@dataclass
class _ReqState:
    requested: dict[int, float] = field(default_factory=dict)  # frag_seq -> last_ts


class RetransmitQueue:
    def __init__(self, ttl_s: float = 0.5) -> None:
        self._ttl = float(ttl_s)
        self._m: dict[Key, _ReqState] = {}
        self._ctr = REGISTRY.counter("retransmit_frames_total")

    def request(self, session_id: str, stream_id: str, msg_seq: int, missing: list[int]) -> list[int]:
        """Return fragment indices to request now, de-duplicating within ttl window."""
        key: Key = (session_id, stream_id, msg_seq)
        st = self._m.setdefault(key, _ReqState())
        now = time.time()
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("retransmit.request") if tracer else None
        if span_cm:
            span = span_cm.__enter__()
            try:
                span.set_attribute("retrans.session", session_id)
                span.set_attribute("retrans.stream", stream_id)
                span.set_attribute("retrans.msg_seq", msg_seq)
                span.set_attribute("retrans.missing_count", len(missing))
            except Exception as e:
                logger.warning(f"Failed to set retransmit span attributes: {e}")
        out: list[int] = []
        for idx in sorted(missing):
            last = st.requested.get(idx, 0.0)
            if now - last >= self._ttl:
                out.append(idx)
                st.requested[idx] = now
        if out:
            self._ctr.inc(len(out))
        # cleanup stale entries to bound memory
        stale = [i for i, ts in st.requested.items() if now - ts > 60.0]
        for i in stale:
            st.requested.pop(i, None)
        if span_cm:
            try:
                span.set_attribute("retrans.sent_count", len(out))
            except Exception as e:
                logger.warning(f"Failed to set retransmit sent count attribute: {e}")
            span_cm.__exit__(None, None, None)
        return out

    def clear(self, session_id: str, stream_id: str, msg_seq: int) -> None:
        self._m.pop((session_id, stream_id, msg_seq), None)
