"""GAP-214: Request-level cost/regret savings KPI.

This module calculates regret metrics for routing decisions,
measuring the cost difference between chosen and optimal models.
"""

from dataclasses import dataclass
from typing import Any, Optional

from metrics.registry import REGISTRY

from .model_manifest import policy_permit
from .routing_constants import QUALITY_THRESH, Candidate


@dataclass
class RegretAnalysis:
    """Analysis of regret for a routing decision."""

    chosen_model: str
    chosen_cost: float
    optimal_model: str
    optimal_cost: float
    regret_amount: float
    regret_percentage: float
    quality_requirement: str
    latency_requirement_ms: int
    total_tokens: int
    viable_candidates: int


class RegretCalculator:
    """Calculates regret for routing decisions."""

    def __init__(self):
        self.regret_pct_histogram = REGISTRY.histogram(
            "regret_pct", [0.0, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0]
        )

    def calculate_regret(
        self,
        chosen: Candidate,
        all_candidates: list[Candidate],
        quality: str,
        latency_slo_ms: int,
        registry: dict[str, Any],
        total_tokens: int,
    ) -> RegretAnalysis:
        """Calculate regret for a routing decision.

        Args:
            chosen: The model that was actually chosen
            all_candidates: All available candidate models
            quality: Quality requirement ("fast", "balanced", "high")
            latency_slo_ms: Latency requirement in milliseconds
            registry: Model registry with status and safety info
            total_tokens: Total tokens in the request

        Returns:
            RegretAnalysis with detailed regret metrics
        """
        q_min = QUALITY_THRESH.get(quality, 0.75)

        # Find all viable candidates that meet quality, latency, and safety requirements
        viable_candidates = []
        for candidate in all_candidates:
            rec = registry.get(candidate.name, {})

            # Skip shadow models
            if rec.get("status") == "shadow":
                continue

            # Check safety requirement
            if not policy_permit(rec, "A"):
                continue

            # Check quality and latency requirements
            if candidate.quality_pred >= q_min and candidate.latency_p95 <= latency_slo_ms:
                viable_candidates.append(candidate)

        if not viable_candidates:
            # No viable candidates - this shouldn't happen in normal operation
            return RegretAnalysis(
                chosen_model=chosen.name,
                chosen_cost=0.0,
                optimal_model="none",
                optimal_cost=0.0,
                regret_amount=0.0,
                regret_percentage=0.0,
                quality_requirement=quality,
                latency_requirement_ms=latency_slo_ms,
                total_tokens=total_tokens,
                viable_candidates=0,
            )

        # Find the optimal (cheapest) viable candidate
        optimal = min(viable_candidates, key=lambda c: c.cost_per_1k_tokens)

        # Calculate costs for the request
        chosen_cost = (chosen.cost_per_1k_tokens / 1000.0) * total_tokens
        optimal_cost = (optimal.cost_per_1k_tokens / 1000.0) * total_tokens

        # Calculate regret
        regret_amount = chosen_cost - optimal_cost
        regret_percentage = (regret_amount / optimal_cost) * 100.0 if optimal_cost > 0 else 0.0

        # Record regret percentage in histogram
        self.regret_pct_histogram.observe(regret_percentage)

        return RegretAnalysis(
            chosen_model=chosen.name,
            chosen_cost=chosen_cost,
            optimal_model=optimal.name,
            optimal_cost=optimal_cost,
            regret_amount=regret_amount,
            regret_percentage=regret_percentage,
            quality_requirement=quality,
            latency_requirement_ms=latency_slo_ms,
            total_tokens=total_tokens,
            viable_candidates=len(viable_candidates),
        )

    def get_regret_summary(self, analyses: list[RegretAnalysis]) -> dict[str, float]:
        """Get summary statistics for a batch of regret analyses.

        Args:
            analyses: List of regret analyses

        Returns:
            Dictionary with summary statistics
        """
        if not analyses:
            return {
                "total_analyses": 0,
                "avg_regret_pct": 0.0,
                "max_regret_pct": 0.0,
                "regret_above_1pct_count": 0,
                "regret_above_5pct_count": 0,
                "perfect_decisions_pct": 0.0,
            }

        total_regret = sum(a.regret_percentage for a in analyses)
        max_regret = max(a.regret_percentage for a in analyses)
        regret_above_1pct = sum(1 for a in analyses if a.regret_percentage > 1.0)
        regret_above_5pct = sum(1 for a in analyses if a.regret_percentage > 5.0)
        perfect_decisions = sum(1 for a in analyses if a.regret_percentage == 0.0)

        return {
            "total_analyses": len(analyses),
            "avg_regret_pct": total_regret / len(analyses),
            "max_regret_pct": max_regret,
            "regret_above_1pct_count": regret_above_1pct,
            "regret_above_5pct_count": regret_above_5pct,
            "perfect_decisions_pct": (perfect_decisions / len(analyses)) * 100.0,
        }


# Global instance
_regret_calculator: Optional[RegretCalculator] = None


def get_regret_calculator() -> RegretCalculator:
    """Get global regret calculator instance."""
    global _regret_calculator
    if _regret_calculator is None:
        _regret_calculator = RegretCalculator()
    return _regret_calculator
