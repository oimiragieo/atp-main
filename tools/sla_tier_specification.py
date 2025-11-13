#!/usr/bin/env python3
"""SLA Tier Specification & SLO Targets Tool.

This tool implements a comprehensive Service Level Agreement (SLA) tier system
with Service Level Objectives (SLOs) and Service Level Indicators (SLIs).
It defines latency, availability, and error budgets per tier with automated
alert configuration generation.

Usage:
    python sla_tier_specification.py --help
"""

import argparse
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

# Optional imports for metrics integration
try:
    from metrics import SLO_BREACH_EVENTS_TOTAL
except ImportError:
    SLO_BREACH_EVENTS_TOTAL = None


class ServiceTier(Enum):
    """Service tier definitions with associated priorities."""
    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    BASIC = "basic"


@dataclass
class SLITargets:
    """Service Level Indicator targets for a tier."""
    latency_p50_ms: float  # 50th percentile latency
    latency_p95_ms: float  # 95th percentile latency
    latency_p99_ms: float  # 99th percentile latency
    availability_pct: float  # Uptime percentage (99.9, 99.95, etc.)
    error_budget_pct: float  # Maximum error rate percentage
    throughput_qps: int  # Minimum throughput requirement


@dataclass
class SLODefinition:
    """Service Level Objective definition with compliance windows."""
    sli_targets: SLITargets
    compliance_window_days: int  # Rolling window for SLO measurement
    alert_threshold_pct: float  # When to trigger alerts (e.g., 0.8 for 80%)
    burn_rate_threshold: float  # Error budget burn rate threshold


@dataclass
class AlertConfiguration:
    """Alert configuration for SLO breaches."""
    alert_name: str
    condition: str
    severity: str
    description: str
    runbook_url: Optional[str] = None
    labels: Optional[dict[str, str]] = None


@dataclass
class SLATier:
    """Complete SLA tier specification."""
    tier: ServiceTier
    slo_definition: SLODefinition
    pricing_multiplier: float  # Cost multiplier relative to basic tier
    concurrency_limit: int  # Maximum concurrent requests
    rate_limit_qps: int  # Rate limit per second
    support_sla_hours: int  # Support response time in hours
    data_retention_days: int  # Data retention period
    custom_features: list[str]  # Tier-specific features


