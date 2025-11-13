"""GAP-335A: Multi-objective scoring engine.

Provides multi-objective optimization for routing decisions with support for:
- Cost minimization
- Latency minimization
- Quality score maximization
- Carbon intensity minimization

Supports both Pareto frontier analysis and weighted scalarization approaches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# Metrics for multi-objective scoring
_H_FRONTIER_SIZE = REGISTRY.histogram("multi_objective_frontier_size", [1, 5, 10, 20, 50])
_CTR_SCORING_INVOCATIONS = REGISTRY.counter("multi_objective_scoring_invocations_total")
_CTR_PARETO_DOMINATED = REGISTRY.counter("multi_objective_pareto_dominated_total")


@dataclass
class ObjectiveVector:
    """Represents a point in multi-objective space."""

    cost: float  # USD cost (minimize)
    latency: float  # milliseconds (minimize)
    quality_score: float  # 0-1 score (maximize)
    carbon_intensity: float  # gCO2e/kWh (minimize)

    def __post_init__(self):
        """Validate objective values."""
        if not (0.0 <= self.quality_score <= 1.0):
            raise ValueError(f"Quality score must be between 0.0 and 1.0, got {self.quality_score}")
        if self.cost < 0:
            raise ValueError(f"Cost must be non-negative, got {self.cost}")
        if self.latency < 0:
            raise ValueError(f"Latency must be non-negative, got {self.latency}")
        if self.carbon_intensity < 0:
            raise ValueError(f"Carbon intensity must be non-negative, got {self.carbon_intensity}")

    def dominates(self, other: ObjectiveVector) -> bool:
        """Check if this vector dominates another in Pareto sense.

        A vector dominates another if it's better or equal in all objectives
        and strictly better in at least one objective.
        """
        # For minimization objectives (cost, latency, carbon_intensity)
        min_better_or_equal = (
            self.cost <= other.cost
            and self.latency <= other.latency
            and self.carbon_intensity <= other.carbon_intensity
        )

        # For maximization objectives (quality_score)
        max_better_or_equal = self.quality_score >= other.quality_score

        # Must be better or equal in ALL objectives
        all_better_or_equal = min_better_or_equal and max_better_or_equal

        # Must be strictly better in AT LEAST one objective
        strictly_better_in_one = (
            self.cost < other.cost
            or self.latency < other.latency
            or self.quality_score > other.quality_score
            or self.carbon_intensity < other.carbon_intensity
        )

        return all_better_or_equal and strictly_better_in_one

    def distance_to(self, other: ObjectiveVector) -> float:
        """Calculate Euclidean distance between two objective vectors."""
        # Normalize quality_score (maximize) by negating it for distance calculation
        return (
            (self.cost - other.cost) ** 2
            + (self.latency - other.latency) ** 2
            + (-self.quality_score - (-other.quality_score)) ** 2  # Negate for maximization
            + (self.carbon_intensity - other.carbon_intensity) ** 2
        ) ** 0.5


@dataclass
class ScoredOption:
    """Represents a routing option with its objective vector and metadata."""

    option_id: str
    objectives: ObjectiveVector
    metadata: dict[str, Any]
    scalar_score: float = 0.0  # For weighted scalarization


class MultiObjectiveScorer:
    """Multi-objective scoring engine for routing optimization.

    Supports both Pareto frontier analysis and weighted scalarization.
    """

    def __init__(self):
        """Initialize the multi-objective scorer."""
        self.weights = {
            "cost": 0.25,
            "latency": 0.25,
            "quality_score": 0.25,
            "carbon_intensity": 0.25,
        }

    def set_weights(
        self, cost: float = 0.25, latency: float = 0.25, quality_score: float = 0.25, carbon_intensity: float = 0.25
    ) -> None:
        """Set weights for weighted scalarization.

        Args:
            cost: Weight for cost minimization (0-1)
            latency: Weight for latency minimization (0-1)
            quality_score: Weight for quality score maximization (0-1)
            carbon_intensity: Weight for carbon intensity minimization (0-1)

        Weights must sum to 1.0.
        """
        weights = [cost, latency, quality_score, carbon_intensity]
        if not all(0 <= w <= 1 for w in weights):
            raise ValueError("All weights must be between 0 and 1")
        if abs(sum(weights) - 1.0) > 1e-6:
            raise ValueError("Weights must sum to 1.0")

        self.weights = {
            "cost": cost,
            "latency": latency,
            "quality_score": quality_score,
            "carbon_intensity": carbon_intensity,
        }

    def calculate_scalar_score(self, objectives: ObjectiveVector) -> float:
        """Calculate weighted scalar score for an objective vector.

        Higher scores are better (normalized to 0-1 range).
        """
        # Normalize each objective to 0-1 range (assuming reasonable bounds)
        # These bounds should be calibrated based on your system's characteristics
        cost_norm = max(0, 1 - objectives.cost / 10.0)  # Assume $10 is max reasonable cost
        latency_norm = max(0, 1 - objectives.latency / 5000.0)  # Assume 5s is max reasonable latency
        quality_norm = objectives.quality_score  # Already 0-1
        carbon_norm = max(0, 1 - objectives.carbon_intensity / 1000.0)  # Assume 1000 gCO2e/kWh is max

        # Calculate weighted score
        score = (
            self.weights["cost"] * cost_norm
            + self.weights["latency"] * latency_norm
            + self.weights["quality_score"] * quality_norm
            + self.weights["carbon_intensity"] * carbon_norm
        )

        return score

    def find_pareto_frontier(self, options: list[ScoredOption]) -> list[ScoredOption]:
        """Find Pareto-optimal options using dominance filtering.

        Returns the non-dominated (Pareto-optimal) options.
        """
        if not options:
            return []

        # Initialize Pareto frontier
        pareto_frontier = []

        for candidate in options:
            is_dominated = False

            # Check if candidate is dominated by any existing frontier member
            for frontier_option in pareto_frontier:
                if frontier_option.objectives.dominates(candidate.objectives):
                    is_dominated = True
                    _CTR_PARETO_DOMINATED.inc(1)
                    break

            if not is_dominated:
                # Remove any existing frontier members that are dominated by candidate
                pareto_frontier = [f for f in pareto_frontier if not candidate.objectives.dominates(f.objectives)]
                pareto_frontier.append(candidate)

        # Record frontier size
        _H_FRONTIER_SIZE.observe(len(pareto_frontier))

        return pareto_frontier

    def score_options(self, options: list[ScoredOption], use_pareto: bool = True) -> list[ScoredOption]:
        """Score routing options using multi-objective optimization.

        Args:
            options: List of routing options to score
            use_pareto: If True, use Pareto frontier; if False, use weighted scalarization

        Returns:
            Scored options (either Pareto frontier or scalar-scored)
        """
        _CTR_SCORING_INVOCATIONS.inc(1)

        if not options:
            return []

        if use_pareto:
            # Use Pareto frontier approach
            return self.find_pareto_frontier(options)
        else:
            # Use weighted scalarization approach
            for option in options:
                option.scalar_score = self.calculate_scalar_score(option.objectives)

            # Sort by scalar score (descending - higher is better)
            return sorted(options, key=lambda x: x.scalar_score, reverse=True)

    def select_best_option(
        self, options: list[ScoredOption], use_pareto: bool = True, selection_strategy: str = "first"
    ) -> ScoredOption | None:
        """Select the best option from scored options.

        Args:
            options: List of routing options
            use_pareto: Whether to use Pareto frontier or scalarization
            selection_strategy: How to select from Pareto frontier ("first", "random", "closest_to_ideal")

        Returns:
            Best option or None if no options provided
        """
        if not options:
            return None

        scored_options = self.score_options(options, use_pareto)

        if not use_pareto:
            # For scalarization, return the highest scored option
            return scored_options[0]

        # For Pareto frontier, use selection strategy
        if selection_strategy == "first":
            return scored_options[0]
        elif selection_strategy == "random":
            import random

            return random.choice(scored_options)
        elif selection_strategy == "closest_to_ideal":
            # Find option closest to ideal point (0 cost, 0 latency, 1 quality, 0 carbon)
            ideal = ObjectiveVector(cost=0, latency=0, quality_score=1, carbon_intensity=0)
            return min(scored_options, key=lambda x: x.objectives.distance_to(ideal))
        else:
            raise ValueError(f"Unknown selection strategy: {selection_strategy}")


# Global instance for import
multi_objective_scorer = MultiObjectiveScorer()
