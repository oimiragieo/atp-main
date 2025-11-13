#!/usr/bin/env python3
"""Preemption Metrics Capture Harness (GAP-182).

Captures and analyzes preemption metrics during benchmarking scenarios.
Integrates with the existing metrics registry to collect preemption statistics.
"""

import asyncio
import json
import statistics
import time
from collections import defaultdict
from typing import Any

from metrics.registry import REGISTRY
from router_service.preemption import Active, pick_preemptions


class PreemptionMetricsHarness:
    """Captures and analyzes preemption metrics during benchmarking."""

    def __init__(self):
        self.metrics_history: list[dict[str, Any]] = []
        self.start_time = time.time()

    def capture_baseline_metrics(self) -> dict[str, Any]:
        """Capture baseline metrics before scenario execution."""
        return {
            "timestamp": time.time(),
            "preemptions_total": self._get_metric_value("preemptions_total"),
            "type": "baseline",
        }

    def capture_scenario_metrics(
        self, scenario_name: str, active_sessions: list[Active], needed_slots: int, preempted: list[str]
    ) -> dict[str, Any]:
        """Capture metrics after scenario execution."""
        # Calculate QoS distribution
        qos_dist = defaultdict(int)
        for session in active_sessions:
            qos_dist[session.qos] += 1

        # Calculate preempted by QoS
        preempted_by_qos = defaultdict(int)
        for session in preempted:
            # Extract QoS from session ID (first character)
            qos = session[0] if session else "unknown"
            preempted_by_qos[qos] += 1

        # Calculate age statistics for preempted sessions
        preempted_ages = []
        session_age_map = {s.session: time.time() * 1000 - s.started_ms for s in active_sessions}

        for session in preempted:
            if session in session_age_map:
                preempted_ages.append(session_age_map[session])

        age_stats = {}
        if preempted_ages:
            age_stats = {
                "mean_age_ms": statistics.mean(preempted_ages),
                "median_age_ms": statistics.median(preempted_ages),
                "min_age_ms": min(preempted_ages),
                "max_age_ms": max(preempted_ages),
                "stdev_age_ms": statistics.stdev(preempted_ages) if len(preempted_ages) > 1 else 0,
            }

        return {
            "timestamp": time.time(),
            "scenario_name": scenario_name,
            "total_sessions": len(active_sessions),
            "qos_distribution": dict(qos_dist),
            "needed_slots": needed_slots,
            "preempted_count": len(preempted),
            "preempted_by_qos": dict(preempted_by_qos),
            "preemption_efficiency": len(preempted) / needed_slots if needed_slots > 0 else 0,
            "preemptions_total": self._get_metric_value("preemptions_total"),
            "age_statistics": age_stats,
            "type": "scenario",
        }

    def _get_metric_value(self, metric_name: str) -> float:
        """Get current value of a metric from the registry."""
        try:
            # Access the metric registry to get current values
            # This is a simplified version - in practice you'd need to access
            # the actual metric values from the registry
            return getattr(REGISTRY, "_metrics", {}).get(metric_name, 0)
        except Exception:
            return 0

    def calculate_scenario_delta(self, baseline: dict, scenario: dict) -> dict[str, Any]:
        """Calculate the delta between baseline and scenario metrics."""
        return {
            "preemptions_delta": scenario["preemptions_total"] - baseline["preemptions_total"],
            "time_delta_ms": (scenario["timestamp"] - baseline["timestamp"]) * 1000,
            "efficiency": scenario["preemption_efficiency"],
        }

    async def run_scenario_with_metrics(
        self, scenario_name: str, active_sessions: list[Active], needed_slots: int, prefer_oldest: bool = True
    ) -> dict[str, Any]:
        """Run a scenario and capture comprehensive metrics."""
        # Capture baseline
        baseline = self.capture_baseline_metrics()

        # Run scenario
        start_time = time.time()
        preempted = pick_preemptions(active_sessions, needed_slots, prefer_oldest)
        execution_time_ms = (time.time() - start_time) * 1000

        # Capture scenario metrics
        scenario_metrics = self.capture_scenario_metrics(scenario_name, active_sessions, needed_slots, preempted)
        scenario_metrics["execution_time_ms"] = execution_time_ms

        # Calculate delta
        delta = self.calculate_scenario_delta(baseline, scenario_metrics)

        # Combine all metrics
        result = {"baseline": baseline, "scenario": scenario_metrics, "delta": delta, "preempted_sessions": preempted}

        self.metrics_history.append(result)
        return result

    def generate_metrics_report(self) -> dict[str, Any]:
        """Generate a comprehensive metrics report."""
        if not self.metrics_history:
            return {"error": "No metrics data available"}

        # Aggregate statistics across all scenarios
        total_scenarios = len(self.metrics_history)
        total_preemptions = sum(r["delta"]["preemptions_delta"] for r in self.metrics_history)
        avg_efficiency = statistics.mean(
            r["scenario"]["preemption_efficiency"] for r in self.metrics_history if r["scenario"]["needed_slots"] > 0
        )
        avg_execution_time = statistics.mean(r["scenario"]["execution_time_ms"] for r in self.metrics_history)

        # QoS-specific statistics
        qos_preemption_counts = defaultdict(int)
        for result in self.metrics_history:
            for qos, count in result["scenario"]["preempted_by_qos"].items():
                qos_preemption_counts[qos] += count

        # Age statistics aggregation
        age_means = [
            r["scenario"]["age_statistics"].get("mean_age_ms", 0)
            for r in self.metrics_history
            if r["scenario"]["age_statistics"]
        ]

        age_stats_agg = {}
        if age_means:
            age_stats_agg = {
                "mean_age_across_scenarios": statistics.mean(age_means),
                "median_age_across_scenarios": statistics.median(age_means),
                "age_variance": statistics.variance(age_means) if len(age_means) > 1 else 0,
            }

        return {
            "summary": {
                "total_scenarios": total_scenarios,
                "total_preemptions": total_preemptions,
                "average_efficiency": avg_efficiency,
                "average_execution_time_ms": avg_execution_time,
                "qos_preemption_distribution": dict(qos_preemption_counts),
            },
            "age_statistics": age_stats_agg,
            "scenario_details": self.metrics_history,
            "generated_at": time.time(),
        }

    def export_metrics_report(self, filename: str = "preemption_metrics_report.json"):
        """Export comprehensive metrics report to JSON."""
        report = self.generate_metrics_report()

        with open(filename, "w") as f:
            json.dump(report, f, indent=2)

        print(f"📊 Metrics report exported to {filename}")
        return report


