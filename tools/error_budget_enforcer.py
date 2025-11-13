#!/usr/bin/env python3
"""Error Budget Policy Enforcement for CI/CD Pipeline."""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional


@dataclass
class SLODefinition:
    """Service Level Objective definition."""

    name: str
    target_percentage: float  # e.g., 99.9 for 99.9% uptime
    window_days: int  # Rolling window in days
    error_budget_percentage: float  # Max allowed error budget consumption


@dataclass
class SLOViolation:
    """Represents an SLO violation."""

    slo_name: str
    timestamp: datetime
    actual_percentage: float
    target_percentage: float
    error_budget_consumed: float
    description: str


@dataclass
class ErrorBudgetState:
    """Current state of error budget consumption."""

    slo_name: str
    total_requests: int = 0
    error_requests: int = 0
    window_start: datetime = field(default_factory=lambda: datetime.now() - timedelta(days=30))
    violations: list[SLOViolation] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def error_rate_percentage(self) -> float:
        """Calculate current error rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.error_requests / self.total_requests) * 100

    @property
    def availability_percentage(self) -> float:
        """Calculate current availability percentage."""
        return 100.0 - self.error_rate_percentage

    def add_measurement(self, total_requests: int, error_requests: int):
        """Add a new measurement to the error budget."""
        self.total_requests += total_requests
        self.error_requests += error_requests
        self.last_updated = datetime.now()

    def check_violation(self, slo: SLODefinition) -> Optional[SLOViolation]:
        """Check if current measurements violate the SLO."""
        current_availability = self.availability_percentage

        if current_availability < slo.target_percentage:
            error_budget_consumed = (
                (slo.target_percentage - current_availability) / (100.0 - slo.target_percentage)
            ) * 100

            violation = SLOViolation(
                slo_name=slo.name,
                timestamp=datetime.now(),
                actual_percentage=current_availability,
                target_percentage=slo.target_percentage,
                error_budget_consumed=error_budget_consumed,
                description=f"SLO violation: {current_availability:.2f}% < {slo.target_percentage:.2f}% target",
            )

            self.violations.append(violation)
            return violation

        return None

    def get_error_budget_remaining(self, slo: SLODefinition) -> float:
        """Calculate remaining error budget percentage."""
        current_availability = self.availability_percentage
        if current_availability >= slo.target_percentage:
            return slo.error_budget_percentage  # Full budget remaining

        # Calculate consumed budget as percentage of allowed error rate
        # consumed_budget% = (current_error_rate - allowed_error_rate) / allowed_error_rate * 100%
        allowed_error_rate = 100.0 - slo.target_percentage
        current_error_rate = 100.0 - current_availability

        if current_error_rate <= allowed_error_rate:
            return slo.error_budget_percentage

        consumed = ((current_error_rate - allowed_error_rate) / allowed_error_rate) * slo.error_budget_percentage
        return max(0.0, slo.error_budget_percentage - consumed)


class ErrorBudgetEnforcer:
    """Enforces error budget policies in CI/CD pipeline."""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "error_budget_config.json"
        self.slos: dict[str, SLODefinition] = {}
        self.states: dict[str, ErrorBudgetState] = {}
        self.load_config()

    def load_config(self):
        """Load SLO configuration from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    config_data = json.load(f)

                for slo_data in config_data.get("slos", []):
                    slo = SLODefinition(
                        name=slo_data["name"],
                        target_percentage=slo_data["target_percentage"],
                        window_days=slo_data["window_days"],
                        error_budget_percentage=slo_data["error_budget_percentage"],
                    )
                    self.slos[slo.name] = slo
                    self.states[slo.name] = ErrorBudgetState(slo.name)

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading config: {e}")
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        """Create default SLO configuration."""
        default_slos = [
            {"name": "api_availability", "target_percentage": 99.9, "window_days": 30, "error_budget_percentage": 5.0},
            {
                "name": "p95_latency",
                "target_percentage": 95.0,  # 95% of requests under 200ms
                "window_days": 7,
                "error_budget_percentage": 10.0,
            },
            {
                "name": "error_rate",
                "target_percentage": 99.0,  # Max 1% error rate
                "window_days": 30,
                "error_budget_percentage": 3.0,
            },
        ]

        for slo_data in default_slos:
            slo = SLODefinition(**slo_data)
            self.slos[slo.name] = slo
            self.states[slo.name] = ErrorBudgetState(slo.name)

        self.save_config()

    def save_config(self):
        """Save current configuration to file."""
        config_data = {
            "slos": [
                {
                    "name": slo.name,
                    "target_percentage": slo.target_percentage,
                    "window_days": slo.window_days,
                    "error_budget_percentage": slo.error_budget_percentage,
                }
                for slo in self.slos.values()
            ]
        }

        with open(self.config_file, "w") as f:
            json.dump(config_data, f, indent=2)

    def record_measurement(self, slo_name: str, total_requests: int, error_requests: int):
        """Record a measurement for an SLO."""
        if slo_name not in self.states:
            raise ValueError(f"Unknown SLO: {slo_name}")

        self.states[slo_name].add_measurement(total_requests, error_requests)

    def check_all_slos(self) -> list[SLOViolation]:
        """Check all SLOs for violations."""
        violations = []

        for slo_name, slo in self.slos.items():
            state = self.states[slo_name]
            violation = state.check_violation(slo)
            if violation:
                violations.append(violation)

        return violations

    def enforce_budget_gates(self) -> bool:
        """Enforce error budget gates. Returns True if all gates pass."""
        violations = self.check_all_slos()

        if violations:
            print("❌ Error Budget Policy Violations:")
            for violation in violations:
                print(f"  - {violation.slo_name}: {violation.description}")
                print(".2f")
            return False

        # Check if any SLO is close to exhausting its budget
        budget_warnings = []
        for slo_name, slo in self.slos.items():
            state = self.states[slo_name]
            remaining = state.get_error_budget_remaining(slo)

            if remaining < 20.0:  # Less than 20% budget remaining
                budget_warnings.append(f"{slo_name}: {remaining:.1f}% budget remaining")

        if budget_warnings:
            print("⚠️  Error Budget Warnings:")
            for warning in budget_warnings:
                print(f"  - {warning}")

        print("✅ All error budget gates passed")
        return True

    def get_budget_status(self) -> dict[str, Any]:
        """Get comprehensive budget status for all SLOs."""
        status = {}

        for slo_name, slo in self.slos.items():
            state = self.states[slo_name]
            status[slo_name] = {
                "slo_target": slo.target_percentage,
                "current_availability": state.availability_percentage,
                "error_rate": state.error_rate_percentage,
                "total_requests": state.total_requests,
                "error_requests": state.error_requests,
                "budget_remaining_percent": state.get_error_budget_remaining(slo),
                "violations_count": len(state.violations),
                "last_updated": state.last_updated.isoformat(),
            }

        return status

    def export_metrics(self, output_file: str):
        """Export error budget metrics for monitoring."""
        status = self.get_budget_status()

        metrics = {"timestamp": datetime.now().isoformat(), "error_budget_status": status}

        with open(output_file, "w") as f:
            json.dump(metrics, f, indent=2)

    def simulate_measurements(self, slo_name: str, days: int = 30):
        """Simulate measurements for testing purposes."""
        if slo_name not in self.states:
            raise ValueError(f"Unknown SLO: {slo_name}")

        # Simulate daily measurements with some variance
        base_requests = 10000
        base_error_rate = 0.005  # 0.5% base error rate

        for _ in range(days):
            # Add some daily variance
            daily_requests = base_requests + int((0.1 * base_requests) * (0.5 - time.time() % 1))
            daily_errors = int(daily_requests * (base_error_rate + (0.002 * (0.5 - time.time() % 1))))

            self.record_measurement(slo_name, daily_requests, daily_errors)


