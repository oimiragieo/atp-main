Budget Burn-rate (POC)

Summary
- Tracks recent USD consumption per session and computes a rolling burn-rate (USD/min) over a time window.
- Updates gauge `budget_burn_rate_usd_per_min` (last session evaluated) for quick visibility.

Implementation
- router_service/budget.py:
  - BudgetGovernor maintains per-session deque of (timestamp, usd_micros) on consume().
  - burn_rate_usd_per_min(session, window_s) returns USD/min over last window_s seconds.
  - consume() prunes stale events and updates a gauge with a 5-minute window snapshot.

Tests
- tests/test_budget_burn_rate_poc.py validates expected USD/min computations over a 60s window and that burn drops to zero with a zero-length window.

Future
- Per-tenant burn-rate alerts and forecast projection.
- Window configuration via environment and central metrics catalog.
