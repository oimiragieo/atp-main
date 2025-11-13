"""Tests for GAP-344: Shadow evaluation & promotion workflow."""

import time
from unittest.mock import MagicMock, patch

from router_service.shadow_evaluation import ShadowEvaluationTracker


class TestShadowEvaluationTracker:
    """Test shadow evaluation tracking and promotion decisions."""

    def setup_method(self):
        """Reset tracker before each test."""
        self.tracker = ShadowEvaluationTracker()
        # Override defaults for testing
        self.tracker.min_sample_window = 10
        self.tracker.win_rate_threshold = 0.6
        self.tracker.cost_savings_threshold = 0.1
        self.tracker.max_evaluation_window_days = 7

    def test_start_shadow_evaluation(self):
        """Test starting shadow evaluation tracking."""
        self.tracker.start_shadow_evaluation("test-model")
        assert "test-model" in self.tracker.shadow_windows

        start_time, sample_count, win_count, total_savings = self.tracker.shadow_windows["test-model"]
        assert sample_count == 0
        assert win_count == 0
        assert total_savings == 0.0
        assert start_time <= time.time()

    def test_record_shadow_comparison_win_on_quality(self):
        """Test recording a comparison where shadow model wins on quality."""
        self.tracker.start_shadow_evaluation("test-model")

        self.tracker.record_shadow_comparison(
            shadow_model="test-model",
            primary_model="primary-model",
            shadow_quality=0.8,
            primary_quality=0.7,
            shadow_cost=0.05,
            primary_cost=0.10,
        )

        _, sample_count, win_count, total_savings = self.tracker.shadow_windows["test-model"]
        assert sample_count == 1
        assert win_count == 1
        assert total_savings == 0.05  # 0.10 - 0.05

    def test_record_shadow_comparison_win_on_cost_tie_quality(self):
        """Test recording a comparison where quality ties but shadow wins on cost."""
        self.tracker.start_shadow_evaluation("test-model")

        self.tracker.record_shadow_comparison(
            shadow_model="test-model",
            primary_model="primary-model",
            shadow_quality=0.8,
            primary_quality=0.8,
            shadow_cost=0.05,
            primary_cost=0.10,
        )

        _, sample_count, win_count, total_savings = self.tracker.shadow_windows["test-model"]
        assert sample_count == 1
        assert win_count == 1
        assert total_savings == 0.05

    def test_record_shadow_comparison_loss(self):
        """Test recording a comparison where shadow model loses."""
        self.tracker.start_shadow_evaluation("test-model")

        self.tracker.record_shadow_comparison(
            shadow_model="test-model",
            primary_model="primary-model",
            shadow_quality=0.6,
            primary_quality=0.8,
            shadow_cost=0.05,
            primary_cost=0.10,
        )

        _, sample_count, win_count, total_savings = self.tracker.shadow_windows["test-model"]
        assert sample_count == 1
        assert win_count == 0
        assert total_savings == 0.05

    def test_should_promote_insufficient_samples(self):
        """Test promotion check with insufficient samples."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add only 5 samples (less than min 10)
        for _i in range(5):
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8,
                primary_quality=0.7,
                shadow_cost=0.05,
                primary_cost=0.10,
            )

        should_promote, reason = self.tracker.should_promote_shadow_model("test-model")
        assert not should_promote
        assert "Insufficient samples" in reason

    def test_should_promote_good_performance(self):
        """Test promotion check with good performance."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add 15 samples with 80% win rate and good cost savings
        for i in range(15):
            wins = i < 12  # 12 wins out of 15 = 80%
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8 if wins else 0.6,
                primary_quality=0.7 if wins else 0.8,
                shadow_cost=0.0,  # Exact cost savings: 0.10 - 0.0 = 0.10 = threshold
                primary_cost=0.10,
            )

        should_promote, reason = self.tracker.should_promote_shadow_model("test-model")
        # With overridden min_sample_window=10, this should succeed
        assert should_promote
        assert "Win rate:" in reason
        assert "Cost savings:" in reason

    def test_should_promote_low_win_rate(self):
        """Test promotion check with low win rate."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add 15 samples with only 40% win rate
        for i in range(15):
            wins = i < 6  # 6 wins out of 15 = 40%
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8 if wins else 0.6,
                primary_quality=0.7 if wins else 0.8,
                shadow_cost=0.05,
                primary_cost=0.10,
            )

        should_promote, reason = self.tracker.should_promote_shadow_model("test-model")
        assert not should_promote
        assert "Win rate too low" in reason

    def test_should_promote_low_cost_savings(self):
        """Test promotion check with low cost savings."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add 15 samples with good win rate but minimal cost savings
        for _i in range(15):
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8,
                primary_quality=0.7,
                shadow_cost=0.095,  # Only $0.005 savings
                primary_cost=0.10,
            )

        should_promote, reason = self.tracker.should_promote_shadow_model("test-model")
        assert not should_promote
        assert "Cost savings too low" in reason

    def test_should_demote_poor_performance(self):
        """Test demotion check for poor performance."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add 15 samples with only 10% win rate (very poor)
        for i in range(15):
            wins = i < 2  # 2 wins out of 15 = 13%
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8 if wins else 0.6,
                primary_quality=0.7 if wins else 0.8,
                shadow_cost=0.05,
                primary_cost=0.10,
            )

        should_demote, reason = self.tracker.should_demote_shadow_model("test-model")
        assert should_demote
        assert "Poor performance" in reason

    def test_should_demote_good_performance(self):
        """Test demotion check for acceptable performance."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add 15 samples with 50% win rate (acceptable)
        for i in range(15):
            wins = i < 8  # 8 wins out of 15 = 53%
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8 if wins else 0.6,
                primary_quality=0.7 if wins else 0.8,
                shadow_cost=0.05,
                primary_cost=0.10,
            )

        should_demote, reason = self.tracker.should_demote_shadow_model("test-model")
        assert not should_demote
        assert "Performance acceptable" in reason

    def test_promote_model(self):
        """Test recording a promotion."""
        self.tracker.start_shadow_evaluation("test-model")

        # Mock the counter's inc method
        with patch("router_service.shadow_evaluation.REGISTRY") as mock_registry:
            mock_counter = MagicMock()
            mock_registry.counter.return_value = mock_counter

            # Create a new tracker with mocked registry
            tracker = ShadowEvaluationTracker()
            tracker.start_shadow_evaluation("test-model")

            tracker.promote_model("test-model")
            mock_counter.inc.assert_called_once()

        # Model should be removed from tracking (check the mocked tracker)
        assert "test-model" not in tracker.shadow_windows

    def test_demote_model(self):
        """Test recording a demotion."""
        self.tracker.start_shadow_evaluation("test-model")

        # Mock the counter's inc method
        with patch("router_service.shadow_evaluation.REGISTRY") as mock_registry:
            mock_counter = MagicMock()
            mock_registry.counter.return_value = mock_counter

            # Create a new tracker with mocked registry
            tracker = ShadowEvaluationTracker()
            tracker.start_shadow_evaluation("test-model")

            tracker.demote_model("test-model")
            mock_counter.inc.assert_called_once()

        # Model should be removed from tracking (check the mocked tracker)
        assert "test-model" not in tracker.shadow_windows

    def test_get_shadow_stats(self):
        """Test getting shadow model statistics."""
        self.tracker.start_shadow_evaluation("test-model")

        # Add some comparisons
        for _i in range(10):
            self.tracker.record_shadow_comparison(
                shadow_model="test-model",
                primary_model="primary-model",
                shadow_quality=0.8,
                primary_quality=0.7,
                shadow_cost=0.05,
                primary_cost=0.10,
            )

        stats = self.tracker.get_shadow_stats("test-model")
        assert stats is not None
        assert stats["samples"] == 10
        assert stats["win_rate"] == 1.0
        assert abs(stats["avg_cost_savings"] - 0.05) < 1e-10  # Handle floating point precision
        assert "window_age_days" in stats

    def test_get_shadow_stats_no_data(self):
        """Test getting stats for non-existent model."""
        stats = self.tracker.get_shadow_stats("non-existent")
        assert stats is None

    def test_cleanup_expired_windows(self):
        """Test cleanup of expired evaluation windows."""
        self.tracker.start_shadow_evaluation("test-model")
        self.tracker.max_evaluation_window_days = 0  # Expire immediately

        # Simulate old start time
        self.tracker.shadow_windows["test-model"] = (time.time() - 86400, 0, 0, 0.0)

        expired = self.tracker.cleanup_expired_windows()
        assert "test-model" in expired
        assert "test-model" not in self.tracker.shadow_windows

    @patch.dict("os.environ", {"SHADOW_MIN_SAMPLE_WINDOW": "20"})
    def test_config_from_environment(self):
        """Test configuration loading from environment variables."""
        tracker = ShadowEvaluationTracker()
        assert tracker.min_sample_window == 20