async def benchmark_preemption_policy():
    """Benchmark the preemption policy with various scenarios."""
    print("🔬 Starting Preemption Policy Benchmark...")

    harness = PreemptionMetricsHarness()

    # Define test scenarios
    scenarios = [
        {
            "name": "gold_spike_bronze_rich",
            "sessions": [
                Active("g1", "gold", time.time() * 1000 - 1000),
                Active("g2", "gold", time.time() * 1000 - 2000),
                Active("s1", "silver", time.time() * 1000 - 1500),
                Active("b1", "bronze", time.time() * 1000 - 500),
                Active("b2", "bronze", time.time() * 1000 - 800),
                Active("b3", "bronze", time.time() * 1000 - 1200),
            ],
            "needed": 3,
        },
        {
            "name": "balanced_load_mixed_preemption",
            "sessions": [
                Active("g1", "gold", time.time() * 1000 - 3000),
                Active("s1", "silver", time.time() * 1000 - 2500),
                Active("s2", "silver", time.time() * 1000 - 1800),
                Active("b1", "bronze", time.time() * 1000 - 1000),
                Active("b2", "bronze", time.time() * 1000 - 1500),
            ],
            "needed": 2,
        },
        {
            "name": "bronze_only_preemption",
            "sessions": [
                Active("g1", "gold", time.time() * 1000 - 5000),
                Active("b1", "bronze", time.time() * 1000 - 1000),
                Active("b2", "bronze", time.time() * 1000 - 2000),
                Active("b3", "bronze", time.time() * 1000 - 3000),
                Active("b4", "bronze", time.time() * 1000 - 4000),
            ],
            "needed": 4,
        },
    ]

    # Run scenarios and capture metrics
    for scenario in scenarios:
        result = await harness.run_scenario_with_metrics(scenario["name"], scenario["sessions"], scenario["needed"])
        print(f"✅ Completed: {scenario['name']} - Preempted: {len(result['preempted_sessions'])}")

    # Generate and export report
    report = harness.export_metrics_report()

    # Print summary
    print("\n📈 Preemption Policy Benchmark Results:")
    print("=" * 60)
    print(f"Total Scenarios: {report['summary']['total_scenarios']}")
    print(f"Total Preemptions: {report['summary']['total_preemptions']}")
    print(".1%")
    print(".2f")
    print(f"QoS Distribution: {report['summary']['qos_preemption_distribution']}")

    return report


if __name__ == "__main__":
    asyncio.run(benchmark_preemption_policy())
