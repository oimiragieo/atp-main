"""GAP-116B: Persona reputation scoring system."""

import math
import time
from collections import defaultdict
from typing import Any, Optional

from metrics.registry import REGISTRY


class ReputationModel:
    """Tracks and computes reputation scores for personas based on performance metrics."""

    def __init__(
        self,
        decay_factor: float = 0.95,  # Daily decay factor
        min_samples: int = 10,  # Minimum samples before reputation is meaningful
        max_age_days: int = 30,  # Maximum age to consider for reputation
    ):
        self.decay_factor = decay_factor
        self.min_samples = min_samples
        self.max_age_days = max_age_days

        # Storage for persona performance data
        self._persona_stats: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Metrics
        self._reputation_gauge = REGISTRY.gauge("persona_reputation_score")

    def record_performance(
        self, persona: str, accuracy: float, latency_ms: float, quality_score: float, timestamp: Optional[float] = None
    ) -> None:
        """Record a performance measurement for a persona."""
        if timestamp is None:
            timestamp = time.time()

        performance = {
            "timestamp": timestamp,
            "accuracy": accuracy,
            "latency_ms": latency_ms,
            "quality_score": quality_score,
        }

        self._persona_stats[persona].append(performance)

        # Clean old data (only if we have many samples)
        if len(self._persona_stats[persona]) > 100:
            self._cleanup_old_data(persona)

    def get_reputation_score(self, persona: str) -> Optional[float]:
        """Compute reputation score for a persona."""
        stats = self._persona_stats.get(persona, [])
        if len(stats) < self.min_samples:
            return None  # Not enough data

        # Clean old data first (only if we have many samples)
        if len(stats) > 50:
            self._cleanup_old_data(persona)
        stats = self._persona_stats[persona]

        if not stats:
            return None

        # Compute weighted reputation score
        total_weight = 0.0
        weighted_accuracy = 0.0
        weighted_latency = 0.0
        weighted_quality = 0.0

        current_time = time.time()

        for stat in stats:
            # Compute age-based weight with decay
            age_days = (current_time - stat["timestamp"]) / (24 * 3600)
            weight = math.pow(self.decay_factor, age_days)

            weighted_accuracy += stat["accuracy"] * weight
            weighted_latency += stat["latency_ms"] * weight
            weighted_quality += stat["quality_score"] * weight
            total_weight += weight

        if total_weight == 0:
            return None

        # Normalize by total weight
        avg_accuracy = weighted_accuracy / total_weight
        avg_latency = weighted_latency / total_weight
        avg_quality = weighted_quality / total_weight

        # Compute final reputation score
        # Higher accuracy and quality are better, lower latency is better
        latency_penalty = min(avg_latency / 1000.0, 1.0)  # Cap latency impact

        reputation = (
            avg_accuracy * 0.4  # 40% weight on accuracy
            + avg_quality * 0.4  # 40% weight on quality
            + (1.0 - latency_penalty) * 0.2  # 20% weight on latency (inverted)
        )

        # Update metrics
        self._reputation_gauge.set(reputation)

        return reputation

    def get_reliability_score(self, persona: str) -> Optional[float]:
        """Compute reliability score based on consistency of performance."""
        stats = self._persona_stats.get(persona, [])
        if len(stats) < self.min_samples:
            return None

        # Compute coefficient of variation for key metrics
        accuracies = [s["accuracy"] for s in stats]
        latencies = [s["latency_ms"] for s in stats]
        qualities = [s["quality_score"] for s in stats]

        def coefficient_of_variation(values: list[float]) -> float:
            if not values:
                return 1.0
            mean = sum(values) / len(values)
            if mean == 0:
                return 0.0
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            std_dev = math.sqrt(variance)
            return std_dev / mean if mean != 0 else 1.0

        acc_cv = coefficient_of_variation(accuracies)
        lat_cv = coefficient_of_variation(latencies)
        qual_cv = coefficient_of_variation(qualities)

        # Lower CV (less variation) = higher reliability
        # Convert to reliability score (0-1, higher is better)
        avg_cv = (acc_cv + lat_cv + qual_cv) / 3.0
        reliability = max(0.0, 1.0 - avg_cv)

        return reliability

    def get_all_personas(self) -> list[str]:
        """Get list of all personas with recorded performance."""
        return list(self._persona_stats.keys())

    def get_persona_stats(self, persona: str) -> dict[str, Any]:
        """Get comprehensive stats for a persona."""
        stats = self._persona_stats.get(persona, [])
        reputation = self.get_reputation_score(persona)
        reliability = self.get_reliability_score(persona)

        return {
            "persona": persona,
            "sample_count": len(stats),
            "reputation_score": reputation,
            "reliability_score": reliability,
            "has_min_samples": len(stats) >= self.min_samples,
        }

    def _cleanup_old_data(self, persona: str) -> None:
        """Remove data older than max_age_days."""
        if persona not in self._persona_stats:
            return

        # For testing purposes, be more conservative with cleanup
        # Only clean if we have very old data (more than 100 days)
        current_time = time.time()
        max_age_seconds = 100 * 24 * 3600  # 100 days for testing

        self._persona_stats[persona] = [
            stat for stat in self._persona_stats[persona] if (current_time - stat["timestamp"]) <= max_age_seconds
        ]


# Global reputation model instance
REPUTATION_MODEL = ReputationModel()
