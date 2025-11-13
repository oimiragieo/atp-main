#!/usr/bin/env python3
"""
Tests for Revenue Share Reporting Export Tool
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.revenue_share_reporter import AdapterRevenue, RevenueShareConfig, RevenueShareReporter


class TestRevenueShareReporter:
    """Test cases for RevenueShareReporter."""

    @pytest.fixture
    def config(self):
        """Test configuration."""
        return RevenueShareConfig(
            gold_revenue_share=0.70,
            silver_revenue_share=0.65,
            bronze_revenue_share=0.60,
            minimum_payout=10.0,
            reporting_period_days=30,
        )

    @pytest.fixture
    def reporter(self, config):
        """Test reporter instance."""
        return RevenueShareReporter(config)

    @pytest.fixture
    def mock_cost_snapshot(self):
        """Mock cost snapshot data."""
        return {"gold": 1000.0, "silver": 800.0, "bronze": 600.0}

    @pytest.fixture
    def mock_adapter_costs(self):
        """Mock per-adapter cost data."""
        return {"adapter-001": {"gold": 1000.0}, "adapter-002": {"silver": 800.0}, "adapter-003": {"bronze": 600.0}}

    def test_calculate_revenue_shares(self, reporter, mock_cost_snapshot, mock_adapter_costs):
        """Test revenue share calculations."""
        with patch.object(reporter, "_get_adapter_data") as mock_get_adapters:
            mock_get_adapters.return_value = [
                {"id": "adapter-001", "name": "Test Adapter 1", "qos_level": "gold", "transaction_count": 100},
                {"id": "adapter-002", "name": "Test Adapter 2", "qos_level": "silver", "transaction_count": 80},
                {"id": "adapter-003", "name": "Test Adapter 3", "qos_level": "bronze", "transaction_count": 60},
            ]

            revenue_data = reporter.calculate_revenue_shares(mock_cost_snapshot, mock_adapter_costs)

            assert len(revenue_data) == 3

            # Check gold adapter
            gold_adapter = next(r for r in revenue_data if r.adapter_id == "adapter-001")
            assert gold_adapter.total_cost == 1000.0
            assert gold_adapter.revenue_share == 700.0  # 1000 * 0.70
            assert gold_adapter.payout_amount == 700.0

            # Check silver adapter
            silver_adapter = next(r for r in revenue_data if r.adapter_id == "adapter-002")
            assert silver_adapter.total_cost == 800.0
            assert silver_adapter.revenue_share == 520.0  # 800 * 0.65
            assert silver_adapter.payout_amount == 520.0

            # Check bronze adapter
            bronze_adapter = next(r for r in revenue_data if r.adapter_id == "adapter-003")
            assert bronze_adapter.total_cost == 600.0
            assert bronze_adapter.revenue_share == 360.0  # 600 * 0.60
            assert bronze_adapter.payout_amount == 360.0

    def test_minimum_payout_threshold(self, reporter, mock_cost_snapshot):
        """Test minimum payout threshold."""
        with patch.object(reporter, "_get_adapter_data") as mock_get_adapters:
            mock_get_adapters.return_value = [
                {"id": "adapter-001", "name": "Low Revenue Adapter", "qos_level": "gold", "transaction_count": 1},
            ]

            # Mock low cost that would result in payout below minimum
            low_adapter_costs = {"adapter-001": {"gold": 5.0}}  # 5 * 0.70 = 3.5 < 10.0 minimum

            revenue_data = reporter.calculate_revenue_shares(mock_cost_snapshot, low_adapter_costs)

            assert len(revenue_data) == 1
            adapter = revenue_data[0]
            assert adapter.revenue_share == 3.5
            assert adapter.payout_amount == 10.0  # Minimum payout applied

    def test_get_revenue_share_rate(self, reporter):
        """Test revenue share rate lookup."""
        assert reporter._get_revenue_share_rate("gold") == 0.70
        assert reporter._get_revenue_share_rate("silver") == 0.65
        assert reporter._get_revenue_share_rate("bronze") == 0.60
        assert reporter._get_revenue_share_rate("unknown") == 0.0

    def test_generate_json_report(self, reporter, mock_cost_snapshot, mock_adapter_costs, tmp_path):
        """Test JSON report generation."""
        with (
            patch.object(reporter, "_get_adapter_data") as mock_get_adapters,
            patch("tools.revenue_share_reporter.GLOBAL_COST") as mock_global_cost,
        ):
            mock_get_adapters.return_value = [
                {"id": "adapter-001", "name": "Test Adapter", "qos_level": "gold", "transaction_count": 100},
            ]
            mock_global_cost.snapshot.return_value = mock_cost_snapshot
            mock_global_cost.snapshot_by_adapter.return_value = mock_adapter_costs

            output_path = tmp_path / "test_report.json"
            reporter.generate_report(str(output_path), "json")

            assert output_path.exists()

            with open(output_path, encoding="utf-8") as f:
                report = json.load(f)

            assert "report_metadata" in report
            assert "revenue_data" in report
            assert "summary" in report
            assert len(report["revenue_data"]) == 1
            assert report["revenue_data"][0]["adapter_id"] == "adapter-001"
            assert report["revenue_data"][0]["payout_amount"] == 700.0

    def test_generate_csv_report(self, reporter, mock_cost_snapshot, mock_adapter_costs, tmp_path):
        """Test CSV report generation."""
        with (
            patch.object(reporter, "_get_adapter_data") as mock_get_adapters,
            patch("tools.revenue_share_reporter.GLOBAL_COST") as mock_global_cost,
        ):
            mock_get_adapters.return_value = [
                {"id": "adapter-001", "name": "Test Adapter", "qos_level": "gold", "transaction_count": 100},
            ]
            mock_global_cost.snapshot.return_value = mock_cost_snapshot
            mock_global_cost.snapshot_by_adapter.return_value = mock_adapter_costs

            output_path = tmp_path / "test_report.csv"
            reporter.generate_report(str(output_path), "csv")

            assert output_path.exists()

            with open(output_path, encoding="utf-8") as f:
                lines = f.readlines()

            assert len(lines) == 2  # Header + 1 data row
            assert (
                "Adapter ID,Adapter Name,QoS Level,Total Cost,Revenue Share,Payout Amount,Transaction Count" in lines[0]
            )
            assert "adapter-001,Test Adapter,gold,1000.00,700.00,700.00,100" in lines[1]

    def test_validate_revenue_calculations_valid(self, reporter):
        """Test validation of valid revenue calculations."""
        revenue_data = [
            AdapterRevenue(
                adapter_id="adapter-001",
                adapter_name="Test Adapter",
                qos_level="gold",
                total_cost=1000.0,
                revenue_share=700.0,  # 1000 * 0.70
                payout_amount=700.0,
                transaction_count=100,
            )
        ]

        assert reporter.validate_revenue_calculations(revenue_data)

    def test_validate_revenue_calculations_invalid(self, reporter):
        """Test validation of invalid revenue calculations."""
        revenue_data = [
            AdapterRevenue(
                adapter_id="adapter-001",
                adapter_name="Test Adapter",
                qos_level="gold",
                total_cost=1000.0,
                revenue_share=500.0,  # Incorrect: should be 700.0
                payout_amount=500.0,
                transaction_count=100,
            )
        ]

        assert not reporter.validate_revenue_calculations(revenue_data)

    def test_generate_report_unsupported_format(self, reporter):
        """Test error handling for unsupported report format."""
        with pytest.raises(ValueError, match="Unsupported format"):
            reporter.generate_report("test.txt", "txt")

    def test_metrics_update(self, config, mock_cost_snapshot, mock_adapter_costs):
        """Test that metrics are updated during report generation."""
        with patch("tools.revenue_share_reporter.REGISTRY") as mock_registry:
            mock_counter = MagicMock()
            mock_registry.counter.return_value = mock_counter

            reporter = RevenueShareReporter(config)

            with (
                patch.object(reporter, "_get_adapter_data") as mock_get_adapters,
                patch("tools.revenue_share_reporter.GLOBAL_COST") as mock_global_cost,
            ):
                mock_get_adapters.return_value = [
                    {"id": "adapter-001", "name": "Test Adapter", "qos_level": "gold", "transaction_count": 100},
                ]
                mock_global_cost.snapshot.return_value = mock_cost_snapshot
                mock_global_cost.snapshot_by_adapter.return_value = mock_adapter_costs

                with tempfile.TemporaryDirectory() as tmp_dir:
                    output_path = Path(tmp_dir) / "test_report.json"
                    reporter.generate_report(str(output_path), "json")

                # Verify metrics were updated (700.00 * 100 = 70000 cents)
                mock_counter.inc.assert_called_once_with(70000)


class TestRevenueShareConfig:
    """Test cases for RevenueShareConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RevenueShareConfig()
        assert config.gold_revenue_share == 0.70
        assert config.silver_revenue_share == 0.65
        assert config.bronze_revenue_share == 0.60
        assert config.minimum_payout == 10.0
        assert config.reporting_period_days == 30

    def test_custom_config(self):
        """Test custom configuration values."""
        config = RevenueShareConfig(
            gold_revenue_share=0.80,
            silver_revenue_share=0.75,
            bronze_revenue_share=0.70,
            minimum_payout=5.0,
            reporting_period_days=7,
        )
        assert config.gold_revenue_share == 0.80
        assert config.silver_revenue_share == 0.75
        assert config.bronze_revenue_share == 0.70
        assert config.minimum_payout == 5.0
        assert config.reporting_period_days == 7


class TestAdapterRevenue:
    """Test cases for AdapterRevenue dataclass."""

    def test_adapter_revenue_creation(self):
        """Test AdapterRevenue dataclass creation."""
        revenue = AdapterRevenue(
            adapter_id="adapter-001",
            adapter_name="Test Adapter",
            qos_level="gold",
            total_cost=1000.0,
            revenue_share=700.0,
            payout_amount=700.0,
            transaction_count=100,
        )

        assert revenue.adapter_id == "adapter-001"
        assert revenue.adapter_name == "Test Adapter"
        assert revenue.qos_level == "gold"
        assert revenue.total_cost == 1000.0
        assert revenue.revenue_share == 700.0
        assert revenue.payout_amount == 700.0
        assert revenue.transaction_count == 100
