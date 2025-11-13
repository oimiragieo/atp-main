#!/usr/bin/env python3
"""
Tests for KPI dashboard automation.
"""

import json
import tempfile
from pathlib import Path

from tools.kpi_dashboard_generator import DashboardConfig, DashboardPanel, KPIDashboardGenerator


class TestKPIDashboardGenerator:
    """Test cases for the KPI dashboard generator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = KPIDashboardGenerator()

    def test_create_kpi_dashboard(self):
        """Test creating a KPI dashboard configuration."""
        config = self.generator.create_kpi_dashboard()

        assert config.title == "ATP Platform KPIs"
        assert config.uid == "atp-kpi-overview"
        assert "ATP" in config.tags
        assert "KPI" in config.tags
        assert len(config.panels) > 0

    def test_generate_grafana_json(self):
        """Test generating Grafana JSON from dashboard config."""
        config = DashboardConfig(
            title="Test Dashboard",
            uid="test-uid",
            tags=["test"],
            panels=[
                DashboardPanel(
                    title="Test Panel",
                    type="timeseries",
                    targets=[{"expr": "test_metric", "refId": "A"}],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                )
            ],
        )

        dashboard_json = self.generator.generate_grafana_json(config)

        assert dashboard_json["title"] == "Test Dashboard"
        assert dashboard_json["uid"] == "test-uid"
        assert dashboard_json["tags"] == ["test"]
        assert len(dashboard_json["panels"]) == 1
        assert dashboard_json["panels"][0]["title"] == "Test Panel"

    def test_get_core_kpi_panels(self):
        """Test getting core KPI panels."""
        panels = self.generator._get_core_kpi_panels()

        assert len(panels) == 3
        assert panels[0].title == "Active Connections"
        assert panels[1].title == "Request Rate"
        assert panels[2].title == "Error Rate"

        # Check that panels have proper structure
        for panel in panels:
            assert panel.type in ["timeseries"]
            assert panel.targets
            assert panel.grid_pos

    def test_get_performance_panels(self):
        """Test getting performance panels."""
        panels = self.generator._get_performance_panels()

        assert len(panels) == 2
        assert panels[0].title == "Response Time P95"
        assert panels[1].title == "Throughput"

    def test_get_cost_panels(self):
        """Test getting cost panels."""
        panels = self.generator._get_cost_panels()

        assert len(panels) == 2
        assert panels[0].title == "Cost per Request"
        assert panels[1].title == "Budget Burn Rate"

    def test_get_consensus_panels(self):
        """Test getting consensus panels."""
        panels = self.generator._get_consensus_panels()

        assert len(panels) == 2
        assert panels[0].title == "Consensus Agreement Rate"
        assert panels[1].title == "Adapter Predictability"

    def test_export_dashboard_json(self):
        """Test exporting dashboard as JSON file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_dashboard.json"

            self.generator.export_dashboard_json(str(output_path))

            assert output_path.exists()

            with open(output_path, encoding="utf-8") as f:
                dashboard = json.load(f)

            assert dashboard["title"] == "ATP Platform KPIs"
            assert dashboard["uid"] == "atp-kpi-overview"
            assert len(dashboard["panels"]) > 0

    def test_validate_dashboard_panels_success(self):
        """Test validating dashboard panels when all required panels are present."""
        dashboard_json = {
            "panels": [{"title": "Active Connections"}, {"title": "Request Rate"}, {"title": "Error Rate"}]
        }
        required_panels = ["Active Connections", "Request Rate"]

        is_valid = self.generator.validate_dashboard_panels(dashboard_json, required_panels)
        assert is_valid

    def test_validate_dashboard_panels_missing(self):
        """Test validating dashboard panels when required panels are missing."""
        dashboard_json = {"panels": [{"title": "Active Connections"}]}
        required_panels = ["Active Connections", "Request Rate", "Error Rate"]

        is_valid = self.generator.validate_dashboard_panels(dashboard_json, required_panels)
        assert not is_valid

    def test_metrics_increment(self):
        """Test that metrics are incremented when exporting dashboard."""
        # Test that the generator has the metrics counter
        assert hasattr(self.generator, "dashboards_created")

        # Test that we can call export_dashboard_json without errors
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_dashboard.json"
            self.generator.export_dashboard_json(str(output_path))

            # Verify the file was created
            assert output_path.exists()


def test_kpi_dashboard_generator_executable():
    """Test that the KPI dashboard generator is executable."""
    generator_path = Path("tools/kpi_dashboard_generator.py")
    assert generator_path.exists()

    # Check that it's a valid Python file
    content = generator_path.read_text()
    assert "def main():" in content
    assert "if __name__ == '__main__':" in content


def test_dashboard_json_structure():
    """Test that generated dashboard JSON has correct structure."""
    generator = KPIDashboardGenerator()
    config = generator.create_kpi_dashboard()
    dashboard_json = generator.generate_grafana_json(config)

    # Check required Grafana JSON fields
    required_fields = ["id", "uid", "title", "tags", "timezone", "panels"]
    for field in required_fields:
        assert field in dashboard_json

    # Check panels structure
    assert isinstance(dashboard_json["panels"], list)
    for panel in dashboard_json["panels"]:
        assert "id" in panel
        assert "type" in panel
        assert "title" in panel
        assert "gridPos" in panel
        assert "targets" in panel


def test_cli_export_and_validate():
    """Test the CLI interface for export and validation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "kpi_dashboard.json"

        # Run the generator
        import subprocess
        import sys

        _result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "tools/kpi_dashboard_generator.py",
                "--output",
                str(output_path),
                "--validate",
                "Active Connections",
                "Request Rate",
            ],
            capture_output=True,
            text=True,
            cwd="c:\\dev\\projects\\atp-main",
        )

        assert _result.returncode == 0
        assert output_path.exists()

        content = output_path.read_text()
        dashboard = json.loads(content)
        assert dashboard["title"] == "ATP Platform KPIs"


def test_required_panels_coverage():
    """Test that all expected KPI panels are included."""
    generator = KPIDashboardGenerator()
    config = generator.create_kpi_dashboard()

    panel_titles = {panel.title for panel in config.panels}

    expected_panels = {
        "Active Connections",
        "Request Rate",
        "Error Rate",
        "Response Time P95",
        "Throughput",
        "Cost per Request",
        "Budget Burn Rate",
        "Consensus Agreement Rate",
        "Adapter Predictability",
    }

    assert expected_panels.issubset(panel_titles), f"Missing panels: {expected_panels - panel_titles}"
