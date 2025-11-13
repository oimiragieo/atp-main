#!/usr/bin/env python3
"""Tests for Preemption Benchmarking Suite (GAP-182).

Comprehensive test suite validating the preemption benchmarking tools,
scenarios, metrics capture, and report generation.
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from router_service.preemption import Active
from tools.preemption_metrics_harness import PreemptionMetricsHarness
from tools.preemption_report_generator import PreemptionReportGenerator
from tools.preemption_scenarios import PreemptionScenarioRunner, ScenarioResult


class TestPreemptionScenarioRunner:
    """Test the preemption scenario runner."""

    def test_generate_sessions(self):
        """Test session generation with QoS distribution."""
        runner = PreemptionScenarioRunner(seed=42)

        qos_dist = {"gold": 2, "silver": 3, "bronze": 5}
        sessions = runner.generate_sessions(qos_dist)

        assert len(sessions) == 10
        assert sum(1 for s in sessions if s.qos == "gold") == 2
        assert sum(1 for s in sessions if s.qos == "silver") == 3
        assert sum(1 for s in sessions if s.qos == "bronze") == 5

        # Check session IDs are unique
        session_ids = [s.session for s in sessions]
        assert len(session_ids) == len(set(session_ids))

    @pytest.mark.asyncio
    async def test_run_gold_spike_scenario(self):
        """Test gold spike scenario execution."""
        runner = PreemptionScenarioRunner(seed=42)

        result = await runner.run_gold_spike_scenario()

        assert isinstance(result, ScenarioResult)
        assert result.scenario_name == "gold_spike_heavy_bronze"
        assert result.total_sessions == 65  # 5 gold + 10 silver + 50 bronze
        assert result.needed_slots == 15
        assert len(result.preempted_sessions) <= 15
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_run_all_scenarios(self):
        """Test running all predefined scenarios."""
        runner = PreemptionScenarioRunner(seed=42)

        results = await runner.run_all_scenarios()

        assert len(results) == 5
        scenario_names = [r.scenario_name for r in results]
        expected_names = [
            "gold_spike_heavy_bronze",
            "balanced_load_moderate_preemption",
            "bronze_dominant_small_spike",
            "silver_heavy_silver_preemption",
            "minimal_gold_massive_lower",
        ]
        assert scenario_names == expected_names

    def test_export_results(self):
        """Test exporting results to JSON."""
        runner = PreemptionScenarioRunner(seed=42)

        # Create a mock result
        result = ScenarioResult(
            scenario_name="test_scenario",
            total_sessions=10,
            qos_distribution={"gold": 2, "silver": 3, "bronze": 5},
            preempted_sessions=["b1", "b2", "s1"],
            preempted_counts={"b": 2, "s": 1},
            execution_time_ms=5.5,
            needed_slots=3,
        )
        runner.results = [result]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = f.name

        try:
            runner.export_results(temp_file)

            # Verify file was created and contains expected data
            assert os.path.exists(temp_file)

            with open(temp_file) as f:
                data = json.load(f)

            assert "scenarios" in data
            assert len(data["scenarios"]) == 1
            assert data["scenarios"][0]["name"] == "test_scenario"
            assert data["scenarios"][0]["preemption_efficiency"] == 1.0  # 3/3

        finally:
            os.unlink(temp_file)


class TestPreemptionMetricsHarness:
    """Test the preemption metrics harness."""

    def test_capture_baseline_metrics(self):
        """Test capturing baseline metrics."""
        harness = PreemptionMetricsHarness()

        baseline = harness.capture_baseline_metrics()

        assert "timestamp" in baseline
        assert "preemptions_total" in baseline
        assert baseline["type"] == "baseline"

    def test_capture_scenario_metrics(self):
        """Test capturing scenario metrics."""
        harness = PreemptionMetricsHarness()

        active_sessions = [
            Active("g1", "gold", time.time() * 1000 - 1000),
            Active("s1", "silver", time.time() * 1000 - 2000),
            Active("b1", "bronze", time.time() * 1000 - 3000),
        ]

        preempted = ["b1"]
        result = harness.capture_scenario_metrics("test_scenario", active_sessions, 1, preempted)

        assert result["scenario_name"] == "test_scenario"
        assert result["total_sessions"] == 3
        assert result["qos_distribution"] == {"gold": 1, "silver": 1, "bronze": 1}
        assert result["preempted_count"] == 1
        assert result["preempted_by_qos"] == {"b": 1}
        assert result["preemption_efficiency"] == 1.0

    @pytest.mark.asyncio
    async def test_run_scenario_with_metrics(self):
        """Test running scenario with metrics capture."""
        harness = PreemptionMetricsHarness()

        active_sessions = [
            Active("g1", "gold", time.time() * 1000 - 1000),
            Active("b1", "bronze", time.time() * 1000 - 2000),
            Active("b2", "bronze", time.time() * 1000 - 3000),
        ]

        result = await harness.run_scenario_with_metrics("test_scenario", active_sessions, 2, prefer_oldest=True)

        assert "baseline" in result
        assert "scenario" in result
        assert "delta" in result
        assert "preempted_sessions" in result

        # Should preempt 2 bronze sessions (oldest first)
        assert len(result["preempted_sessions"]) == 2
        assert "b2" in result["preempted_sessions"]  # oldest
        assert "b1" in result["preempted_sessions"]  # newer

    def test_generate_metrics_report(self):
        """Test generating comprehensive metrics report."""
        harness = PreemptionMetricsHarness()

        # Add mock data
        mock_result = {
            "baseline": {"preemptions_total": 0, "timestamp": time.time()},
            "scenario": {
                "scenario_name": "test",
                "total_sessions": 5,
                "qos_distribution": {"gold": 1, "silver": 1, "bronze": 3},
                "needed_slots": 2,
                "preempted_count": 2,
                "preempted_by_qos": {"b": 2},
                "preemption_efficiency": 1.0,
                "preemptions_total": 2,
                "execution_time_ms": 1.5,
                "age_statistics": {
                    "mean_age_ms": 1500,
                    "median_age_ms": 1500,
                    "min_age_ms": 1000,
                    "max_age_ms": 2000,
                    "stdev_age_ms": 500,
                },
            },
            "delta": {"preemptions_delta": 2, "time_delta_ms": 10, "efficiency": 1.0},
            "preempted_sessions": ["b1", "b2"],
        }
        harness.metrics_history = [mock_result]

        report = harness.generate_metrics_report()

        assert "summary" in report
        assert "age_statistics" in report
        assert "scenario_details" in report
        assert report["summary"]["total_scenarios"] == 1
        assert report["summary"]["total_preemptions"] == 2
        assert report["summary"]["average_efficiency"] == 1.0


class TestPreemptionReportGenerator:
    """Test the preemption report generator."""

    def test_load_data_missing_files(self):
        """Test loading data when files don't exist."""
        generator = PreemptionReportGenerator("nonexistent_results.json", "nonexistent_metrics.json")

        generator.load_data()

        # Should handle missing files gracefully
        assert generator.results_data == {"scenarios": []}
        assert generator.metrics_data == {"scenario_details": []}

    def test_generate_summary_report(self):
        """Test generating summary report."""
        generator = PreemptionReportGenerator()

        # Mock data
        generator.results_data = {
            "timestamp": time.time(),
            "scenarios": [
                {
                    "name": "test_scenario",
                    "total_sessions": 10,
                    "qos_distribution": {"gold": 2, "silver": 3, "bronze": 5},
                    "needed_slots": 3,
                    "preempted_count": 3,
                    "preempted_by_qos": {"b": 3},
                    "preemption_efficiency": 1.0,
                }
            ],
        }

        generator.metrics_data = {
            "summary": {
                "total_scenarios": 1,
                "total_preemptions": 3,
                "average_efficiency": 1.0,
                "average_execution_time_ms": 2.5,
                "qos_preemption_distribution": {"b": 3},
            },
            "age_statistics": {
                "mean_age_across_scenarios": 1500,
                "median_age_across_scenarios": 1500,
                "age_variance": 250000,
            },
            "scenario_details": [],
        }

        report = generator.generate_summary_report()

        assert "Executive Summary" in report
        assert "test_scenario" in report
        assert "Recommendations" in report
        assert "Excellent preemption efficiency" in report

    def test_generate_markdown_report(self):
        """Test generating Markdown report."""
        generator = PreemptionReportGenerator()

        # Mock data
        generator.results_data = {
            "scenarios": [
                {
                    "name": "test_scenario",
                    "total_sessions": 5,
                    "qos_distribution": {"gold": 1, "silver": 1, "bronze": 3},
                    "needed_slots": 2,
                    "preempted_count": 2,
                    "preempted_by_qos": {"b": 2},
                    "preemption_efficiency": 1.0,
                }
            ]
        }

        generator.metrics_data = {
            "summary": {
                "total_scenarios": 1,
                "total_preemptions": 2,
                "average_efficiency": 1.0,
                "qos_preemption_distribution": {"b": 2},
            }
        }

        report = generator.generate_markdown_report()

        assert report.startswith("# Preemption Benchmarking Suite Report")
        assert "| Bronze | 2 | 100.0% |" in report
        assert "Excellent performance" in report

    def test_save_reports(self):
        """Test saving reports to files."""
        generator = PreemptionReportGenerator()

        # Mock data
        generator.results_data = {"scenarios": []}
        generator.metrics_data = {
            "summary": {
                "total_scenarios": 0,
                "total_preemptions": 0,
                "average_efficiency": 0.0,
                "average_execution_time_ms": 0.0,
                "qos_preemption_distribution": {},
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            generator.save_reports(temp_dir)

            # Check that files were created
            expected_files = ["preemption_summary_report.txt", "preemption_detailed_report.txt", "preemption_report.md"]

            for filename in expected_files:
                filepath = Path(temp_dir) / filename
                assert filepath.exists(), f"File {filename} was not created"
                assert filepath.stat().st_size > 0, f"File {filename} is empty"


class TestPreemptionBenchmarkingIntegration:
    """Integration tests for the complete preemption benchmarking suite."""

    @pytest.mark.asyncio
    async def test_full_benchmark_workflow(self):
        """Test the complete benchmarking workflow."""
        # This would be a full integration test, but for now we'll test the components

        # Test scenario runner
        runner = PreemptionScenarioRunner(seed=42)
        result = await runner.run_gold_spike_scenario()

        assert result.total_sessions == 65
        assert result.needed_slots == 15
        assert len(result.preempted_sessions) > 0

        # Test metrics harness
        harness = PreemptionMetricsHarness()
        active_sessions = [
            Active("g1", "gold", time.time() * 1000 - 1000),
            Active("b1", "bronze", time.time() * 1000 - 2000),
        ]

        metrics_result = await harness.run_scenario_with_metrics("integration_test", active_sessions, 1)

        assert len(metrics_result["preempted_sessions"]) == 1
        assert metrics_result["scenario"]["preemption_efficiency"] == 1.0

    def test_benchmark_data_consistency(self):
        """Test that benchmark data is consistent across components."""
        # Create test data
        runner = PreemptionScenarioRunner(seed=42)

        # Simulate running scenarios
        async def run_test():
            results = await runner.run_all_scenarios()
            return results

        # Run in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(run_test())
        finally:
            loop.close()

        # Verify all results have required fields
        for result in results:
            assert result.scenario_name
            assert result.total_sessions > 0
            assert result.needed_slots > 0
            assert isinstance(result.preempted_sessions, list)
            assert isinstance(result.preempted_counts, dict)
            assert result.execution_time_ms >= 0

        # Verify QoS distribution consistency
        for result in results:
            total_from_dist = sum(result.qos_distribution.values())
            assert total_from_dist == result.total_sessions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
