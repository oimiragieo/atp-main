"""Tests for GAP-345: Regret & savings computation service."""

from unittest.mock import patch

from router_service.regret_computation import RegretComputationService


class TestRegretComputationService:
    """Test regret and savings calculations."""

    def setup_method(self):
        """Reset service before each test."""
        self.service = RegretComputationService()

    def test_load_model_costs_from_registry(self):
        """Test loading costs from model registry JSON."""
        # Should load costs from the registry file
        costs = self.service._model_costs
        assert isinstance(costs, dict)
        assert len(costs) > 0

        # Should have some expected models
        assert "premium-model" in costs
        assert "cheap-model" in costs

    def test_identify_frontier_model(self):
        """Test identification of frontier model (most expensive)."""
        frontier = self.service._frontier_model
        assert isinstance(frontier, str)
        assert len(frontier) > 0

        # Frontier should be in the costs dict
        assert frontier in self.service._model_costs

    def test_calculate_regret_cheaper_model(self):
        """Test regret calculation when chosen model is cheaper than frontier."""
        # Choose cheap model vs premium frontier
        result = self.service.calculate_regret(
            chosen_model="cheap-model",
            tokens_used=1000,
            actual_cost_usd=0.005,  # $0.005 per 1k tokens
        )

        assert "regret_pct" in result
        assert "savings_usd" in result
        assert "frontier_cost_usd" in result
        assert result["regret_pct"] < 0  # Negative regret = savings
        assert result["savings_usd"] > 0  # Positive savings

    def test_calculate_regret_expensive_model(self):
        """Test regret calculation when chosen model is more expensive than frontier."""
        # Choose expensive model
        result = self.service.calculate_regret(
            chosen_model="premium-model",
            tokens_used=1000,
            actual_cost_usd=0.03,  # $0.03 per 1k tokens
        )

        assert result["regret_pct"] >= 0  # Non-negative regret
        assert result["savings_usd"] <= 0  # Non-positive savings

    def test_calculate_regret_unknown_model(self):
        """Test regret calculation for unknown model."""
        result = self.service.calculate_regret(chosen_model="unknown-model", tokens_used=1000, actual_cost_usd=0.01)

        # Should still calculate based on actual cost
        assert "regret_pct" in result
        assert isinstance(result["regret_pct"], float)

    def test_calculate_savings_pct(self):
        """Test savings percentage calculation."""
        savings_pct = self.service.calculate_savings_pct(
            chosen_model="cheap-model", tokens_used=1000, actual_cost_usd=0.005
        )

        assert isinstance(savings_pct, float)
        # Cheap model should show positive savings
        assert savings_pct > 0

    def test_get_frontier_cost_per_1k_tokens(self):
        """Test getting frontier cost per 1k tokens."""
        cost = self.service.get_frontier_cost_per_1k_tokens()
        assert isinstance(cost, float)
        assert cost > 0

    def test_regret_with_zero_tokens(self):
        """Test regret calculation with zero tokens."""
        result = self.service.calculate_regret(chosen_model="cheap-model", tokens_used=0, actual_cost_usd=0.0)

        assert result["regret_pct"] == 0.0
        assert result["savings_usd"] == 0.0

    def test_fallback_costs_when_registry_missing(self):
        """Test fallback costs when registry file is missing."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            service = RegretComputationService()
            assert len(service._model_costs) > 0
            assert "premium-model" in service._model_costs

    def test_metric_update(self):
        """Test that regret metric is updated."""
        # This would normally update the Prometheus metric
        result = self.service.calculate_regret(chosen_model="cheap-model", tokens_used=1000, actual_cost_usd=0.005)

        # Metric should have been set (we can't easily test the actual metric value
        # without mocking the registry, but the call should not error)
        assert result["regret_pct"] is not None

    def test_large_token_count(self):
        """Test regret calculation with large token counts."""
        result = self.service.calculate_regret(
            chosen_model="cheap-model",
            tokens_used=100000,  # 100k tokens
            actual_cost_usd=0.5,
        )

        assert isinstance(result["regret_pct"], float)
        assert isinstance(result["savings_usd"], float)
        assert result["frontier_cost_usd"] > 0
