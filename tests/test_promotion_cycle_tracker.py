"""Tests for promotion cycle tracking."""

import time
from unittest.mock import patch

import pytest

from router_service.promotion_cycle_tracker import PromotionCycleTracker, tracker


class TestPromotionCycleTracker:
    """Test promotion cycle tracking functionality."""

    def test_initial_state(self):
        """Test initial state of promotion cycle tracker."""
        tracker = PromotionCycleTracker()
        assert tracker.model_candidate_times == {}
        assert tracker.completed_cycles == []
        stats = tracker.get_cycle_stats()
        assert stats["total_promotions"] == 0
        assert stats["mean_cycle_days"] == 0.0
        assert stats["active_candidates"] == 0

    def test_record_model_candidate(self):
        """Test recording a model candidate."""
        tracker = PromotionCycleTracker()
        tracker.record_model_candidate("test-model")

        assert "test-model" in tracker.model_candidate_times
        assert isinstance(tracker.model_candidate_times["test-model"], float)

    def test_record_model_candidate_duplicate(self):
        """Test recording the same model candidate multiple times doesn't overwrite timestamp."""
        tracker = PromotionCycleTracker()
        tracker.record_model_candidate("test-model")
        first_time = tracker.model_candidate_times["test-model"]

        time.sleep(0.001)  # Small delay
        tracker.record_model_candidate("test-model")

        # Should keep the original timestamp
        assert tracker.model_candidate_times["test-model"] == first_time

    def test_record_promotion_without_candidate(self):
        """Test recording promotion for model that was never a candidate."""
        tracker = PromotionCycleTracker()
        tracker.record_promotion("unknown-model")

        # Should not add to completed cycles
        assert len(tracker.completed_cycles) == 0

    def test_record_promotion_with_candidate(self):
        """Test recording promotion for a valid candidate."""
        tracker = PromotionCycleTracker()
        tracker.record_model_candidate("test-model")

        # Simulate time passing (1 day)
        candidate_time = tracker.model_candidate_times["test-model"]
        with patch("time.time", return_value=candidate_time + 24 * 3600):
            tracker.record_promotion("test-model")

        # Should have one completed cycle
        assert len(tracker.completed_cycles) == 1
        assert tracker.completed_cycles[0][0] == candidate_time
        assert tracker.completed_cycles[0][1] == candidate_time + 24 * 3600

        # Model should be removed from candidates
        assert "test-model" not in tracker.model_candidate_times

        # Stats should reflect 1 day cycle
        stats = tracker.get_cycle_stats()
        assert stats["total_promotions"] == 1
        assert stats["mean_cycle_days"] == pytest.approx(1.0, abs=0.01)

    def test_multiple_promotions(self):
        """Test tracking multiple promotion cycles."""
        tracker = PromotionCycleTracker()

        # First model: 1 day cycle
        tracker.record_model_candidate("model1")
        candidate1_time = tracker.model_candidate_times["model1"]
        with patch("time.time", return_value=candidate1_time + 24 * 3600):
            tracker.record_promotion("model1")

        # Second model: 2 day cycle
        tracker.record_model_candidate("model2")
        candidate2_time = tracker.model_candidate_times["model2"]
        with patch("time.time", return_value=candidate2_time + 2 * 24 * 3600):
            tracker.record_promotion("model2")

        # Check stats
        stats = tracker.get_cycle_stats()
        assert stats["total_promotions"] == 2
        assert stats["mean_cycle_days"] == pytest.approx(1.5, abs=0.01)  # (1 + 2) / 2

    def test_metrics_integration(self):
        """Test that metrics are updated during promotion tracking."""
        with patch("router_service.promotion_cycle_tracker.REGISTRY") as mock_registry:
            mock_histogram = mock_registry.histogram.return_value
            mock_gauge = mock_registry.gauge.return_value
            tracker = PromotionCycleTracker()

            tracker.record_model_candidate("test-model")
            candidate_time = tracker.model_candidate_times["test-model"]

            with patch("time.time", return_value=candidate_time + 12 * 3600):  # 0.5 days
                tracker.record_promotion("test-model")

            # Should have observed the cycle time in histogram
            mock_histogram.observe.assert_called_with(pytest.approx(0.5, abs=0.01))
            # Should have updated the gauge
            mock_gauge.set.assert_called()

    def test_get_cycle_stats_empty(self):
        """Test getting stats when no cycles have been completed."""
        tracker = PromotionCycleTracker()
        stats = tracker.get_cycle_stats()

        expected = {"total_promotions": 0, "mean_cycle_days": 0.0, "active_candidates": 0}
        assert stats == expected

    def test_reset(self):
        """Test resetting the tracker."""
        tracker = PromotionCycleTracker()
        tracker.record_model_candidate("test-model")
        tracker.completed_cycles.append((1000000, 1000001))

        tracker.reset()

        assert tracker.model_candidate_times == {}
        assert tracker.completed_cycles == []


class TestGlobalTracker:
    """Test the global tracker instance."""

    def test_global_tracker_is_instance(self):
        """Test that the global tracker is properly instantiated."""
        assert isinstance(tracker, PromotionCycleTracker)

    def test_global_tracker_functionality(self):
        """Test that the global tracker works as expected."""
        # Reset the global tracker
        tracker.model_candidate_times.clear()
        tracker.completed_cycles.clear()

        tracker.record_model_candidate("global-test-model")
        assert "global-test-model" in tracker.model_candidate_times
