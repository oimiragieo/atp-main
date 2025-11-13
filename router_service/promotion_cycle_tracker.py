"""GAP-201: Promotion/demotion cycle tracking for mean_promotion_cycle_days metric."""

import time

from metrics.registry import REGISTRY


class PromotionCycleTracker:
    """Tracks promotion cycle times and computes mean_promotion_cycle_days."""

    def __init__(self) -> None:
        # Initialize metrics for GAP-201
        # Buckets for promotion cycle days: 1 hour, 1 day, 1 week, 1 month, 3 months, 6 months, 1 year
        self._promotion_cycle_days = REGISTRY.histogram("promotion_cycle_days", [1 / 24, 1, 7, 30, 90, 180, 365])
        self._mean_promotion_cycle_days = REGISTRY.gauge("mean_promotion_cycle_days")

        # Track model candidate timestamps (when first added to registry)
        self.model_candidate_times: dict[str, float] = {}

        # Track completed promotion cycles (candidate_ts, promotion_ts)
        self.completed_cycles: list[tuple[float, float]] = []

    def record_model_candidate(self, model_name: str) -> None:
        """Record when a model is first added as a candidate (shadow status)."""
        if model_name not in self.model_candidate_times:
            self.model_candidate_times[model_name] = time.time()

    def record_promotion(self, model_name: str) -> None:
        """Record when a model is promoted from shadow to active status."""
        candidate_time = self.model_candidate_times.get(model_name)
        if candidate_time is not None:
            promotion_time = time.time()
            cycle_days = (promotion_time - candidate_time) / (24 * 3600)  # Convert to days

            # Record individual cycle time
            self._promotion_cycle_days.observe(cycle_days)

            # Store completed cycle
            self.completed_cycles.append((candidate_time, promotion_time))

            # Update mean
            self._update_mean_cycle_days()

            # Clean up - model is no longer a candidate once promoted
            self.model_candidate_times.pop(model_name, None)

    def _update_mean_cycle_days(self) -> None:
        """Update the mean promotion cycle days metric."""
        if not self.completed_cycles:
            self._mean_promotion_cycle_days.set(0.0)
            return

        total_days = 0.0
        for candidate_ts, promotion_ts in self.completed_cycles:
            cycle_days = (promotion_ts - candidate_ts) / (24 * 3600)
            total_days += cycle_days

        mean_days = total_days / len(self.completed_cycles)
        self._mean_promotion_cycle_days.set(mean_days)

    def get_cycle_stats(self) -> dict[str, float]:
        """Get current promotion cycle statistics."""
        if not self.completed_cycles:
            return {"total_promotions": 0, "mean_cycle_days": 0.0, "active_candidates": len(self.model_candidate_times)}

        total_days = sum(
            (promotion_ts - candidate_ts) / (24 * 3600) for candidate_ts, promotion_ts in self.completed_cycles
        )

        return {
            "total_promotions": len(self.completed_cycles),
            "mean_cycle_days": total_days / len(self.completed_cycles),
            "active_candidates": len(self.model_candidate_times),
        }

    def reset(self) -> None:
        """Reset all tracking data (for testing)."""
        self.model_candidate_times.clear()
        self.completed_cycles.clear()
        self._update_mean_cycle_days()


# Global instance for the application
tracker = PromotionCycleTracker()
