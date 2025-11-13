"""POC: Bronze preemption & EPREEMPT (GAP-021).

Selects bronze sessions to preempt when higher QoS demand spikes.
This is a decision helper; integration with transport is deferred.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from metrics.registry import REGISTRY

from .tracing import get_tracer

_CTR_PREEMPT = REGISTRY.counter("preemptions_total")


@dataclass
class Active:
    session: str
    qos: str  # gold|silver|bronze
    started_ms: float


def pick_preemptions(active: Sequence[Active], needed: int, prefer_oldest: bool = True) -> list[str]:
    """Return up to `needed` bronze (then silver) sessions to preempt.

    Preference: bronze first; within tier, oldest running first (if prefer_oldest).
    Emits a tracing span for observability and increments preemption counter.
    """
    # candidates: bronze then silver if insufficient
    bronze = [a for a in active if a.qos == "bronze"]
    silver = [a for a in active if a.qos == "silver"]
    key = (lambda a: a.started_ms) if prefer_oldest else (lambda a: -a.started_ms)
    bronze.sort(key=key)
    silver.sort(key=key)
    chosen = [a.session for a in bronze[:needed]]
    if len(chosen) < needed:
        remain = needed - len(chosen)
        chosen.extend(a.session for a in silver[:remain])
    if chosen:
        _CTR_PREEMPT.inc(len(chosen))
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("preempt.select") if tracer else None
        if span_cm:
            span_cm.__enter__()
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("preempt.count", len(chosen))
                span.set_attribute("preempt.reason", "qos_spike")
            except Exception:  # noqa: S110
                pass
            span_cm.__exit__(None, None, None)
    return chosen
