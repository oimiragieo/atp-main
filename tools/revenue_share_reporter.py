#!/usr/bin/env python3
"""
Revenue Share Reporting Export Tool

Generates revenue share reports for adapter providers based on usage and cost data.
Calculates revenue shares and exports reports for payout processing.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from metrics.registry import REGISTRY
from router_service.cost_aggregator import GLOBAL_COST


@dataclass
class RevenueShareConfig:
    """Configuration for revenue share calculations."""

    gold_revenue_share: float = 0.70  # 70% to adapter provider
    silver_revenue_share: float = 0.65  # 65% to adapter provider
    bronze_revenue_share: float = 0.60  # 60% to adapter provider
    minimum_payout: float = 10.0  # Minimum payout threshold
    reporting_period_days: int = 30


@dataclass
class AdapterRevenue:
    """Revenue data for a specific adapter."""

    adapter_id: str
    adapter_name: str
    qos_level: str
    total_cost: float
    revenue_share: float
    payout_amount: float
    transaction_count: int


class RevenueShareReporter:
    """Generates revenue share reports for adapter providers."""

    def __init__(self, config: RevenueShareConfig | None = None):
        self.config = config or RevenueShareConfig()
        self.revenue_share_payouts = REGISTRY.counter("revenue_share_payouts")

    def calculate_revenue_shares(
        self, cost_snapshot: dict[str, float], adapter_costs: dict[str, dict[str, float]]
    ) -> list[AdapterRevenue]:
        """Calculate revenue shares for all adapters based on cost data."""
        revenue_data = []

        # Mock adapter data - in real implementation, this would come from adapter registry
        adapters = self._get_adapter_data()

        for adapter in adapters:
            adapter_id = adapter["id"]
            qos = adapter["qos_level"].lower()

            # Get cost for this specific adapter
            total_cost = 0.0
            if adapter_id in adapter_costs and qos in adapter_costs[adapter_id]:
                total_cost = adapter_costs[adapter_id][qos]

            revenue_share_rate = self._get_revenue_share_rate(qos)
            revenue_share = total_cost * revenue_share_rate
            payout_amount = max(revenue_share, self.config.minimum_payout) if revenue_share > 0 else 0

            revenue_data.append(
                AdapterRevenue(
                    adapter_id=adapter_id,
                    adapter_name=adapter["name"],
                    qos_level=qos,
                    total_cost=total_cost,
                    revenue_share=revenue_share,
                    payout_amount=payout_amount,
                    transaction_count=adapter.get("transaction_count", 0),
                )
            )

        return revenue_data

    def _get_adapter_data(self) -> list[dict[str, Any]]:
        """Get adapter data (mock implementation)."""
        # In real implementation, this would query the adapter registry/database
        return [
            {"id": "adapter-001", "name": "OpenAI GPT-4", "qos_level": "gold", "transaction_count": 1500},
            {"id": "adapter-002", "name": "Anthropic Claude", "qos_level": "gold", "transaction_count": 1200},
            {"id": "adapter-003", "name": "Google Gemini", "qos_level": "silver", "transaction_count": 800},
            {"id": "adapter-004", "name": "Meta Llama", "qos_level": "bronze", "transaction_count": 600},
        ]

    def _get_revenue_share_rate(self, qos: str) -> float:
        """Get revenue share rate for QoS level."""
        rates = {
            "gold": self.config.gold_revenue_share,
            "silver": self.config.silver_revenue_share,
            "bronze": self.config.bronze_revenue_share,
        }
        return rates.get(qos, 0.0)

    def generate_report(self, output_path: str, report_format: str = "json") -> None:
        """Generate revenue share report."""
        # Get current cost snapshot
        cost_snapshot = GLOBAL_COST.snapshot()
        adapter_costs = GLOBAL_COST.snapshot_by_adapter()

        # Calculate revenue shares
        revenue_data = self.calculate_revenue_shares(cost_snapshot, adapter_costs)

        # Generate report based on format
        if report_format == "json":
            self._export_json_report(revenue_data, output_path)
        elif report_format == "csv":
            self._export_csv_report(revenue_data, output_path)
        else:
            raise ValueError(f"Unsupported format: {report_format}")

        # Update metrics
        total_payouts = sum(r.payout_amount for r in revenue_data)
        self.revenue_share_payouts.inc(int(total_payouts * 100))  # Store in cents

        print(f"Revenue share report generated: {output_path}")
        print(f"Total payouts: ${total_payouts:.2f}")
        print(f"Adapters processed: {len(revenue_data)}")

    def _export_json_report(self, revenue_data: list[AdapterRevenue], output_path: str) -> None:
        """Export revenue report as JSON."""
        report = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "reporting_period_days": self.config.reporting_period_days,
                "revenue_share_config": {
                    "gold_rate": self.config.gold_revenue_share,
                    "silver_rate": self.config.silver_revenue_share,
                    "bronze_rate": self.config.bronze_revenue_share,
                    "minimum_payout": self.config.minimum_payout,
                },
            },
            "revenue_data": [
                {
                    "adapter_id": r.adapter_id,
                    "adapter_name": r.adapter_name,
                    "qos_level": r.qos_level,
                    "total_cost": round(r.total_cost, 2),
                    "revenue_share": round(r.revenue_share, 2),
                    "payout_amount": round(r.payout_amount, 2),
                    "transaction_count": r.transaction_count,
                }
                for r in revenue_data
            ],
            "summary": {
                "total_adapters": len(revenue_data),
                "total_cost": round(sum(r.total_cost for r in revenue_data), 2),
                "total_payouts": round(sum(r.payout_amount for r in revenue_data), 2),
                "platform_revenue": round(sum(r.total_cost - r.revenue_share for r in revenue_data), 2),
            },
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    def _export_csv_report(self, revenue_data: list[AdapterRevenue], output_path: str) -> None:
        """Export revenue report as CSV."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Adapter ID",
                    "Adapter Name",
                    "QoS Level",
                    "Total Cost",
                    "Revenue Share",
                    "Payout Amount",
                    "Transaction Count",
                ]
            )

            for revenue in revenue_data:
                writer.writerow(
                    [
                        revenue.adapter_id,
                        revenue.adapter_name,
                        revenue.qos_level,
                        f"{revenue.total_cost:.2f}",
                        f"{revenue.revenue_share:.2f}",
                        f"{revenue.payout_amount:.2f}",
                        revenue.transaction_count,
                    ]
                )

    def validate_revenue_calculations(self, revenue_data: list[AdapterRevenue]) -> bool:
        """Validate revenue share calculations."""
        for revenue in revenue_data:
            expected_share = revenue.total_cost * self._get_revenue_share_rate(revenue.qos_level)
            if abs(revenue.revenue_share - expected_share) > 0.01:  # Allow for small floating point differences
                print(
                    f"Validation failed for {revenue.adapter_name}: expected {expected_share}, got {revenue.revenue_share}"
                )
                return False

            if revenue.payout_amount < 0:
                print(f"Invalid payout amount for {revenue.adapter_name}: {revenue.payout_amount}")
                return False

        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate revenue share reports")
    parser.add_argument("--output", required=True, help="Output path for report")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Report format")
    parser.add_argument("--validate", action="store_true", help="Validate calculations after generation")

    args = parser.parse_args()

    reporter = RevenueShareReporter()
    reporter.generate_report(args.output, args.format)

    if args.validate:
        # Load and validate the generated report
        if args.format == "json":
            with open(args.output, encoding="utf-8") as f:
                report = json.load(f)
                revenue_data = [AdapterRevenue(**item) for item in report["revenue_data"]]
        else:
            # CSV validation would require parsing, skip for now
            print("CSV validation not implemented")
            return

        if reporter.validate_revenue_calculations(revenue_data):
            print("✅ Revenue calculations validated successfully")
        else:
            print("❌ Revenue calculation validation failed")
            exit(1)


if __name__ == "__main__":
    main()
