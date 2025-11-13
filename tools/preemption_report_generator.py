#!/usr/bin/env python3
"""Preemption Benchmark Report Template (GAP-182).

Generates formatted reports from preemption benchmarking results.
Provides both human-readable and machine-readable output formats.
"""

import json
import time
from pathlib import Path


class PreemptionReportGenerator:
    """Generates formatted reports from preemption benchmark results."""

    def __init__(self, results_file: str = "preemption_benchmark_results.json",
                 metrics_file: str = "preemption_metrics_report.json"):
        self.results_file = results_file
        self.metrics_file = metrics_file
        self.results_data = None
        self.metrics_data = None

    def load_data(self):
        """Load benchmark results and metrics data."""
        try:
            with open(self.results_file) as f:
                self.results_data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {self.results_file} not found")
            self.results_data = {"scenarios": []}

        try:
            with open(self.metrics_file) as f:
                self.metrics_data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: {self.metrics_file} not found")
            self.metrics_data = {"scenario_details": []}

    def generate_summary_report(self) -> str:
        """Generate a human-readable summary report."""
        if not self.results_data or not self.metrics_data:
            self.load_data()

        report_lines = []
        report_lines.append("Preemption Benchmarking Suite Report")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Timestamp
        if self.results_data and "timestamp" in self.results_data:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S",
                                    time.localtime(self.results_data["timestamp"]))
            report_lines.append(f"Generated: {timestamp}")
            report_lines.append("")

        # Executive Summary
        report_lines.append("Executive Summary")
        report_lines.append("-" * 30)

        if self.metrics_data and "summary" in self.metrics_data:
            summary = self.metrics_data["summary"]
            report_lines.append(f"Total Scenarios Run: {summary['total_scenarios']}")
            report_lines.append(f"Total Preemptions: {summary['total_preemptions']}")
            report_lines.append(".1%")
            report_lines.append(".2f")
            report_lines.append("")

            # QoS Distribution
            report_lines.append("QoS Preemption Distribution:")
            for qos, count in summary['qos_preemption_distribution'].items():
                qos_name = {"g": "Gold", "s": "Silver", "b": "Bronze"}.get(qos, qos.upper())
                report_lines.append(f"  {qos_name}: {count} preemptions")
            report_lines.append("")

        # Scenario Details
        report_lines.append("Scenario Details")
        report_lines.append("-" * 25)

        if self.results_data and "scenarios" in self.results_data:
            for scenario in self.results_data["scenarios"]:
                report_lines.append(f"\n* {scenario['name']}:")
                report_lines.append(f"  Total Sessions: {scenario['total_sessions']}")
                report_lines.append(f"  QoS Distribution: {scenario['qos_distribution']}")
                report_lines.append(f"  Needed Slots: {scenario['needed_slots']}")
                report_lines.append(f"  Preempted: {scenario['preempted_count']} sessions")
                report_lines.append(f"  Preemption Efficiency: {scenario['preemption_efficiency']:.1%}")
                report_lines.append(f"  By QoS: {scenario['preempted_by_qos']}")

        # Age Statistics
        if self.metrics_data and "age_statistics" in self.metrics_data:
            age_stats = self.metrics_data["age_statistics"]
            if age_stats:
                report_lines.append("\nAge Statistics (Preempted Sessions)")
                report_lines.append("-" * 40)
                report_lines.append(".2f")
                report_lines.append(".2f")
                report_lines.append(".2f")

        # Performance Analysis
        report_lines.append("\nPerformance Analysis")
        report_lines.append("-" * 30)

        if self.metrics_data and "scenario_details" in self.metrics_data:
            details = self.metrics_data["scenario_details"]

            # Calculate performance metrics
            efficiencies = [s["scenario"]["preemption_efficiency"] for s in details
                          if s["scenario"]["needed_slots"] > 0]
            execution_times = [s["scenario"]["execution_time_ms"] for s in details]

            if efficiencies:
                avg_efficiency = sum(efficiencies) / len(efficiencies)
                report_lines.append(f"Average Efficiency: {avg_efficiency:.1%}")

            if execution_times:
                avg_time = sum(execution_times) / len(execution_times)
                report_lines.append(f"Average Execution Time: {avg_time:.2f}ms")

        # Recommendations
        report_lines.append("\nRecommendations")
        report_lines.append("-" * 20)

        if self.metrics_data and "summary" in self.metrics_data:
            summary = self.metrics_data["summary"]
            efficiency = summary.get("average_efficiency", 0)

            if efficiency > 0.9:
                report_lines.append("SUCCESS: Excellent preemption efficiency (>90%)")
                report_lines.append("   Policy is effectively targeting lower QoS sessions")
            elif efficiency > 0.7:
                report_lines.append("WARNING: Good preemption efficiency (70-90%)")
                report_lines.append("   Consider optimizing QoS distribution for better results")
            else:
                report_lines.append("ERROR: Low preemption efficiency (<70%)")
                report_lines.append("   Review preemption policy and session distribution")

            # QoS-specific recommendations
            qos_dist = summary.get("qos_preemption_distribution", {})
            bronze_count = qos_dist.get("b", 0)
            silver_count = qos_dist.get("s", 0)

            if bronze_count > silver_count * 2:
                report_lines.append("SUCCESS: Bronze-first policy working effectively")
            elif silver_count > bronze_count:
                report_lines.append("WARNING: High silver preemption - review bronze availability")

        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("End of Preemption Benchmark Report")

        return "\n".join(report_lines)

    def generate_detailed_report(self) -> str:
        """Generate a detailed technical report."""
        if not self.results_data or not self.metrics_data:
            self.load_data()

        report_lines = []
        report_lines.append("Preemption Benchmarking Suite - Detailed Technical Report")
        report_lines.append("=" * 90)
        report_lines.append("")

        # Technical Details Header
        report_lines.append("Technical Details")
        report_lines.append("-" * 25)

        if self.metrics_data and "scenario_details" in self.metrics_data:
            for i, detail in enumerate(self.metrics_data["scenario_details"], 1):
                scenario = detail["scenario"]
                delta = detail["delta"]

                report_lines.append(f"\nScenario {i}: {scenario['scenario_name']}")
                report_lines.append("-" * (15 + len(scenario['scenario_name'])))

                # Session details
                report_lines.append(f"Session Count: {scenario['total_sessions']}")
                report_lines.append(f"QoS Distribution: {scenario['qos_distribution']}")
                report_lines.append(f"Required Slots: {scenario['needed_slots']}")

                # Preemption details
                report_lines.append(f"Preempted Sessions: {scenario['preempted_count']}")
                report_lines.append(f"Preemption Efficiency: {scenario['preemption_efficiency']:.3f}")
                report_lines.append(f"Preempted by QoS: {scenario['preempted_by_qos']}")

                # Performance metrics
                report_lines.append(".2f")
                report_lines.append(f"Preemptions Delta: {delta['preemptions_delta']}")

                # Age statistics
                if scenario.get("age_statistics"):
                    age = scenario["age_statistics"]
                    report_lines.append("Age Statistics (ms):")
                    report_lines.append(f"  Min: {age.get('min', 0):.2f}")
                    report_lines.append(f"  Max: {age.get('max', 0):.2f}")
                    report_lines.append(f"  Avg: {age.get('avg', 0):.2f}")
                    report_lines.append(f"  Median: {age.get('median', 0):.2f}")

                report_lines.append("")

        # Raw Data Section
        report_lines.append("Raw Benchmark Data")
        report_lines.append("-" * 30)
        report_lines.append("See JSON files for complete raw data:")
        report_lines.append(f"  - {self.results_file}")
        report_lines.append(f"  - {self.metrics_file}")

        return "\n".join(report_lines)

    def generate_markdown_report(self) -> str:
        """Generate a Markdown-formatted report for documentation."""
        if not self.results_data or not self.metrics_data:
            self.load_data()

        report_lines = []
        report_lines.append("# Preemption Benchmarking Suite Report")
        report_lines.append("")

        # Summary section
        report_lines.append("## Executive Summary")
        report_lines.append("")

        if self.metrics_data and "summary" in self.metrics_data:
            summary = self.metrics_data["summary"]
            report_lines.append(f"- **Total Scenarios**: {summary['total_scenarios']}")
            report_lines.append(f"- **Total Preemptions**: {summary['total_preemptions']}")
            report_lines.append(".1%")
            report_lines.append(".2f")
            report_lines.append("")

            # QoS Distribution Table
            report_lines.append("### QoS Preemption Distribution")
            report_lines.append("")
            report_lines.append("| QoS Class | Preemptions | Percentage |")
            report_lines.append("|-----------|-------------|------------|")

            total_preemptions = sum(summary['qos_preemption_distribution'].values())
            for qos, count in summary['qos_preemption_distribution'].items():
                qos_name = {"g": "Gold", "s": "Silver", "b": "Bronze"}.get(qos, qos.upper())
                percentage = (count / total_preemptions * 100) if total_preemptions > 0 else 0
                report_lines.append(f"| {qos_name} | {count} | {percentage:.1f}% |")

            report_lines.append("")

        # Scenario Details
        report_lines.append("## Scenario Details")
        report_lines.append("")

        if self.results_data and "scenarios" in self.results_data:
            for scenario in self.results_data["scenarios"]:
                report_lines.append(f"### {scenario['name']}")
                report_lines.append("")
                report_lines.append(f"- **Total Sessions**: {scenario['total_sessions']}")
                report_lines.append(f"- **QoS Distribution**: {scenario['qos_distribution']}")
                report_lines.append(f"- **Needed Slots**: {scenario['needed_slots']}")
                report_lines.append(f"- **Preempted**: {scenario['preempted_count']} sessions")
                report_lines.append(f"- **Efficiency**: {scenario['preemption_efficiency']:.1%}")
                report_lines.append(f"- **By QoS**: {scenario['preempted_by_qos']}")
                report_lines.append("")

        # Recommendations
        report_lines.append("## Recommendations")
        report_lines.append("")

        if self.metrics_data and "summary" in self.metrics_data:
            summary = self.metrics_data["summary"]
            efficiency = summary.get("average_efficiency", 0)

            if efficiency > 0.9:
                report_lines.append("SUCCESS: **Excellent performance**: Preemption efficiency >90%")
            elif efficiency > 0.7:
                report_lines.append("WARNING: **Good performance**: Preemption efficiency 70-90%")
            else:
                report_lines.append("ERROR: **Needs improvement**: Preemption efficiency <70%")

        report_lines.append("")
        report_lines.append("*Report generated by Preemption Benchmarking Suite (GAP-182)*")

        return "\n".join(report_lines)

    def save_reports(self, output_dir: str = "."):
        """Save all report formats to files."""
        Path(output_dir).mkdir(exist_ok=True)

        # Summary report
        summary_path = Path(output_dir) / "preemption_summary_report.txt"
        with open(summary_path, 'w') as f:
            f.write(self.generate_summary_report())
        print(f"Summary report saved to {summary_path}")

        # Detailed report
        detailed_path = Path(output_dir) / "preemption_detailed_report.txt"
        with open(detailed_path, 'w') as f:
            f.write(self.generate_detailed_report())
        print(f"Detailed report saved to {detailed_path}")

        # Markdown report
        markdown_path = Path(output_dir) / "preemption_report.md"
        with open(markdown_path, 'w') as f:
            f.write(self.generate_markdown_report())
        print(f"Markdown report saved to {markdown_path}")


def main():
    """Generate all preemption benchmark reports."""
    print("Generating Preemption Benchmark Reports...")

    generator = PreemptionReportGenerator()

    # Generate and save all reports
    generator.save_reports("reports")

    print("All reports generated successfully!")


if __name__ == "__main__":
    main()
