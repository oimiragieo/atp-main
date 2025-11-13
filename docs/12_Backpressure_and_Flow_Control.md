# 12 — Backpressure & Flow Control

- Triplet windows: max_parallel, max_tokens, max_usd_micros per stream.
- Router backpressure signals and Bronze shedding to protect latency.
- Agent CTRL/STATUS: READY/BUSY/PAUSE/DRAINING with suggested_window.
- AIMD for window tuning; queue watermarks and ECN-style advisories.
 
## Watermark Backpressure (POC)

- Module: `router_service/backpressure_watermark.py`
- Config: `high_ms`, `low_ms`, `require_n` consecutive highs to trigger.
- Metric: `queue_high_watermark_events_total` increments on entering high-watermark state.

## ECN Advisory Flags (POC)

- Module: `router_service/ecn.py`
- Adds `ECN` to frame flags and increments `ecn_mark_total`.
- Intended to be set when watermark backpressure triggers.
- Reaction: `AIMDController.ecn_reaction(session)` applies multiplicative decrease on ECN.

## WINDOW_UPDATE Emission (POC)

The router emits WINDOW_UPDATE events to notify peers of effective window changes.

- Cadence: emit if `min_interval_s` has elapsed since last emission for the same session.
- Delta: emit immediately when `abs(current - previous) >= min_delta`.
- Metrics: increments `window_update_tx` counter for each emission.
- Tracing: span `window.update` with attributes `window.before`, `window.after`, and `window.delta`.

Reference implementation (POC):

- Emitter: `router_service/window_update_emitter.py`
- Tests: `tests/test_window_update_emitter_poc.py`

Recommended initial values:

- `min_delta = 2` for integer concurrency windows.
- `min_interval_s = 0.5` to dampen bursts while remaining responsive.

## Budget Semantics (POC)

The router performs preflight checks against per-session budgets before admitting
work. Budgets cover both tokens and USD micros to support dual-mode fairness.

- Interface: see `router_service/budget.py`.
- Governor: `BudgetGovernor` maintains per-session `Budget` with limits and usage.
- Preflight: `BudgetGovernor.preflight(session, usage)` returns True if the request
  fits within remaining tokens and USD; otherwise False.
- Consumption: `BudgetGovernor.consume(session, usage)` updates usage after serving.
- Metrics: gauges `budget_remaining_tokens` and `budget_remaining_usd_micros` (POC reflects
  the last evaluated session for simplicity; label fan-out can be added later).
- Tracing: span `budget.check` with attributes for remaining/requested amounts and decision.

Example (POC)
```
from router_service.budget import BudgetGovernor, Usage
gov = BudgetGovernor(default_tokens=1000, default_usd_micros=1_000_000)
usage = Usage(tokens=200, usd_micros=120_000)
if gov.preflight('sess-1', usage):
    # admit work
    gov.consume('sess-1', usage)
else:
    # reject / shed or ask client to downsize
  pass
```

## QoS Tiers (POC)

QoS tiers influence scheduling priority when resources are contended.

- Tiers: `gold` > `silver` > `bronze`.
- Behavior (POC): higher tier requests are dequeued before lower tiers, with
  FIFO within the same tier. This preserves fairness while enabling priority
  service.
- Metrics: queue depths per tier (`fair_q_depth_gold`, `fair_q_depth_silver`,
  `fair_q_depth_bronze`).
- Tracing: `fair.acquire` span includes attribute `fair.qos` on fast path.

Reference implementation (POC):

- `router_service/qos_scheduler.py`
- `tests/test_qos_priority_poc.py`

## Preemption (POC)

When higher QoS demand spikes, the router can select lower-tier sessions for
preemption to reclaim capacity. The POC provides a selection helper that prefers
bronze sessions and, if necessary, silver sessions, choosing the oldest first.

- Engine: `router_service/preemption.py`
- Metrics: `preemptions_total`
- Tracing: `preempt.select` with `preempt.count` and reason (`qos_spike`).
- Test: `tests/test_preemption_poc.py`

## Concurrency Enforcement (POC)

Concurrency limits are enforced via the fair scheduler and AIMD window. When
`window_allowed` is reached for a session and no timeout is provided, further
acquires are denied immediately, preserving latency and fairness.

- Test: `tests/test_concurrency_enforcement_poc.py`
- Budget guard denials are tracked via `window_denied_tokens_total` and
  `window_denied_usd_total` counters.

## Budget Preflight Guard (POC)

The budget preflight guard integrates budget checks into the request admission
path, providing opt-in enforcement via `ENABLE_BUDGET_PREFLIGHT` environment
variable.

- Module: `router_service/budget_guard.py`
- Function: `preflight_check(session, usage, governor)` performs preflight and
  returns True if the request fits within remaining budget, False otherwise.
- Metrics: Increments `window_denied_tokens_total` or `window_denied_usd_total`
  counters based on the denial reason (tokens vs USD limit exceeded).
- Tracing: Creates `budget.denied` spans with attributes for session, reason,
  requested amounts, and remaining budget.
- Integration: Called in the ask path before admitting work; denials prevent
  resource allocation and tool execution.
- Behavior: When budget is exceeded, the request is rejected with tracing and
  metrics for observability, enabling cost control and fair resource sharing.
