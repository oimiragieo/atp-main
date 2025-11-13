"""WINDOW_UPDATE control frame emitter (GAP-006 POC).

Emits a logical window update event when either:
- The absolute delta between previous and current window exceeds `min_delta`, or
- `min_interval_s` has elapsed since the last emission (cadence tick).

This POC focuses on emission policy and observability hooks; wiring frames on the
transport is deferred.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from metrics.registry import REGISTRY

from .tracing import get_tracer


@dataclass
class WindowUpdateEvent:
    session: str
    before: int
    after: int
    at: float


class WindowUpdateEmitter:
    def __init__(self, min_delta: int = 1, min_interval_s: float = 0.5) -> None:
        self.min_delta = max(1, int(min_delta))
        self.min_interval_s = float(min_interval_s)
        self._last_value: dict[str, int] = {}
        self._last_emit: dict[str, float] = {}
        self._ctr_tx = REGISTRY.counter("window_update_tx")

    def maybe_emit(self, session: str, current: int, now: float | None = None) -> list[WindowUpdateEvent]:
        now_f = float(now or time.time())
        if session not in self._last_value:
            # Initialize baseline without emitting
            self._last_value[session] = current
            self._last_emit[session] = now_f
            return []
        before = self._last_value.get(session, current)
        last_t = self._last_emit.get(session, now_f)

        delta = abs(current - before)
        due_by_delta = delta >= self.min_delta
        due_by_cadence = (now_f - last_t) >= self.min_interval_s

        if not (due_by_delta or due_by_cadence):
            self._last_value[session] = current
            return []

        # Emit one update
        ev = WindowUpdateEvent(session=session, before=before, after=current, at=now_f)
        self._last_value[session] = current
        self._last_emit[session] = now_f
        self._ctr_tx.inc(1)

        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("window.update") if tracer else None
        if span_cm:
            span_cm.__enter__()
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("window.before", before)
                span.set_attribute("window.after", current)
                span.set_attribute("window.delta", current - before)
            except Exception as _err:  # noqa: S110
                _ = _err
            span_cm.__exit__(None, None, None)
        return [ev]
