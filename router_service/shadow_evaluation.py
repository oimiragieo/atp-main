"""GAP-344: Shadow evaluation & promotion workflow for SLM models."""

import os
import time

from metrics.registry import REGISTRY


class ShadowEvaluationTracker:
    """Tracks shadow model performance over evaluation windows for promotion decisions."""

    def __init__(self) -> None:
        # GAP-344: Metrics for shadow evaluation workflow
        self._slm_promotions_total = REGISTRY.counter("slm_promotions_total")
        self._slm_demotions_total = REGISTRY.counter("slm_demotions_total")

        # Track shadow model evaluation windows
        # model_name -> (start_time, sample_count, win_count, total_cost_savings)
        self.shadow_windows: dict[str, tuple[float, int, int, float]] = {}

        # Track promotion cycles for GAP-201
        # model_name -> (first_candidate_ts, promotion_count, last_promotion_ts)
        self.promotion_cycles: dict[str, tuple[float, int, float | None]] = {}

        # Configuration
        self.min_sample_window = int(os.getenv("SHADOW_MIN_SAMPLE_WINDOW", "100"))  # Min samples before evaluation
        self.win_rate_threshold = float(os.getenv("SHADOW_WIN_RATE_THRESHOLD", "0.6"))  # 60% win rate
        self.cost_savings_threshold = float(os.getenv("SHADOW_COST_SAVINGS_THRESHOLD", "0.1"))  # 10% cost savings
        self.max_evaluation_window_days = int(os.getenv("SHADOW_MAX_WINDOW_DAYS", "7"))  # Max 7 days

    def start_shadow_evaluation(self, model_name: str) -> None:
        """Start tracking a shadow model's evaluation window."""
        if model_name not in self.shadow_windows:
            self.shadow_windows[model_name] = (time.time(), 0, 0, 0.0)

    def record_shadow_comparison(
        self,
        shadow_model: str,
        primary_model: str,
        shadow_quality: float,
        primary_quality: float,
        shadow_cost: float,
        primary_cost: float,
    ) -> None:
        """Record a shadow vs primary model comparison."""
        if shadow_model not in self.shadow_windows:
            return

        start_time, sample_count, win_count, total_savings = self.shadow_windows[shadow_model]

        # Update sample count
        sample_count += 1

        # Check if shadow model "won" this comparison
        if shadow_quality > primary_quality:
            win_count += 1
        elif shadow_quality == primary_quality and shadow_cost < primary_cost:
            # Tie on quality, but cheaper wins
            win_count += 1

        # Calculate cost savings (positive = shadow is cheaper)
        cost_savings = primary_cost - shadow_cost
        total_savings += cost_savings

        # Update tracking
        self.shadow_windows[shadow_model] = (start_time, sample_count, win_count, total_savings)

    def should_promote_shadow_model(self, model_name: str) -> tuple[bool, str]:
        """Check if a shadow model meets promotion criteria.

        Returns:
            (should_promote, reason)
        """
        if model_name not in self.shadow_windows:
            return False, "No evaluation window found"

        start_time, sample_count, win_count, total_savings = self.shadow_windows[model_name]

        # Check minimum sample window
        if sample_count < self.min_sample_window:
            return False, f"Insufficient samples: {sample_count}/{self.min_sample_window}"

        # Check evaluation window timeout
        window_age_days = (time.time() - start_time) / (24 * 3600)
        if window_age_days > self.max_evaluation_window_days:
            return False, f"Evaluation window expired: {window_age_days:.1f} days"

        # Calculate win rate
        win_rate = win_count / sample_count

        # Calculate average cost savings per sample
        avg_cost_savings = total_savings / sample_count

        # Check win rate threshold
        if win_rate < self.win_rate_threshold:
            return False, f"Win rate too low: {win_rate:.2f} < {self.win_rate_threshold}"

        # Check cost savings threshold
        if avg_cost_savings < self.cost_savings_threshold:
            return False, f"Cost savings too low: ${avg_cost_savings:.3f} < ${self.cost_savings_threshold}"

        # All criteria met
        reason = f"Win rate: {win_rate:.2f}, Cost savings: ${avg_cost_savings:.3f}, Samples: {sample_count}"
        return True, reason

    def should_demote_shadow_model(self, model_name: str) -> tuple[bool, str]:
        """Check if a shadow model should be demoted (poor performance).

        Returns:
            (should_demote, reason)
        """
        if model_name not in self.shadow_windows:
            return False, "No evaluation window found"

        start_time, sample_count, win_count, total_savings = self.shadow_windows[model_name]

        # Need minimum samples to make demotion decision
        if sample_count < self.min_sample_window:
            return False, f"Insufficient samples for demotion: {sample_count}/{self.min_sample_window}"

        # Calculate win rate
        win_rate = win_count / sample_count

        # Demote if win rate is very poor (< 20%) and we have enough samples
        poor_performance_threshold = 0.2
        if win_rate < poor_performance_threshold:
            reason = f"Poor performance: win rate {win_rate:.2f} < {poor_performance_threshold}"
            return True, reason

        return False, "Performance acceptable"

    def promote_model(self, model_name: str) -> None:
        """Record a successful promotion."""
        self._slm_promotions_total.inc()
        # Clean up tracking
        self.shadow_windows.pop(model_name, None)

    def demote_model(self, model_name: str) -> None:
        """Record a demotion."""
        self._slm_demotions_total.inc()
        # Clean up tracking
        self.shadow_windows.pop(model_name, None)

    def get_shadow_stats(self, model_name: str) -> dict[str, float] | None:
        """Get current statistics for a shadow model."""
        if model_name not in self.shadow_windows:
            return None

        start_time, sample_count, win_count, total_savings = self.shadow_windows[model_name]

        if sample_count == 0:
            return {
                "samples": 0,
                "win_rate": 0.0,
                "avg_cost_savings": 0.0,
                "window_age_days": (time.time() - start_time) / (24 * 3600),
            }

        return {
            "samples": sample_count,
            "win_rate": win_count / sample_count,
            "avg_cost_savings": total_savings / sample_count,
            "window_age_days": (time.time() - start_time) / (24 * 3600),
        }

    def record_model_candidate(self, model_name: str) -> None:
        """Record a model as a promotion candidate for cycle tracking."""
        if model_name not in self.promotion_cycles:
            self.promotion_cycles[model_name] = (time.time(), 0, None)

    def record_promotion(self, model_name: str) -> None:
        """Record a successful promotion for cycle tracking."""
        if model_name in self.promotion_cycles:
            first_ts, count, _ = self.promotion_cycles[model_name]
            self.promotion_cycles[model_name] = (first_ts, count + 1, time.time())
        else:
            # First promotion for this model
            self.promotion_cycles[model_name] = (time.time(), 1, time.time())

    def cleanup_expired_windows(self) -> list[str]:
        """Clean up expired evaluation windows and return list of expired models."""
        expired_models = []
        current_time = time.time()
        max_age_seconds = self.max_evaluation_window_days * 24 * 3600

        for model_name, (start_time, _sample_count, _win_count, _total_savings) in list(self.shadow_windows.items()):
            window_age = current_time - start_time
            if window_age > max_age_seconds:
                expired_models.append(model_name)
                del self.shadow_windows[model_name]

        return expired_models


# Global instance
shadow_tracker = ShadowEvaluationTracker()
