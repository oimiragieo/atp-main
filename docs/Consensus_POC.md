# Consensus Scoring (POC)

Computes an agreement score across multiple responses and records a histogram
metric for observability. Metrics are exported via `metrics.registry.REGISTRY.export()` for integration with the /metrics endpoint.

- Engine: `router_service/consensus.py`
- Tests: `tests/test_consensus_poc.py`
- Metrics: `agreement_pct` histogram (buckets: 0.2, 0.4, 0.6, 0.8, 0.9)

Scoring
- Jaccard similarity across token sets of each response (case-insensitive).
- `meets_threshold(texts, threshold)` helper returns a boolean.

Example
```
from router_service.consensus import jaccard_agreement, meets_threshold
score = jaccard_agreement(["the quick", "the quick brown"])  # ~0.67
ok = meets_threshold(["x y", "x z"], threshold=0.4)  # True
```

Future
-- Add ROUGE-L/ROUGE-1 as alternative scorer.
-- Weight by confidence and model reliability.

Multi-Strategy Consensus (POC)
- Strategies (router_service/consensus.py):
  - `consensus_union(texts)`: union of tokens across responses.
  - `consensus_quorum(texts, quorum)`: returns a text repeated at least `quorum` times.
  - `consensus_two_phase(texts, agree_threshold)`: picks the text with highest average Jaccard and returns it only if average agreement meets `agree_threshold`.
- Metrics: `consensus_strategy_used_<strategy>_total` counters (one per strategy in the POC registry).
- Tests: `tests/test_multi_strategy_consensus_poc.py`.
