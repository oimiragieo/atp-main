"""POC: Budget preflight guard integration helper.

Encapsulates budget preflight behavior with counters and tracing.
"""

from __future__ import annotations

from metrics.registry import REGISTRY

from .budget import BudgetGovernor, Usage
from .tracing import get_tracer

_DENY_TOKENS = REGISTRY.counter("window_denied_tokens_total")
_DENY_USD = REGISTRY.counter("window_denied_usd_total")


def preflight_check(session: str, usage: Usage, governor: BudgetGovernor) -> bool:
    ok = governor.preflight(session, usage)
    if ok:
        return True
    rem = governor.remaining(session)
    reason = "tokens" if usage.tokens > rem.tokens else "usd"
    if reason == "tokens":
        _DENY_TOKENS.inc(1)
    else:
        _DENY_USD.inc(1)
    tracer = get_tracer()
    span_cm = tracer.start_as_current_span("budget.denied") if tracer else None
    if span_cm:
        span_cm.__enter__()
        try:
            import opentelemetry.trace as ottrace

            span = ottrace.get_current_span()
            span.set_attribute("budget.session", session)
            span.set_attribute("budget.reason", reason)
            span.set_attribute("budget.req_tokens", usage.tokens)
            span.set_attribute("budget.req_usd", usage.usd_micros)
            span.set_attribute("budget.rem_tokens", rem.tokens)
            span.set_attribute("budget.rem_usd", rem.usd_micros)
        except Exception:  # noqa: S110
            pass
        span_cm.__exit__(None, None, None)
    return False
