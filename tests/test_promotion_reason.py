"""Tests for GAP-217: Promotion reason parameterization."""

from router_service.lifecycle import build_promotion_reason


class TestPromotionReasonBuilder:
    """Test cases for the build_promotion_reason function."""

    def test_cost_improvement_only(self):
        """Test promotion reason when only cost improvement meets threshold."""
        reason = build_promotion_reason(
            shadow_model="gpt-4-turbo",
            shadow_stats=(100, 90, 50.0, 2000.0),  # 90% success, $0.50 avg cost, 20s avg latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # 85% success, $1.00 avg cost, 25s avg latency
            cost_threshold=0.8,
        )
        assert "cost_improvement_50.0pct" in reason

    def test_success_rate_improvement_only(self):
        """Test promotion reason when only success rate improvement."""
        reason = build_promotion_reason(
            shadow_model="claude-3",
            shadow_stats=(100, 95, 95.0, 2200.0),  # 95% success, $0.95 avg cost, 22s avg latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # 85% success, $1.00 avg cost, 25s avg latency
            cost_threshold=0.8,
        )
        # Cost: 0.95 < 1.00 * 0.8 = 0.95 < 0.80? No
        # Success: 95% > 85%? Yes (11.8% improvement)
        # Latency: 22s < 25s? Yes (12.0% improvement)
        # Primary reason should be latency (higher improvement percentage)
        assert "latency_improvement_12.0pct_plus_1_other_criteria" in reason

    def test_latency_improvement_only(self):
        """Test promotion reason when only latency improvement."""
        reason = build_promotion_reason(
            shadow_model="claude-3-fast",
            shadow_stats=(100, 85, 95.0, 1500.0),  # 85% success, $0.95 avg cost, 15s avg latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # 85% success, $1.00 avg cost, 25s avg latency
            cost_threshold=0.8,
        )
        assert "latency_improvement_40.0pct" in reason

    def test_multiple_criteria_met(self):
        """Test promotion reason when multiple criteria are met."""
        reason = build_promotion_reason(
            shadow_model="gpt-4-turbo",
            shadow_stats=(100, 95, 50.0, 2000.0),  # 95% success, $0.50 avg cost, 20s avg latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # 85% success, $1.00 avg cost, 25s avg latency
            cost_threshold=0.8,
        )
        # Should include cost improvement as primary reason plus others
        assert "cost_improvement_50.0pct_plus_2_other_criteria" in reason

    def test_threshold_not_met(self):
        """Test when no improvement criteria are met."""
        reason = build_promotion_reason(
            shadow_model="expensive-model",
            shadow_stats=(100, 80, 120.0, 3000.0),  # 80% success, $1.20 avg cost, 30s avg latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # 85% success, $1.00 avg cost, 25s avg latency
            cost_threshold=0.8,
        )
        assert reason == "threshold_not_met"

    def test_insufficient_data(self):
        """Test when shadow model has no calls."""
        reason = build_promotion_reason(
            shadow_model="new-model",
            shadow_stats=(0, 0, 0.0, 0.0),  # No calls
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),
            cost_threshold=0.8,
        )
        assert reason == "insufficient_data"

    def test_primary_insufficient_data(self):
        """Test when primary model has no calls."""
        reason = build_promotion_reason(
            shadow_model="shadow-model",
            shadow_stats=(100, 90, 50.0, 2000.0),
            primary_model="primary-model",
            primary_stats=(0, 0, 0.0, 0.0),  # No calls
            cost_threshold=0.8,
        )
        assert reason == "insufficient_data"

    def test_cost_threshold_customization(self):
        """Test that custom cost threshold works correctly."""
        reason = build_promotion_reason(
            shadow_model="gpt-4-turbo",
            shadow_stats=(100, 90, 90.0, 2000.0),  # $0.90 avg cost, 20s latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # $1.00 avg cost, 25s latency
            cost_threshold=0.95,  # 5% improvement required
        )
        # Cost: 0.90 < 1.00 * 0.95 = 0.90 < 0.95? Yes (10% improvement)
        # Success: 90% > 85%? Yes (5.9% improvement)
        # Latency: 20s < 25s? Yes (20% improvement)
        # Primary should be latency (highest improvement)
        assert "latency_improvement_20.0pct_plus_2_other_criteria" in reason

    def test_cost_threshold_not_met_custom(self):
        """Test when cost improvement doesn't meet custom threshold."""
        reason = build_promotion_reason(
            shadow_model="gpt-4-turbo",
            shadow_stats=(100, 90, 95.0, 2000.0),  # $0.95 avg cost, 20s latency
            primary_model="gpt-4",
            primary_stats=(100, 85, 100.0, 2500.0),  # $1.00 avg cost, 25s latency
            cost_threshold=0.92,  # 8% improvement required, but only 5% achieved
        )
        # Cost: 0.95 < 1.00 * 0.92 = 0.95 < 0.92? No (only 5% improvement)
        # Success: 90% > 85%? Yes (5.9% improvement)
        # Latency: 20s < 25s? Yes (20% improvement)
        # Should detect success and latency, primary latency
        assert "latency_improvement_20.0pct_plus_1_other_criteria" in reason
