"""POC: QoS-aware fair scheduler (GAP-020).

Simplified scheduler to demonstrate QoS priority ordering and basic metrics.
This does not replace the main FairScheduler; it's a focused POC to validate
semantics and observability before integration.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from metrics.registry import REGISTRY

from .tracing import get_tracer

QOS_ORDER = {"gold": 3, "silver": 2, "bronze": 1}


@dataclass
class _QEntry:
    session: str
    qos: str
    weight: float = 1.0
    enqueued_at: float = field(default_factory=time.time)


class QoSFairScheduler:
    def __init__(self) -> None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self._lock = asyncio.Lock()
        self._queue: list[_QEntry] = []
        self._active: dict[str, int] = {}
        # metrics (separate gauges per qos)
        self._g_depth_gold = REGISTRY.gauge("fair_q_depth_gold")
        self._g_depth_silver = REGISTRY.gauge("fair_q_depth_silver")
        self._g_depth_bronze = REGISTRY.gauge("fair_q_depth_bronze")

    def _refresh_depths(self) -> None:
        counts = {"gold": 0, "silver": 0, "bronze": 0}
        for e in self._queue:
            if e.qos in counts:
                counts[e.qos] += 1
        self._g_depth_gold.set(counts["gold"])  # best-effort
        self._g_depth_silver.set(counts["silver"])  # best-effort
        self._g_depth_bronze.set(counts["bronze"])  # best-effort

    async def fast_acquire(self, session: str, qos: str = "silver") -> bool:
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("fair.acquire") if tracer else None
        if span_cm:
            span_cm.__enter__()
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("fair.qos", qos)
                span.set_attribute("fair.fast_path", True)
            except Exception:  # noqa: S110
                pass
            span_cm.__exit__(None, None, None)
        self._active[session] = self._active.get(session, 0) + 1
        return True

    async def release(self, session: str) -> None:
        async with self._lock:
            cur = self._active.get(session, 0)
            if cur > 1:
                self._active[session] = cur - 1
            else:
                self._active.pop(session, None)

    async def offer(self, session: str, qos: str = "silver", weight: float = 1.0) -> None:
        async with self._lock:
            self._queue.append(_QEntry(session=session, qos=qos, weight=max(0.1, weight)))
            self._refresh_depths()

    async def pick_next(self) -> str | None:
        async with self._lock:
            if not self._queue:
                return None
            best_idx = -1
            best_q = -1
            best_age = 0.0
            now = time.time()
            for i, e in enumerate(self._queue):
                q = QOS_ORDER.get(e.qos, 0)
                age = now - e.enqueued_at
                if q > best_q or (q == best_q and age > best_age):
                    best_q = q
                    best_age = age
                    best_idx = i
            if best_idx == -1:
                return None
            e = self._queue.pop(best_idx)
            self._refresh_depths()
            self._active[e.session] = self._active.get(e.session, 0) + 1
            return e.session
