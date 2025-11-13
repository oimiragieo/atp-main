"""GAP-210: Central metrics catalog generator.

Builds and maintains a comprehensive catalog of all ATP router metrics
with descriptions, types, and schema validation.
"""

import json
import os
import sys
from typing import Any

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics.registry import REGISTRY


class MetricsCatalogGenerator:
    """Generates and validates metrics catalog for ATP router."""

    def __init__(self) -> None:
        self.catalog_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"enum": ["counter", "histogram", "gauge"]},
                            "description": {"type": "string"},
                            "unit": {"type": "string"},
                            "buckets": {"type": "array", "items": {"type": "number"}},
                            "labels": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "type", "description"],
                    },
                },
                "version": {"type": "string"},
                "generated_at": {"type": "string"},
            },
            "required": ["metrics", "version"],
        }

        # Known metrics catalog with descriptions
        self.known_metrics = {
            # Request metrics
            "atp_router_requests_total": {
                "type": "counter",
                "description": "Total number of requests processed",
                "unit": "requests",
                "labels": ["method", "status"],
            },
            "atp_router_request_duration_seconds": {
                "type": "histogram",
                "description": "Request duration in seconds",
                "unit": "seconds",
                "buckets": [0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            },
            "atp_router_active_connections": {
                "type": "gauge",
                "description": "Number of active connections",
                "unit": "connections",
            },
            # Model selection metrics
            "atp_router_model_selections_total": {
                "type": "counter",
                "description": "Total model selections by algorithm",
                "unit": "selections",
                "labels": ["algorithm", "model"],
            },
            "atp_router_ucb_score": {
                "type": "gauge",
                "description": "Upper Confidence Bound score for model selection",
                "unit": "score",
                "labels": ["model", "cluster"],
            },
            # Consensus metrics
            "atp_router_consensus_agreement_pct": {
                "type": "gauge",
                "description": "Percentage of consensus agreement",
                "unit": "percent",
            },
            "atp_router_evidence_score": {
                "type": "histogram",
                "description": "Evidence scores for consensus",
                "unit": "score",
                "buckets": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            },
            # Resource metrics
            "atp_router_memory_usage_bytes": {"type": "gauge", "description": "Memory usage in bytes", "unit": "bytes"},
            "atp_router_cpu_usage_percent": {"type": "gauge", "description": "CPU usage percentage", "unit": "percent"},
            # Error metrics
            "atp_router_errors_total": {
                "type": "counter",
                "description": "Total number of errors",
                "unit": "errors",
                "labels": ["type", "component"],
            },
            # SLM and energy metrics
            "slm_energy_savings_kwh_total": {
                "type": "counter",
                "description": "Total energy savings from SLM vs large model usage",
                "unit": "kWh",
            },
            "slm_carbon_savings_co2e_grams_total": {
                "type": "counter",
                "description": "Total CO2e savings from SLM vs large model usage",
                "unit": "grams",
            },
            "slm_energy_efficiency_ratio": {
                "type": "gauge",
                "description": "Ratio of SLM energy use vs large model (lower is better)",
                "unit": "ratio",
            },
            # Window and QoS metrics
            "atp_router_window_tokens_remaining": {
                "type": "gauge",
                "description": "Remaining tokens in current window",
                "unit": "tokens",
                "labels": ["tier"],
            },
            "atp_router_budget_burn_rate_usd_per_min": {
                "type": "gauge",
                "description": "Current budget burn rate",
                "unit": "usd_per_minute",
            },
            # Federation metrics
            "atp_router_federation_updates_total": {
                "type": "counter",
                "description": "Total federation route updates",
                "unit": "updates",
                "labels": ["peer", "type"],
            },
            # Security metrics
            "atp_router_waf_blocks_total": {
                "type": "counter",
                "description": "Total WAF blocks",
                "unit": "blocks",
                "labels": ["rule", "severity"],
            },
            "atp_router_pii_redactions_total": {
                "type": "counter",
                "description": "Total PII redactions performed",
                "unit": "redactions",
            },
        }

    def generate_catalog(self) -> dict[str, Any]:
        """Generate complete metrics catalog from known metrics and registry."""
        import datetime

        # Start with known metrics
        catalog_metrics = []

        # Add known metrics
        for name, info in self.known_metrics.items():
            metric_entry = {
                "name": name,
                "type": info["type"],
                "description": info["description"],
                "unit": info.get("unit", ""),
                "buckets": info.get("buckets", []),
                "labels": info.get("labels", []),
            }
            catalog_metrics.append(metric_entry)

        # Add any metrics found in registry but not in known catalog
        registry_export = REGISTRY.export()

        for metric_type, metrics in registry_export.items():
            if metric_type == "ts":
                continue

            for name in metrics.keys():
                if not any(m["name"] == name for m in catalog_metrics):
                    # Add unknown metric with basic info
                    metric_entry = {
                        "name": name,
                        "type": metric_type[:-1],  # Remove 's' from counters/gauges/histograms
                        "description": f"Auto-discovered {metric_type[:-1]} metric",
                        "unit": "",
                        "buckets": [],
                        "labels": [],
                    }
                    catalog_metrics.append(metric_entry)

        # Sort metrics by name
        catalog_metrics.sort(key=lambda x: x["name"])

        catalog = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "metrics": catalog_metrics,
            "version": "1.0.0",
            "generated_at": datetime.datetime.now().isoformat(),
            "total_metrics": len(catalog_metrics),
        }

        return catalog

    def validate_catalog(self, catalog: dict[str, Any]) -> list[str]:
        """Validate catalog against schema and return validation errors."""
        errors = []

        # Basic structure validation
        if "metrics" not in catalog:
            errors.append("Missing 'metrics' field")
            return errors

        if not isinstance(catalog["metrics"], list):
            errors.append("'metrics' field must be a list")
            return errors

        # Validate each metric
        for i, metric in enumerate(catalog["metrics"]):
            if not isinstance(metric, dict):
                errors.append(f"Metric {i} must be a dictionary")
                continue

            required_fields = ["name", "type", "description"]
            for field in required_fields:
                if field not in metric:
                    errors.append(f"Metric {i} ({metric.get('name', 'unknown')}) missing required field '{field}'")

            if "type" in metric and metric["type"] not in ["counter", "histogram", "gauge"]:
                errors.append(f"Metric {i} ({metric.get('name', 'unknown')}) has invalid type '{metric['type']}'")

        return errors

    def save_catalog(self, output_path: str) -> None:
        """Generate and save metrics catalog to file."""
        catalog = self.generate_catalog()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(catalog, f, indent=2)

    def load_and_validate_catalog(self, catalog_path: str) -> tuple[dict[str, Any], list[str]]:
        """Load catalog from file and validate it."""
        try:
            with open(catalog_path) as f:
                catalog = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return {}, [f"Failed to load catalog: {e}"]

        errors = self.validate_catalog(catalog)
        return catalog, errors


def main():
    """Command-line interface for metrics catalog generation."""
    import argparse

    parser = argparse.ArgumentParser(description="ATP Router Metrics Catalog Generator")
    parser.add_argument("--output", "-o", default="docs/metrics_catalog.json", help="Output path for metrics catalog")
    parser.add_argument("--validate", help="Validate existing catalog file")

    args = parser.parse_args()

    generator = MetricsCatalogGenerator()

    if args.validate:
        # Validate existing catalog
        catalog, errors = generator.load_and_validate_catalog(args.validate)
        if errors:
            print("Validation errors:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print(f"Catalog validation successful. Found {len(catalog.get('metrics', []))} metrics.")
            return 0
    else:
        # Generate new catalog
        generator.save_catalog(args.output)
        print(f"Metrics catalog generated and saved to {args.output}")

        # Validate the generated catalog
        catalog, errors = generator.load_and_validate_catalog(args.output)
        if errors:
            print("Warning: Generated catalog has validation errors:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"Generated catalog is valid with {len(catalog.get('metrics', []))} metrics.")

        return 0


if __name__ == "__main__":
    exit(main())