class SLATierSpecification:
    """Main class for SLA tier specification and SLO management."""

    def __init__(self):
        self.tiers: dict[ServiceTier, SLATier] = {}
        self._initialize_default_tiers()

    def _initialize_default_tiers(self):
        """Initialize default SLA tier specifications."""

        # Platinum Tier - Highest performance and availability
        platinum_sli = SLITargets(
            latency_p50_ms=50,
            latency_p95_ms=100,
            latency_p99_ms=200,
            availability_pct=99.99,  # 52.56 minutes downtime/year
            error_budget_pct=0.01,   # 99.99% success rate
            throughput_qps=10000
        )
        platinum_slo = SLODefinition(
            sli_targets=platinum_sli,
            compliance_window_days=30,
            alert_threshold_pct=0.95,
            burn_rate_threshold=2.0
        )
        self.tiers[ServiceTier.PLATINUM] = SLATier(
            tier=ServiceTier.PLATINUM,
            slo_definition=platinum_slo,
            pricing_multiplier=5.0,
            concurrency_limit=1000,
            rate_limit_qps=5000,
            support_sla_hours=1,
            data_retention_days=365,
            custom_features=[
                "Dedicated infrastructure",
                "24/7 premium support",
                "Custom SLAs",
                "Advanced analytics",
                "Priority feature requests"
            ]
        )

        # Gold Tier - High performance and availability
        gold_sli = SLITargets(
            latency_p50_ms=75,
            latency_p95_ms=150,
            latency_p99_ms=300,
            availability_pct=99.95,  # 4.38 hours downtime/year
            error_budget_pct=0.05,   # 99.95% success rate
            throughput_qps=5000
        )
        gold_slo = SLODefinition(
            sli_targets=gold_sli,
            compliance_window_days=30,
            alert_threshold_pct=0.90,
            burn_rate_threshold=1.5
        )
        self.tiers[ServiceTier.GOLD] = SLATier(
            tier=ServiceTier.GOLD,
            slo_definition=gold_slo,
            pricing_multiplier=3.0,
            concurrency_limit=500,
            rate_limit_qps=2000,
            support_sla_hours=4,
            data_retention_days=180,
            custom_features=[
                "High availability",
                "Business hours support",
                "Enhanced monitoring",
                "Priority queuing"
            ]
        )

        # Silver Tier - Standard performance and availability
        silver_sli = SLITargets(
            latency_p50_ms=100,
            latency_p95_ms=250,
            latency_p99_ms=500,
            availability_pct=99.9,   # 8.77 hours downtime/year
            error_budget_pct=0.1,    # 99.9% success rate
            throughput_qps=2000
        )
        silver_slo = SLODefinition(
            sli_targets=silver_sli,
            compliance_window_days=30,
            alert_threshold_pct=0.85,
            burn_rate_threshold=1.2
        )
        self.tiers[ServiceTier.SILVER] = SLATier(
            tier=ServiceTier.SILVER,
            slo_definition=silver_slo,
            pricing_multiplier=2.0,
            concurrency_limit=200,
            rate_limit_qps=1000,
            support_sla_hours=12,
            data_retention_days=90,
            custom_features=[
                "Standard availability",
                "Email support",
                "Basic monitoring"
            ]
        )

        # Bronze Tier - Basic performance and availability
        bronze_sli = SLITargets(
            latency_p50_ms=150,
            latency_p95_ms=400,
            latency_p99_ms=800,
            availability_pct=99.5,   # 1.83 days downtime/year
            error_budget_pct=0.5,    # 99.5% success rate
            throughput_qps=1000
        )
        bronze_slo = SLODefinition(
            sli_targets=bronze_sli,
            compliance_window_days=30,
            alert_threshold_pct=0.80,
            burn_rate_threshold=1.0
        )
        self.tiers[ServiceTier.BRONZE] = SLATier(
            tier=ServiceTier.BRONZE,
            slo_definition=bronze_slo,
            pricing_multiplier=1.5,
            concurrency_limit=100,
            rate_limit_qps=500,
            support_sla_hours=24,
            data_retention_days=30,
            custom_features=[
                "Basic availability",
                "Community support",
                "Limited monitoring"
            ]
        )

        # Basic Tier - Entry level service
        basic_sli = SLITargets(
            latency_p50_ms=250,
            latency_p95_ms=750,
            latency_p99_ms=1500,
            availability_pct=99.0,   # 3.65 days downtime/year
            error_budget_pct=1.0,    # 99.0% success rate
            throughput_qps=500
        )
        basic_slo = SLODefinition(
            sli_targets=basic_sli,
            compliance_window_days=30,
            alert_threshold_pct=0.75,
            burn_rate_threshold=0.8
        )
        self.tiers[ServiceTier.BASIC] = SLATier(
            tier=ServiceTier.BASIC,
            slo_definition=basic_slo,
            pricing_multiplier=1.0,
            concurrency_limit=50,
            rate_limit_qps=200,
            support_sla_hours=72,
            data_retention_days=7,
            custom_features=[
                "Best effort availability",
                "Community support only",
                "Minimal monitoring"
            ]
        )

    def get_tier(self, tier: ServiceTier) -> SLATier:
        """Get SLA tier specification."""
        if tier not in self.tiers:
            raise ValueError(f"Tier {tier.value} not found")
        return self.tiers[tier]

    def generate_alert_configurations(self, tier: ServiceTier) -> list[AlertConfiguration]:
        """Generate Prometheus alert configurations for a tier."""
        sla_tier = self.get_tier(tier)
        slo = sla_tier.slo_definition
        sli = slo.sli_targets

        alerts = []

        # Latency P95 alert
        alerts.append(AlertConfiguration(
            alert_name=f"SLO_Latency_P95_{tier.value.title()}",
            condition=f"""http_request_duration_seconds{{quantile="0.95",tier="{tier.value}"}} > {sli.latency_p95_ms / 1000}""",
            severity="warning",
            description=f"P95 latency for {tier.value} tier exceeds SLO target of {sli.latency_p95_ms}ms",
            labels={"tier": tier.value, "slo_type": "latency_p95"}
        ))

        # Latency P99 alert
        alerts.append(AlertConfiguration(
            alert_name=f"SLO_Latency_P99_{tier.value.title()}",
            condition=f"""http_request_duration_seconds{{quantile="0.99",tier="{tier.value}"}} > {sli.latency_p99_ms / 1000}""",
            severity="critical",
            description=f"P99 latency for {tier.value} tier exceeds SLO target of {sli.latency_p99_ms}ms",
            labels={"tier": tier.value, "slo_type": "latency_p99"}
        ))

        # Error rate alert
        alerts.append(AlertConfiguration(
            alert_name=f"SLO_Error_Rate_{tier.value.title()}",
            condition=f"""rate(http_requests_total{{status=~"5..",tier="{tier.value}"}}[5m]) / rate(http_requests_total{{tier="{tier.value}"}}[5m]) > {sli.error_budget_pct / 100}""",
            severity="critical",
            description=f"Error rate for {tier.value} tier exceeds SLO target of {sli.error_budget_pct}%",
            labels={"tier": tier.value, "slo_type": "error_rate"}
        ))

        # Availability alert (based on error rate over time)
        alerts.append(AlertConfiguration(
            alert_name=f"SLO_Availability_{tier.value.title()}",
            condition=f"""(1 - (sum(rate(http_requests_total{{status=~"5..",tier="{tier.value}"}}[7d])) / sum(rate(http_requests_total{{tier="{tier.value}"}}[7d])))) < {sli.availability_pct / 100}""",
            severity="critical",
            description=f"Availability for {tier.value} tier below SLO target of {sli.availability_pct}%",
            labels={"tier": tier.value, "slo_type": "availability"}
        ))

        # Error budget burn rate alert
        alerts.append(AlertConfiguration(
            alert_name=f"SLO_Burn_Rate_{tier.value.title()}",
            condition=f"""rate(http_requests_total{{status=~"5..",tier="{tier.value}"}}[1h]) / ({sli.error_budget_pct / 100} / 24) > {slo.burn_rate_threshold}""",
            severity="warning",
            description=f"Error budget burn rate for {tier.value} tier exceeds {slo.burn_rate_threshold}x threshold",
            labels={"tier": tier.value, "slo_type": "burn_rate"}
        ))

        return alerts

    def evaluate_slo_compliance(self, tier: ServiceTier, metrics_data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate SLO compliance for a tier based on metrics data."""
        sla_tier = self.get_tier(tier)
        slo = sla_tier.slo_definition
        sli = slo.sli_targets

        results = {
            "tier": tier.value,
            "compliance_window_days": slo.compliance_window_days,
            "sli_targets": {
                "latency_p50_ms": sli.latency_p50_ms,
                "latency_p95_ms": sli.latency_p95_ms,
                "latency_p99_ms": sli.latency_p99_ms,
                "availability_pct": sli.availability_pct,
                "error_budget_pct": sli.error_budget_pct,
                "throughput_qps": sli.throughput_qps
            },
            "current_metrics": {},
            "compliance_status": {},
            "breach_events": []
        }

        # Extract current metrics
        current_latency_p95 = metrics_data.get("latency_p95_ms", 0)
        current_latency_p99 = metrics_data.get("latency_p99_ms", 0)
        current_error_rate = metrics_data.get("error_rate_pct", 0)
        current_availability = metrics_data.get("availability_pct", 100)
        current_throughput = metrics_data.get("throughput_qps", 0)

        results["current_metrics"] = {
            "latency_p95_ms": current_latency_p95,
            "latency_p99_ms": current_latency_p99,
            "error_rate_pct": current_error_rate,
            "availability_pct": current_availability,
            "throughput_qps": current_throughput
        }

        # Evaluate compliance
        results["compliance_status"] = {
            "latency_p95_compliant": current_latency_p95 <= sli.latency_p95_ms,
            "latency_p99_compliant": current_latency_p99 <= sli.latency_p99_ms,
            "error_rate_compliant": current_error_rate <= sli.error_budget_pct,
            "availability_compliant": current_availability >= sli.availability_pct,
            "throughput_compliant": current_throughput >= sli.throughput_qps
        }

        # Check for breaches and record metrics
        if not results["compliance_status"]["latency_p95_compliant"]:
            results["breach_events"].append({
                "type": "latency_p95",
                "threshold": sli.latency_p95_ms,
                "actual": current_latency_p95,
                "severity": "warning"
            })
            if SLO_BREACH_EVENTS_TOTAL:
                SLO_BREACH_EVENTS_TOTAL.inc()

        if not results["compliance_status"]["latency_p99_compliant"]:
            results["breach_events"].append({
                "type": "latency_p99",
                "threshold": sli.latency_p99_ms,
                "actual": current_latency_p99,
                "severity": "critical"
            })
            if SLO_BREACH_EVENTS_TOTAL:
                SLO_BREACH_EVENTS_TOTAL.inc()

        if not results["compliance_status"]["error_rate_compliant"]:
            results["breach_events"].append({
                "type": "error_rate",
                "threshold": sli.error_budget_pct,
                "actual": current_error_rate,
                "severity": "critical"
            })
            if SLO_BREACH_EVENTS_TOTAL:
                SLO_BREACH_EVENTS_TOTAL.inc()

        if not results["compliance_status"]["availability_compliant"]:
            results["breach_events"].append({
                "type": "availability",
                "threshold": sli.availability_pct,
                "actual": current_availability,
                "severity": "critical"
            })
            if SLO_BREACH_EVENTS_TOTAL:
                SLO_BREACH_EVENTS_TOTAL.inc()

        return results

    def export_sla_catalog(self, output_path: str):
        """Export complete SLA catalog to JSON file."""
        catalog = {
            "metadata": {
                "version": "1.0",
                "description": "SLA Tier Specifications and SLO Targets",
                "last_updated": "2025-01-08"
            },
            "tiers": {}
        }

        for tier_enum, sla_tier in self.tiers.items():
            tier_data = {
                "tier": tier_enum.value,
                "pricing_multiplier": sla_tier.pricing_multiplier,
                "concurrency_limit": sla_tier.concurrency_limit,
                "rate_limit_qps": sla_tier.rate_limit_qps,
                "support_sla_hours": sla_tier.support_sla_hours,
                "data_retention_days": sla_tier.data_retention_days,
                "custom_features": sla_tier.custom_features,
                "slo_definition": {
                    "compliance_window_days": sla_tier.slo_definition.compliance_window_days,
                    "alert_threshold_pct": sla_tier.slo_definition.alert_threshold_pct,
                    "burn_rate_threshold": sla_tier.slo_definition.burn_rate_threshold,
                    "sli_targets": {
                        "latency_p50_ms": sla_tier.slo_definition.sli_targets.latency_p50_ms,
                        "latency_p95_ms": sla_tier.slo_definition.sli_targets.latency_p95_ms,
                        "latency_p99_ms": sla_tier.slo_definition.sli_targets.latency_p99_ms,
                        "availability_pct": sla_tier.slo_definition.sli_targets.availability_pct,
                        "error_budget_pct": sla_tier.slo_definition.sli_targets.error_budget_pct,
                        "throughput_qps": sla_tier.slo_definition.sli_targets.throughput_qps
                    }
                }
            }
            catalog["tiers"][tier_enum.value] = tier_data

        with open(output_path, "w") as f:
            json.dump(catalog, f, indent=2)

        logging.info(f"SLA catalog exported to {output_path}")


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="SLA Tier Specification & SLO Targets Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export SLA catalog
  python sla_tier_specification.py --export-catalog sla_catalog.json

  # Generate alerts for gold tier
  python sla_tier_specification.py --generate-alerts gold --output alerts_gold.yaml

  # Evaluate SLO compliance
  python sla_tier_specification.py --evaluate-compliance platinum --metrics-file metrics.json

  # Show tier specifications
  python sla_tier_specification.py --show-tiers
        """
    )

    parser.add_argument(
        "--export-catalog",
        help="Export complete SLA catalog to JSON file"
    )

    parser.add_argument(
        "--generate-alerts",
        choices=[tier.value for tier in ServiceTier],
        help="Generate Prometheus alert configurations for specified tier"
    )

    parser.add_argument(
        "--evaluate-compliance",
        choices=[tier.value for tier in ServiceTier],
        help="Evaluate SLO compliance for specified tier"
    )

    parser.add_argument(
        "--metrics-file",
        help="JSON file containing current metrics data for compliance evaluation"
    )

    parser.add_argument(
        "--show-tiers",
        action="store_true",
        help="Display all tier specifications"
    )

    parser.add_argument(
        "--output",
        help="Output file for generated configurations"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    sla_spec = SLATierSpecification()

    if args.export_catalog:
        sla_spec.export_sla_catalog(args.export_catalog)
        print(f"SLA catalog exported to {args.export_catalog}")

    elif args.generate_alerts:
        tier = ServiceTier(args.generate_alerts)
        alerts = sla_spec.generate_alert_configurations(tier)

        if args.output:
            # Export as YAML-like format for Prometheus
            with open(args.output, "w") as f:
                f.write("# Prometheus Alert Configuration\n")
                f.write(f"# Generated for {tier.value} tier\n\n")
                for alert in alerts:
                    f.write("---\n")
                    f.write(f"alert: {alert.alert_name}\n")
                    f.write(f"expr: {alert.condition}\n")
                    f.write("for: 5m\n")
                    f.write("labels:\n")
                    f.write(f"  severity: {alert.severity}\n")
                    if alert.labels:
                        for key, value in alert.labels.items():
                            f.write(f"  {key}: {value}\n")
                    f.write("annotations:\n")
                    f.write(f"  description: {alert.description}\n")
                    if alert.runbook_url:
                        f.write(f"  runbook_url: {alert.runbook_url}\n")
                    f.write("\n")
            print(f"Alert configurations exported to {args.output}")
        else:
            print(f"Alert configurations for {tier.value} tier:")
            for alert in alerts:
                print(f"- {alert.alert_name}: {alert.description}")

    elif args.evaluate_compliance:
        if not args.metrics_file:
            print("Error: --metrics-file required for compliance evaluation")
            return

        try:
            with open(args.metrics_file) as f:
                metrics_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Metrics file {args.metrics_file} not found")
            return
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in metrics file {args.metrics_file}")
            return

        tier = ServiceTier(args.evaluate_compliance)
        results = sla_spec.evaluate_slo_compliance(tier, metrics_data)

        print(f"SLO Compliance Evaluation for {tier.value} tier:")
        print("=" * 50)
        print(f"Compliance Window: {results['compliance_window_days']} days")
        print("\nSLI Targets:")
        for key, value in results['sli_targets'].items():
            print(f"  {key}: {value}")

        print("\nCurrent Metrics:")
        for key, value in results['current_metrics'].items():
            print(f"  {key}: {value}")

        print("\nCompliance Status:")
        all_compliant = True
        for key, compliant in results['compliance_status'].items():
            status = "✅ PASS" if compliant else "❌ FAIL"
            print(f"  {key}: {status}")
            if not compliant:
                all_compliant = False

        if results['breach_events']:
            print("\nBreach Events:")
            for breach in results['breach_events']:
                print(f"  {breach['type']}: {breach['actual']} > {breach['threshold']} ({breach['severity']})")

        overall_status = "✅ COMPLIANT" if all_compliant else "❌ NON-COMPLIANT"
        print(f"\nOverall Status: {overall_status}")

    elif args.show_tiers:
        print("SLA Tier Specifications:")
        print("=" * 50)

        for tier_enum in ServiceTier:
            tier = sla_spec.get_tier(tier_enum)
            slo = tier.slo_definition
            sli = slo.sli_targets

            print(f"\n{tier_enum.value.upper()} TIER")
            print("-" * 30)
            print(f"Pricing Multiplier: {tier.pricing_multiplier}x")
            print(f"Concurrency Limit: {tier.concurrency_limit}")
            print(f"Rate Limit: {tier.rate_limit_qps} QPS")
            print(f"Support SLA: {tier.support_sla_hours} hours")
            print(f"Data Retention: {tier.data_retention_days} days")

            print("\nSLO Targets:")
            print(f"  Latency P95: {sli.latency_p95_ms}ms")
            print(f"  Availability: {sli.availability_pct}%")
            print(f"  Error Budget: {sli.error_budget_pct}%")
            print(f"  Throughput: {sli.throughput_qps} QPS")

            print("\nFeatures:")
            for feature in tier.custom_features:
                print(f"  • {feature}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
