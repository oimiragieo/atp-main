"""POC: Champion/Challenger selection (GAP-023).

Selects a challenger model given candidates with simple heuristics trading off
cost and predicted quality. Tracks challenger wins for a basic win-rate metric.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from metrics.registry import REGISTRY

_CTR_CHALLENGER_WIN = REGISTRY.counter("challenger_wins_total")
_CTR_CHALLENGER_RUNS = REGISTRY.counter("challenger_runs_total")


@dataclass
class Candidate:
    name: str
    cost_per_1k_tokens: float
    quality_pred: float


def select_challenger(primary: Candidate, pool: Iterable[Candidate]) -> Candidate | None:
    """Pick a challenger with quality gain at modest cost premium.

    Heuristic: choose candidate with quality_pred >= primary.quality_pred + 0.02
    and cost_per_1k <= primary.cost_per_1k * 1.5, preferring the best quality gain.
    Returns None if no suitable challenger.
    """
    best = None
    best_cost = float("inf")
    best_gain = 0.0
    for c in pool:
        if c.name == primary.name:
            continue
        gain = c.quality_pred - primary.quality_pred
        if gain >= 0.02 and c.cost_per_1k_tokens <= primary.cost_per_1k_tokens * 1.5:
            if (
                best is None
                or c.cost_per_1k_tokens < best_cost
                or (c.cost_per_1k_tokens == best_cost and gain > best_gain)
            ):
                best = c
                best_cost = c.cost_per_1k_tokens
                best_gain = gain
    return best


def record_outcome(primary_quality: float, challenger_quality: float) -> None:
    _CTR_CHALLENGER_RUNS.inc(1)
    if challenger_quality > primary_quality:
        _CTR_CHALLENGER_WIN.inc(1)
