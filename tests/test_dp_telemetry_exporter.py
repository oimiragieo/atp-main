"""
Tests for GAP-271: DP Telemetry Exporter.
"""

import csv
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from tools.dp_telemetry_exporter import (
    DpTelemetryEvent,
    DpTelemetryExporter,
    ExportFormat,
    get_dp_telemetry_exporter,
    initialize_dp_telemetry_exporter,
)


class TestDpTelemetryExporter:
    """Test cases for the DP telemetry exporter."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for exports."""
        temp_path = tempfile.mkdtemp()
        yield Path(temp_path)
        shutil.rmtree(temp_path)

    @pytest.fixture
    def exporter(self, temp_dir):
        """Create a test exporter instance."""
        return DpTelemetryExporter(export_path=str(temp_dir), max_epsilon_per_tenant=2.0)

    @pytest.fixture
    def sample_events(self):
        """Create sample DP telemetry events."""
        return [
            DpTelemetryEvent(
                event_id="evt_001",
                event_type="request_count",
                tenant_id="tenant1",
                timestamp=datetime.now(),
                dp_value=95.2,
                epsilon_used=0.1,
                sensitivity=1.0,
                raw_value=100,
                metadata={"endpoint": "/api/v1"},
            ),
            DpTelemetryEvent(
                event_id="evt_002",
                event_type="latency_ms",
                tenant_id="tenant1",
                timestamp=datetime.now(),
                dp_value=245.8,
                epsilon_used=0.2,
                sensitivity=10.0,
                raw_value=250,
                metadata={"method": "GET"},
            ),
            DpTelemetryEvent(
                event_id="evt_003",
                event_type="error_rate",
                tenant_id="tenant2",
                timestamp=datetime.now(),
                dp_value=0.025,
                epsilon_used=0.05,
                sensitivity=0.1,
                raw_value=0.02,
                metadata={"status_code": "500"},
            ),
        ]

    def test_add_event_within_budget(self, exporter, sample_events):
        """Test adding events within privacy budget."""
        event = sample_events[0]

        # Should succeed within budget
        assert exporter.add_event(event)
        assert event.tenant_id in exporter.tenant_epsilon_usage
        assert exporter.tenant_epsilon_usage[event.tenant_id] == event.epsilon_used

    def test_add_event_exceeds_budget(self, exporter):
        """Test rejecting events that exceed privacy budget."""
        # Add event that uses most of the budget
        event1 = DpTelemetryEvent(
            event_id="evt_001",
            event_type="test",
            tenant_id="tenant1",
            timestamp=datetime.now(),
            dp_value=100.0,
            epsilon_used=1.8,
            sensitivity=1.0,
        )

        assert exporter.add_event(event1)
        assert exporter.tenant_epsilon_usage["tenant1"] == 1.8

        # Try to add event that would exceed budget
        event2 = DpTelemetryEvent(
            event_id="evt_002",
            event_type="test",
            tenant_id="tenant1",
            timestamp=datetime.now(),
            dp_value=200.0,
            epsilon_used=0.3,  # 1.8 + 0.3 = 2.1 > 2.0 limit
            sensitivity=1.0,
        )

        assert not exporter.add_event(event2)
        assert len(exporter.pending_events) == 1  # Only first event added

    def test_export_json(self, exporter, sample_events, temp_dir):
        """Test JSON export format."""
        # Add events
        for event in sample_events:
            exporter.add_event(event)

        # Export to JSON
        filepath = exporter.export_batch(ExportFormat.JSON)

        # Verify file was created
        assert Path(filepath).exists()

        # Verify file contents
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        assert "export_timestamp" in data
        assert data["total_events"] == 3
        assert len(data["events"]) == 3

        # Verify event data (should not include raw_value)
        event_data = data["events"][0]
        assert "event_id" in event_data
        assert "dp_value" in event_data
        assert "raw_value" not in event_data  # Raw values should be excluded
        assert event_data["tenant_id"] == "tenant1"

    def test_export_csv(self, exporter, sample_events, temp_dir):
        """Test CSV export format."""
        # Add events
        for event in sample_events:
            exporter.add_event(event)

        # Export to CSV
        filepath = exporter.export_batch(ExportFormat.CSV)

        # Verify file was created
        assert Path(filepath).exists()

        # Verify file contents
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        assert rows[0]["event_id"] == "evt_001"
        assert rows[0]["tenant_id"] == "tenant1"
        assert float(rows[0]["dp_value"]) == 95.2

    def test_export_prometheus(self, exporter, sample_events, temp_dir):
        """Test Prometheus export format."""
        # Add events
        for event in sample_events:
            exporter.add_event(event)

        # Export to Prometheus
        filepath = exporter.export_batch(ExportFormat.PROMETHEUS)

        # Verify file was created
        assert Path(filepath).exists()

        # Verify file contents
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        assert "# DP Telemetry Export" in content
        assert "dp_telemetry_request_count" in content
        assert "dp_telemetry_latency_ms" in content
        assert "dp_telemetry_error_rate" in content

    def test_empty_export(self, exporter):
        """Test exporting when no events are pending."""
        # Should not fail with empty export
        filepath = exporter.export_batch(ExportFormat.JSON)
        assert filepath == ""  # Empty string returned for no events

    def test_budget_status(self, exporter, sample_events):
        """Test getting budget status for tenants."""
        # Add some events
        exporter.add_event(sample_events[0])  # 0.1 epsilon
        exporter.add_event(sample_events[1])  # 0.2 epsilon, same tenant

        status = exporter.get_budget_status("tenant1")

        assert status["tenant_id"] == "tenant1"
        assert status["epsilon_used"] == pytest.approx(0.3, rel=1e-10)
        assert status["epsilon_remaining"] == pytest.approx(1.7, rel=1e-10)
        assert status["epsilon_limit"] == 2.0
        assert abs(status["utilization_rate"] - 0.15) < 0.001

    def test_budget_status_unknown_tenant(self, exporter):
        """Test budget status for tenant with no usage."""
        status = exporter.get_budget_status("unknown_tenant")

        assert status["epsilon_used"] == 0.0
        assert status["epsilon_remaining"] == 2.0

    def test_reset_budget(self, exporter, sample_events):
        """Test resetting privacy budget for a tenant."""
        # Add event
        exporter.add_event(sample_events[0])
        assert exporter.tenant_epsilon_usage["tenant1"] == 0.1

        # Reset budget
        exporter.reset_budget("tenant1")
        assert "tenant1" not in exporter.tenant_epsilon_usage

    def test_event_to_dict(self, sample_events):
        """Test converting event to dictionary."""
        event = sample_events[0]

        # Without raw value
        data = event.to_dict(include_raw=False)
        assert "raw_value" not in data
        assert data["event_id"] == "evt_001"
        assert data["dp_value"] == 95.2

        # With raw value
        data_with_raw = event.to_dict(include_raw=True)
        assert "raw_value" in data_with_raw
        assert data_with_raw["raw_value"] == 100

    def test_global_exporter(self, temp_dir):
        """Test global exporter management."""
        # Initially should be None
        assert get_dp_telemetry_exporter() is None

        # Initialize
        exporter = initialize_dp_telemetry_exporter(str(temp_dir))
        assert get_dp_telemetry_exporter() is exporter

    def test_export_format_enum(self):
        """Test export format enum values."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.CSV.value == "csv"
        assert ExportFormat.PROMETHEUS.value == "prometheus"

    def test_invalid_export_format(self, exporter):
        """Test error handling for invalid export format."""
        exporter.add_event(
            DpTelemetryEvent(
                event_id="test",
                event_type="test",
                tenant_id="test",
                timestamp=datetime.now(),
                dp_value=1.0,
                epsilon_used=0.1,
                sensitivity=1.0,
            )
        )

        with pytest.raises(ValueError, match="Unsupported export format"):
            exporter.export_batch("invalid_format")

    def test_different_tenants_budget_tracking(self, exporter):
        """Test that different tenants have separate budget tracking."""
        event1 = DpTelemetryEvent(
            event_id="evt1",
            event_type="test",
            tenant_id="tenant1",
            timestamp=datetime.now(),
            dp_value=1.0,
            epsilon_used=0.5,
            sensitivity=1.0,
        )

        event2 = DpTelemetryEvent(
            event_id="evt2",
            event_type="test",
            tenant_id="tenant2",
            timestamp=datetime.now(),
            dp_value=2.0,
            epsilon_used=0.7,
            sensitivity=1.0,
        )

        exporter.add_event(event1)
        exporter.add_event(event2)

        assert exporter.tenant_epsilon_usage["tenant1"] == 0.5
        assert exporter.tenant_epsilon_usage["tenant2"] == 0.7

    def test_export_clears_pending_events(self, exporter, sample_events):
        """Test that export clears pending events."""
        # Add events
        for event in sample_events:
            exporter.add_event(event)

        assert len(exporter.pending_events) == 3

        # Export
        exporter.export_batch(ExportFormat.JSON)

        # Should be cleared
        assert len(exporter.pending_events) == 0
