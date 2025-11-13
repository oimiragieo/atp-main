# Champion/Challenger (POC)

This POC selects a challenger model alongside a primary (champion) based on
predicted quality and cost, and tracks outcomes for a basic win rate.

- Engine: `router_service/champion_challenger.py`
- Tests: `tests/test_champion_challenger_poc.py`
- Metrics:
  - `challenger_runs_total`: number of challenger trials
  - `challenger_wins_total`: number of times challenger beats the champion

Selection heuristic
- Require ≥ 2% predicted quality gain over the primary.
- Require cost ≤ 1.5× the primary cost.
- Among acceptable candidates, prefer lowest cost; break ties by highest gain.

Example
```
from router_service.champion_challenger import Candidate, select_challenger
ch = select_challenger(
    Candidate('primary', 2.0, 0.80),
    [Candidate('a', 2.5, 0.83), Candidate('b', 2.9, 0.90)]
)
if ch:
    # run challenger in parallel and compare outcomes
    ...
```

Notes
- Integration is opt-in and currently exposes the selected challenger in the
  plan roles (when enabled) without executing it.
- Future: run challenger in shadow or parallel path and call `record_outcome()`
  with measured quality.