def main():
    """Main entry point for CI/CD error budget enforcement."""
    import argparse

    parser = argparse.ArgumentParser(description="Error Budget Policy Enforcement")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--check", action="store_true", help="Check error budget gates")
    parser.add_argument("--status", action="store_true", help="Show budget status")
    parser.add_argument("--export-metrics", help="Export metrics to file")
    parser.add_argument("--simulate", help="Simulate measurements for SLO")
    parser.add_argument(
        "--record",
        nargs=3,
        metavar=("SLO", "TOTAL", "ERRORS"),
        help="Record measurement: SLO_NAME TOTAL_REQUESTS ERROR_REQUESTS",
    )

    args = parser.parse_args()

    enforcer = ErrorBudgetEnforcer(args.config)

    if args.record:
        slo_name, total_str, errors_str = args.record
        try:
            total = int(total_str)
            errors = int(errors_str)
            enforcer.record_measurement(slo_name, total, errors)
            print(f"Recorded measurement for {slo_name}: {total} total, {errors} errors")
        except ValueError as e:
            print(f"Error recording measurement: {e}")
            sys.exit(1)

    if args.simulate:
        try:
            enforcer.simulate_measurements(args.simulate)
            print(f"Simulated 30 days of measurements for {args.simulate}")
        except ValueError as e:
            print(f"Error simulating measurements: {e}")
            sys.exit(1)

    if args.status:
        status = enforcer.get_budget_status()
        print("Error Budget Status:")
        print(json.dumps(status, indent=2))

    if args.export_metrics:
        enforcer.export_metrics(args.export_metrics)
        print(f"Metrics exported to {args.export_metrics}")

    if args.check:
        success = enforcer.enforce_budget_gates()
        sys.exit(0 if success else 1)

    # Default action: check gates
    if not any([args.status, args.export_metrics, args.simulate, args.record]):
        success = enforcer.enforce_budget_gates()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
