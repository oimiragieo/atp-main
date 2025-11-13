"""POC: HEARTBEAT + idle timeout scheduler (GAP-004).

Generates periodic heartbeat events per session/stream and signals FIN on idle.
This is a self-contained helper to validate cadence logic before wiring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from metrics.registry import REGISTRY

from .tracing import get_tracer


@dataclass
class HeartbeatEvent:
    kind: str  # "HB" or "FIN"
    at: float


class HeartbeatScheduler:
    def __init__(self, interval_s: float = 5.0, idle_fin_s: float = 30.0) -> None:
        self.interval_s = float(interval_s)
        self.idle_fin_s = float(idle_fin_s)
        now = time.time()
        self._last_activity = now
        self._last_hb = now
        self._hb_counter = REGISTRY.counter("heartbeats_tx")

    def note_activity(self, at: float | None = None) -> None:
        self._last_activity = float(at or time.time())

    def tick(self, now: float | None = None) -> list[HeartbeatEvent]:
        now_f = float(now or time.time())
        out: list[HeartbeatEvent] = []
        # FIN on idle
        if now_f - self._last_activity >= self.idle_fin_s:
            # tracing span for FIN
            tracer = get_tracer()
            span_cm = tracer.start_as_current_span("heartbeat.fin") if tracer else None
            if span_cm:
                span = span_cm.__enter__()
                try:
                    span.set_attribute("idle_duration_s", float(now_f - self._last_activity))
                    span.set_attribute("idle_fin_s", self.idle_fin_s)
                except Exception:  # noqa: S110 - best-effort
                    pass
            out.append(HeartbeatEvent(kind="FIN", at=now_f))
            if span_cm:
                span_cm.__exit__(None, None, None)
            return out
        # HB cadence
        if now_f - self._last_hb >= self.interval_s:
            # tracing span for HB
            tracer = get_tracer()
            span_cm = tracer.start_as_current_span("heartbeat.tx") if tracer else None
            if span_cm:
                span = span_cm.__enter__()
                try:
                    span.set_attribute("since_last_activity_s", float(now_f - self._last_activity))
                    span.set_attribute("interval_s", self.interval_s)
                    span.set_attribute("idle_fin_s", self.idle_fin_s)
                except Exception:  # noqa: S110 - best-effort
                    pass
            out.append(HeartbeatEvent(kind="HB", at=now_f))
            self._last_hb = now_f
            self._hb_counter.inc(1)
            if span_cm:
                span_cm.__exit__(None, None, None)
        return out
