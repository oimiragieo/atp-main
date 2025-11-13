#!/usr/bin/env python3
"""Preemption Benchmarking Scenarios (GAP-182).

Simulates various preemption scenarios to benchmark the preemption policy
under different QoS distributions and load patterns.
"""

import asyncio
import json
import random
import time
from collections import defaultdict
from dataclasses import dataclass

from router_service.preemption import Active, pick_preemptions


@dataclass
class ScenarioResult:
    """Results from a preemption scenario run."""

    scenario_name: str
    total_sessions: int
    qos_distribution: dict[str, int]
    preempted_sessions: list[str]
    preempted_counts: dict[str, int]
    execution_time_ms: float
    needed_slots: int


class PreemptionScenarioRunner:
    """Runs preemption benchmarking scenarios."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.results: list[ScenarioResult] = []

    def generate_sessions(self, qos_dist: dict[str, int], max_age_ms: float = 10000.0) -> list[Active]:
        """Generate a list of active sessions with given QoS distribution."""
        sessions = []
        session_id = 0

        for qos, count in qos_dist.items():
            for _ in range(count):
                age = self.rng.uniform(0, max_age_ms)
                started_ms = time.time() * 1000 - age
                sessions.append(Active(session=f"{qos}{session_id}", qos=qos, started_ms=started_ms))
                session_id += 1

        return sessions

    async def run_scenario(
        self, name: str, qos_dist: dict[str, int], needed_slots: int, prefer_oldest: bool = True
    ) -> ScenarioResult:
        """Run a single preemption scenario."""
        start_time = time.time()

        # Generate sessions
        active_sessions = self.generate_sessions(qos_dist)

        # Run preemption selection
        preempted = pick_preemptions(active_sessions, needed_slots, prefer_oldest)

        execution_time_ms = (time.time() - start_time) * 1000

        # Count preempted by QoS
        preempted_counts = defaultdict(int)
        for session in preempted:
            qos = session[0]  # First character indicates QoS (g, s, b)
            preempted_counts[qos] += 1

        result = ScenarioResult(
            scenario_name=name,
            total_sessions=sum(qos_dist.values()),
            qos_distribution=qos_dist.copy(),
            preempted_sessions=preempted,
            preempted_counts=dict(preempted_counts),
            execution_time_ms=execution_time_ms,
            needed_slots=needed_slots,
        )

        self.results.append(result)
        return result

    async def run_gold_spike_scenario(self) -> ScenarioResult:
        """Scenario: Gold traffic spike requires preemption of lower QoS."""
        return await self.run_scenario(
            "gold_spike_heavy_bronze", {"gold": 5, "silver": 10, "bronze": 50}, needed_slots=15
        )

    async def run_balanced_load_scenario(self) -> ScenarioResult:
        """Scenario: Balanced load with moderate preemption needs."""
        return await self.run_scenario(
            "balanced_load_moderate_preemption", {"gold": 15, "silver": 20, "bronze": 30}, needed_slots=8
        )

    async def run_bronze_dominant_scenario(self) -> ScenarioResult:
        """Scenario: Bronze-dominant with small gold spike."""
        return await self.run_scenario(
            "bronze_dominant_small_spike", {"gold": 3, "silver": 5, "bronze": 80}, needed_slots=5
        )

    async def run_silver_heavy_scenario(self) -> ScenarioResult:
        """Scenario: Silver-heavy requiring silver preemption."""
        return await self.run_scenario(
            "silver_heavy_silver_preemption", {"gold": 8, "silver": 60, "bronze": 20}, needed_slots=25
        )

    async def run_minimal_gold_scenario(self) -> ScenarioResult:
        """Scenario: Minimal gold with massive lower QoS."""
        return await self.run_scenario(
            "minimal_gold_massive_lower", {"gold": 2, "silver": 100, "bronze": 200}, needed_slots=50
        )

    async def run_all_scenarios(self) -> list[ScenarioResult]:
        """Run all predefined scenarios."""
        scenarios = [
            self.run_gold_spike_scenario,
            self.run_balanced_load_scenario,
            self.run_bronze_dominant_scenario,
            self.run_silver_heavy_scenario,
            self.run_minimal_gold_scenario,
        ]

        results = []
        for scenario in scenarios:
            result = await scenario()
            results.append(result)
            print(f"✅ Completed scenario: {result.scenario_name}")

        return results

    def export_results(self, filename: str = "preemption_benchmark_results.json"):
        """Export results to JSON file."""
        data = {
            "timestamp": time.time(),
            "scenarios": [
                {
                    "name": r.scenario_name,
                    "total_sessions": r.total_sessions,
                    "qos_distribution": r.qos_distribution,
                    "preempted_count": len(r.preempted_sessions),
                    "preempted_by_qos": r.preempted_counts,
                    "execution_time_ms": r.execution_time_ms,
                    "needed_slots": r.needed_slots,
                    "preemption_efficiency": len(r.preempted_sessions) / r.needed_slots if r.needed_slots > 0 else 0,
                }
                for r in self.results
            ],
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        print(f"📊 Results exported to {filename}")


async def main():
    """Main entry point for running preemption scenarios."""
    print("🚀 Starting Preemption Benchmark Scenarios...")

    runner = PreemptionScenarioRunner(seed=42)

    # Run all scenarios
    results = await runner.run_all_scenarios()

    # Export results
    runner.export_results()

    # Print summary
    print("\n📈 Preemption Benchmark Summary:")
    print("=" * 60)

    for result in results:
        print(f"\n🎯 {result.scenario_name}:")
        print(f"  Total Sessions: {result.total_sessions}")
        print(f"  QoS Distribution: {result.qos_distribution}")
        print(f"  Needed Slots: {result.needed_slots}")
        print(f"  Preempted: {len(result.preempted_sessions)} sessions")
        print(f"  By QoS: {result.preempted_counts}")
        print(f"  Execution Time: {result.execution_time_ms:.2f}ms")
        efficiency = len(result.preempted_sessions) / result.needed_slots if result.needed_slots > 0 else 0
        print(f"  Efficiency: {efficiency:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
