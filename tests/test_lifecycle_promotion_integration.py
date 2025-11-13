"""Tests for promotion cycle tracking integration with lifecycle."""

from unittest.mock import MagicMock, patch

from router_service.lifecycle import evaluate_promotions, initialize_promotion_tracking
from router_service.shadow_evaluation import shadow_tracker


class TestLifecycleIntegration:
    """Test promotion cycle tracking integration with lifecycle management."""

    def setup_method(self):
        """Reset tracker before each test."""
        shadow_tracker.promotion_cycles.clear()
        shadow_tracker.shadow_windows.clear()

    def test_initialize_promotion_tracking(self):
        """Test that shadow models are registered as candidates on initialization."""
        model_registry = {
            "active-model": {"status": "active"},
            "shadow-model": {"status": "shadow"},
            "another-shadow": {"status": "shadow"},
            "fallback-model": {"status": "fallback"},
        }

        initialize_promotion_tracking(model_registry)

        # Only shadow models should be recorded as candidates
        assert "active-model" not in shadow_tracker.promotion_cycles
        assert "shadow-model" in shadow_tracker.promotion_cycles
        assert "another-shadow" in shadow_tracker.promotion_cycles
        assert "fallback-model" not in shadow_tracker.promotion_cycles

    def test_promotion_records_cycle(self):
        """Test that promotion evaluation records cycle completion."""
        # Setup model registry with shadow model
        model_registry = {"active-model": {"status": "active"}, "shadow-model": {"status": "shadow"}}

        # Initialize tracking
        initialize_promotion_tracking(model_registry)

        # Setup mock functions
        lifecycle_append = MagicMock()
        persist = MagicMock()
        record_obs = MagicMock()

        # Setup stats map (shadow model has good performance)
        stats_map = {
            "active-model": (100, 10.0),  # 100 calls, $10 total, $0.10 avg
            "shadow-model": (50, 3.0),  # 50 calls, $3 total, $0.06 avg (better)
        }

        model_last_action = {}
        promotion_counter_ref = {"value": 0}

        # Mock time for consistent testing
        with patch("time.time", return_value=1000000):
            evaluate_promotions(
                "test-cluster",
                model_registry,
                model_last_action,
                stats_map,
                lifecycle_append,
                persist,
                record_obs,
                promotion_counter_ref,
            )

        # Should have promoted the shadow model
        assert model_registry["shadow-model"]["status"] == "active"
        assert promotion_counter_ref["value"] == 1

        # Should have recorded the promotion cycle
        assert "shadow-model" in shadow_tracker.promotion_cycles
        first_ts, count, last_ts = shadow_tracker.promotion_cycles["shadow-model"]
        assert count == 1
        assert last_ts == 1000000  # Mocked time

    def test_promotion_without_prior_candidate(self):
        """Test promotion of model that wasn't tracked as candidate."""
        model_registry = {
            "active-model": {"status": "active"},
            "new-shadow": {"status": "shadow"},  # Not initialized in tracker
        }

        # Setup stats map
        stats_map = {"active-model": (100, 10.0), "new-shadow": (50, 3.0)}

        model_last_action = {}
        promotion_counter_ref = {"value": 0}

        # Mock functions
        lifecycle_append = MagicMock()
        persist = MagicMock()
        record_obs = MagicMock()

        evaluate_promotions(
            "test-cluster",
            model_registry,
            model_last_action,
            stats_map,
            lifecycle_append,
            persist,
            record_obs,
            promotion_counter_ref,
        )

        # Should still promote and record cycle (tracker creates entry on first promotion)
        assert model_registry["new-shadow"]["status"] == "active"
        # Model gets recorded in promotion cycles even if not initialized as candidate
        assert "new-shadow" in shadow_tracker.promotion_cycles
        first_ts, count, last_ts = shadow_tracker.promotion_cycles["new-shadow"]
        assert count == 1
