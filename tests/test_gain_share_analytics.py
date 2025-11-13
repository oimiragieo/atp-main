"""Tests for GAP-335B: Gain-share cost analytics module."""

import os
import tempfile
import time
from unittest.mock import MagicMock, patch

from router_service.gain_share_analytics import BaselineEntry, FrontierModel, GainShareAnalytics


class TestGainShareAnalytics:
    """Test gain-share analytics functionality."""

    def setup_method(self):
        """Reset analytics service before each test."""
        # Use temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()

        # Change to temp directory for test isolation
        os.chdir(self.temp_dir)

        # Create fresh service instance
        self.analytics = GainShareAnalytics(data_dir=self.temp_dir)

    def teardown_method(self):
        """Clean up after each test."""
        os.chdir(self.original_cwd)
        # Clean up temp files
        for file in ["frontier_models.json", "baseline_history.jsonl"]:
            if os.path.exists(file):
                os.remove(file)

    def test_initialization_with_default_frontier_models(self):
        """Test initialization creates default frontier models."""
        assert len(self.analytics._frontier_models) > 0
        assert "premium-model" in self.analytics._frontier_models
        assert "openrouter:anthropic/claude-3.5-sonnet" in self.analytics._frontier_models

    def test_update_frontier_model(self):
        """Test updating frontier model."""
        self.analytics.update_frontier_model(
            model_name="test-model",
            cost_per_1k_tokens_usd=0.015,
            capabilities=["test", "mock"],
        )

        model = self.analytics.get_frontier_model("test-model")
        assert model is not None
        assert model.model_name == "test-model"
        assert model.cost_per_1k_tokens_usd == 0.015
        assert "test" in model.capabilities
        assert "mock" in model.capabilities

    def test_get_all_frontier_models(self):
        """Test getting all frontier models."""
        models = self.analytics.get_all_frontier_models()
        assert isinstance(models, dict)
        assert len(models) > 0

        # Should contain our default models
        assert "premium-model" in models

    def test_calculate_realized_savings_cheaper_model(self):
        """Test savings calculation when chosen model is cheaper than frontier."""
        result = self.analytics.calculate_realized_savings(
            chosen_model="cheap-model",
            tokens_used=1000,
            actual_cost_usd=0.005,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        assert "savings_usd" in result
        assert "savings_pct" in result
        assert "baseline_cost_usd" in result
        assert result["savings_usd"] > 0  # Positive savings
        assert result["savings_pct"] > 0  # Positive percentage
        assert result["baseline_cost_usd"] > result["actual_cost_usd"]

    def test_calculate_realized_savings_expensive_model(self):
        """Test savings calculation when chosen model is more expensive than frontier."""
        result = self.analytics.calculate_realized_savings(
            chosen_model="expensive-model",
            tokens_used=1000,
            actual_cost_usd=0.05,  # More expensive than frontier
            tenant="test-tenant",
            adapter="test-adapter",
        )

        assert result["savings_usd"] < 0  # Negative savings (loss)
        assert result["savings_pct"] < 0  # Negative percentage

    def test_calculate_realized_savings_zero_tokens(self):
        """Test savings calculation with zero tokens."""
        result = self.analytics.calculate_realized_savings(
            chosen_model="test-model",
            tokens_used=0,
            actual_cost_usd=0.0,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        assert result["savings_usd"] == 0.0
        assert result["savings_pct"] == 0.0
        assert result["baseline_cost_usd"] == 0.0
        assert result["actual_cost_usd"] == 0.0

    def test_baseline_history_persistence(self):
        """Test that baseline entries are persisted to history."""
        # Clear any existing history
        self.analytics._baseline_history.clear()

        # Add an entry
        self.analytics.calculate_realized_savings(
            chosen_model="test-model",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        # Create new instance to test loading
        analytics2 = GainShareAnalytics(data_dir=self.temp_dir)
        assert len(analytics2._baseline_history) > 0

        entry = analytics2._baseline_history[0]
        assert entry.model == "test-model"
        assert entry.tokens_used == 1000
        assert entry.actual_cost_usd == 0.01
        assert entry.tenant == "test-tenant"
        assert entry.adapter == "test-adapter"

    def test_get_savings_summary_all_entries(self):
        """Test getting savings summary for all entries."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        # Add multiple entries
        self.analytics.calculate_realized_savings(
            chosen_model="model1",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="tenant1",
            adapter="adapter1",
        )

        self.analytics.calculate_realized_savings(
            chosen_model="model2",
            tokens_used=2000,
            actual_cost_usd=0.02,
            tenant="tenant2",
            adapter="adapter2",
        )

        summary = self.analytics.get_savings_summary()

        assert summary["total_entries"] == 2
        assert summary["total_savings_usd"] > 0
        assert "avg_savings_pct" in summary
        assert "time_range" in summary

    def test_get_savings_summary_filtered_by_tenant(self):
        """Test getting savings summary filtered by tenant."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        # Add entries for different tenants
        self.analytics.calculate_realized_savings(
            chosen_model="model1",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="tenant1",
            adapter="adapter1",
        )

        self.analytics.calculate_realized_savings(
            chosen_model="model2",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="tenant2",
            adapter="adapter2",
        )

        summary = self.analytics.get_savings_summary(tenant="tenant1")

        assert summary["total_entries"] == 1
        assert summary["total_savings_usd"] > 0

    def test_get_savings_summary_filtered_by_timestamp(self):
        """Test getting savings summary filtered by timestamp."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        start_time = int(time.time())

        # Add entry
        self.analytics.calculate_realized_savings(
            chosen_model="model1",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="tenant1",
            adapter="adapter1",
        )

        # Get summary from future (should be empty)
        future_time = start_time + 3600
        summary = self.analytics.get_savings_summary(since_timestamp=future_time)

        assert summary["total_entries"] == 0
        assert summary["total_savings_usd"] == 0.0

    def test_get_savings_summary_empty_history(self):
        """Test getting savings summary when no entries exist."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        summary = self.analytics.get_savings_summary()

        assert summary["total_entries"] == 0
        assert summary["total_savings_usd"] == 0.0
        assert summary["avg_savings_pct"] == 0.0

    def test_get_gain_share_report(self):
        """Test generating gain-share report for a tenant."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        # Add some savings data
        self.analytics.calculate_realized_savings(
            chosen_model="cheap-model",
            tokens_used=10000,
            actual_cost_usd=0.1,
            tenant="enterprise-customer",
            adapter="test-adapter",
        )

        report = self.analytics.get_gain_share_report(
            tenant="enterprise-customer",
            gain_share_pct=25.0,
        )

        assert report["tenant"] == "enterprise-customer"
        assert report["gain_share_pct"] == 25.0
        assert "gain_share_amount_usd" in report
        assert "total_savings_usd" in report
        assert report["gain_share_amount_usd"] > 0

    def test_get_gain_share_report_no_data(self):
        """Test gain-share report when no data exists for tenant."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        report = self.analytics.get_gain_share_report(
            tenant="nonexistent-tenant",
            gain_share_pct=30.0,
        )

        assert report["tenant"] == "nonexistent-tenant"
        assert report["total_savings_usd"] == 0.0
        assert report["gain_share_amount_usd"] == 0.0
        assert report["period_entries"] == 0

    def test_frontier_model_persistence(self):
        """Test that frontier models are persisted to disk."""
        # Update a model
        self.analytics.update_frontier_model(
            model_name="persistent-model",
            cost_per_1k_tokens_usd=0.025,
            capabilities=["persistent"],
        )

        # Create new instance to test loading
        analytics2 = GainShareAnalytics(data_dir=self.temp_dir)
        model = analytics2.get_frontier_model("persistent-model")

        assert model is not None
        assert model.cost_per_1k_tokens_usd == 0.025
        assert "persistent" in model.capabilities

    def test_savings_accuracy_large_numbers(self):
        """Test savings calculation accuracy with large token counts."""
        result = self.analytics.calculate_realized_savings(
            chosen_model="test-model",
            tokens_used=1000000,  # 1M tokens
            actual_cost_usd=10.0,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        # Should handle large numbers without precision issues
        assert isinstance(result["savings_usd"], float)
        assert isinstance(result["savings_pct"], float)
        assert result["baseline_cost_usd"] > 0

    def test_multiple_entries_same_tenant(self):
        """Test handling multiple entries for the same tenant."""
        # Clear existing history
        self.analytics._baseline_history.clear()

        tenant = "multi-entry-tenant"

        # Add multiple entries
        for i in range(3):
            self.analytics.calculate_realized_savings(
                chosen_model=f"model{i}",
                tokens_used=1000,
                actual_cost_usd=0.01,
                tenant=tenant,
                adapter=f"adapter{i}",
            )

        summary = self.analytics.get_savings_summary(tenant=tenant)
        report = self.analytics.get_gain_share_report(tenant=tenant)

        assert summary["total_entries"] == 3
        assert report["period_entries"] == 3
        assert summary["total_savings_usd"] > 0

    @patch("router_service.gain_share_analytics.REGISTRY")
    def test_metrics_update(self, mock_registry):
        """Test that metrics are updated correctly."""
        # Mock the registry counters/gauges
        mock_counter = MagicMock()
        mock_gauge = MagicMock()
        mock_registry.counter.return_value = mock_counter
        mock_registry.gauge.return_value = mock_gauge

        # Create analytics instance with mocked registry
        analytics = GainShareAnalytics(data_dir=self.temp_dir)

        # Add an entry
        analytics.calculate_realized_savings(
            chosen_model="test-model",
            tokens_used=1000,
            actual_cost_usd=0.01,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        # Verify metrics were called
        mock_registry.counter.assert_called()
        mock_registry.gauge.assert_called()


class TestBaselineEntry:
    """Test BaselineEntry dataclass."""

    def test_baseline_entry_creation(self):
        """Test creating a baseline entry."""
        entry = BaselineEntry(
            timestamp=1234567890,
            model="test-model",
            tokens_used=1000,
            baseline_cost_usd=0.03,
            actual_cost_usd=0.015,
            savings_usd=0.015,
            tenant="test-tenant",
            adapter="test-adapter",
        )

        assert entry.timestamp == 1234567890
        assert entry.model == "test-model"
        assert entry.tokens_used == 1000
        assert entry.baseline_cost_usd == 0.03
        assert entry.actual_cost_usd == 0.015
        assert entry.savings_usd == 0.015
        assert entry.tenant == "test-tenant"
        assert entry.adapter == "test-adapter"


class TestFrontierModel:
    """Test FrontierModel dataclass."""

    def test_frontier_model_creation(self):
        """Test creating a frontier model."""
        model = FrontierModel(
            model_name="test-frontier",
            cost_per_1k_tokens_usd=0.025,
            capabilities=["reasoning", "code"],
            last_updated=1234567890,
        )

        assert model.model_name == "test-frontier"
        assert model.cost_per_1k_tokens_usd == 0.025
        assert "reasoning" in model.capabilities
        assert "code" in model.capabilities
        assert model.last_updated == 1234567890
