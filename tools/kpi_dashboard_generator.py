#!/usr/bin/env python3
"""
KPI Dashboard Automation Tool

Automates the creation and validation of KPI dashboards for the ATP platform.
Generates Grafana dashboard JSON and validates required panels are present.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from metrics.registry import REGISTRY
except ImportError:
    # Mock registry for testing
    class MockRegistry:
        def counter(self, name):
            return MockCounter()

    class MockCounter:
        def inc(self, amount=1):
            pass

    REGISTRY = MockRegistry()


@dataclass
class DashboardPanel:
    """Represents a Grafana dashboard panel."""

    title: str
    type: str
    targets: list[dict[str, Any]]
    grid_pos: dict[str, int]
    description: str | None = None


@dataclass
class DashboardConfig:
    """Configuration for a KPI dashboard."""

    title: str
    uid: str
    tags: list[str]
    refresh: str = "30s"
    panels: list[DashboardPanel] = None

    def __post_init__(self):
        if self.panels is None:
            self.panels = []


class KPIDashboardGenerator:
    """Generates KPI dashboards for ATP platform monitoring."""

    def __init__(self):
        self.dashboards_created = REGISTRY.counter("kpi_dashboards_created")

    def create_kpi_dashboard(self) -> DashboardConfig:
        """Create a comprehensive KPI dashboard configuration."""
        config = DashboardConfig(
            title="ATP Platform KPIs", uid="atp-kpi-overview", tags=["ATP", "KPI", "Platform"], panels=[]
        )

        # Add core KPI panels
        config.panels.extend(self._get_core_kpi_panels())
        config.panels.extend(self._get_performance_panels())
        config.panels.extend(self._get_cost_panels())
        config.panels.extend(self._get_consensus_panels())

        return config

    def _get_core_kpi_panels(self) -> list[DashboardPanel]:
        """Get core platform KPI panels."""
        return [
            DashboardPanel(
                title="Active Connections",
                type="timeseries",
                targets=[{"expr": "sum(router_active_connections)", "legendFormat": "Connections", "refId": "A"}],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                description="Current active connections to the ATP router",
            ),
            DashboardPanel(
                title="Request Rate",
                type="timeseries",
                targets=[
                    {"expr": "sum(rate(router_requests_total[5m]))", "legendFormat": "Requests/sec", "refId": "A"}
                ],
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
                description="Request rate over the last 5 minutes",
            ),
            DashboardPanel(
                title="Error Rate",
                type="timeseries",
                targets=[
                    {
                        "expr": "sum(rate(router_errors_total[5m])) / sum(rate(router_requests_total[5m])) * 100",
                        "legendFormat": "Error %",
                        "refId": "A",
                    }
                ],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 8},
                description="Error rate as percentage of total requests",
            ),
        ]

    def _get_performance_panels(self) -> list[DashboardPanel]:
        """Get performance-related KPI panels."""
        return [
            DashboardPanel(
                title="Response Time P95",
                type="timeseries",
                targets=[
                    {
                        "expr": "histogram_quantile(0.95, sum(rate(router_request_duration_seconds_bucket[5m])) by (le))",
                        "legendFormat": "P95",
                        "refId": "A",
                    }
                ],
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 8},
                description="95th percentile response time",
            ),
            DashboardPanel(
                title="Throughput",
                type="timeseries",
                targets=[{"expr": "sum(rate(router_requests_total[5m]))", "legendFormat": "Throughput", "refId": "A"}],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 16},
                description="System throughput in requests per second",
            ),
        ]

    def _get_cost_panels(self) -> list[DashboardPanel]:
        """Get cost-related KPI panels."""
        return [
            DashboardPanel(
                title="Cost per Request",
                type="timeseries",
                targets=[
                    {
                        "expr": "sum(rate(cost_total_usd[5m])) / sum(rate(router_requests_total[5m]))",
                        "legendFormat": "Cost/USD",
                        "refId": "A",
                    }
                ],
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 16},
                description="Average cost per request in USD",
            ),
            DashboardPanel(
                title="Budget Burn Rate",
                type="timeseries",
                targets=[{"expr": "sum(rate(cost_total_usd[1h])) * 24", "legendFormat": "Daily Burn", "refId": "A"}],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 24},
                description="Daily budget burn rate in USD",
            ),
        ]

    def _get_consensus_panels(self) -> list[DashboardPanel]:
        """Get consensus-related KPI panels."""
        return [
            DashboardPanel(
                title="Consensus Agreement Rate",
                type="timeseries",
                targets=[
                    {
                        "expr": "histogram_quantile(0.5, sum(rate(agreement_pct_bucket[5m])) by (le))",
                        "legendFormat": "Agreement %",
                        "refId": "A",
                    }
                ],
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 24},
                description="Median consensus agreement percentage",
            ),
            DashboardPanel(
                title="Adapter Predictability",
                type="barchart",
                targets=[
                    {
                        "expr": "sum(rate(adapter_predictability_score[5m])) by (adapter)",
                        "legendFormat": "{{adapter}}",
                        "refId": "A",
                    }
                ],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 32},
                description="Predictability scores by adapter",
            ),
        ]

    def generate_grafana_json(self, config: DashboardConfig) -> dict[str, Any]:
        """Generate Grafana dashboard JSON from configuration."""
        dashboard = {
            "id": None,
            "uid": config.uid,
            "title": config.title,
            "tags": config.tags,
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 1,
            "refresh": config.refresh,
            "time": {"from": "now-1h", "to": "now"},
            "panels": [],
        }

        for i, panel in enumerate(config.panels):
            panel_json = {
                "id": i + 1,
                "type": panel.type,
                "title": panel.title,
                "gridPos": panel.grid_pos,
                "targets": panel.targets,
            }
            if panel.description:
                panel_json["description"] = panel.description

            dashboard["panels"].append(panel_json)

        return dashboard

    def export_dashboard_json(self, output_path: str) -> None:
        """Export KPI dashboard as JSON file."""
        config = self.create_kpi_dashboard()
        dashboard_json = self.generate_grafana_json(config)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dashboard_json, f, indent=2)

        # Increment metrics
        self.dashboards_created.inc()

        print(f"KPI dashboard exported to: {output_file}")

    def validate_dashboard_panels(self, dashboard_json: dict[str, Any], required_panels: list[str]) -> bool:
        """Validate that required panels are present in dashboard."""
        present_panels = {panel["title"] for panel in dashboard_json.get("panels", [])}
        missing_panels = set(required_panels) - present_panels

        if missing_panels:
            print(f"Missing required panels: {missing_panels}")
            return False

        print(f"All required panels present: {required_panels}")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate KPI dashboards")
    parser.add_argument("--output", required=True, help="Output path for dashboard JSON")
    parser.add_argument("--validate", nargs="*", help="Validate presence of specified panels")

    args = parser.parse_args()

    generator = KPIDashboardGenerator()
    generator.export_dashboard_json(args.output)

    if args.validate:
        # Load and validate the generated dashboard
        with open(args.output, encoding="utf-8") as f:
            dashboard = json.load(f)

        is_valid = generator.validate_dashboard_panels(dashboard, args.validate)
        if not is_valid:
            exit(1)


if __name__ == "__main__":
    main()
