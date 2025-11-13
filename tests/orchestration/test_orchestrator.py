# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Test Orchestration System
Comprehensive test orchestration for enterprise ATP platform testing.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import aiofiles
import yaml

# Import test runners and utilities
from tests.utils.coverage_analyzer import CoverageAnalyzer


@dataclass
class TestSuiteConfig:
    """Configuration for a test suite."""

    name: str
    description: str
    enabled: bool
    priority: int
    timeout: int
    parallel: bool
    dependencies: list[str]
    environment: dict[str, str]
    parameters: dict[str, Any]


@dataclass
class TestExecutionResult:
    """Result of test execution."""

    suite_name: str
    success: bool
    duration: float
    tests_run: int
    tests_passed: int
    tests_failed: int
    coverage_percentage: float
    error_message: str | None
    artifacts: list[str]


class TestOrchestrator:
    """Orchestrates comprehensive testing across all test suites."""

    def __init__(self, config_file: str = "tests/config/test_orchestration.yaml"):
        """Initialize test orchestrator."""
        self.config_file = config_file
        self.config = self._load_config()
        self.results: dict[str, TestExecutionResult] = {}
        self.start_time = 0
        self.end_time = 0

        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("tests/logs/orchestration.log"), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    def _load_config(self) -> dict[str, Any]:
        """Load test orchestration configuration."""
        if os.path.exists(self.config_file):
            with open(self.config_file) as f:
                return yaml.safe_load(f)
        else:
            # Default configuration
            return self._get_default_config()

    def _get_default_config(self) -> dict[str, Any]:
        """Get default test orchestration configuration."""
        return {
            "test_suites": {
                "unit": {
                    "name": "Unit Tests",
                    "description": "Fast unit tests for individual components",
                    "enabled": True,
                    "priority": 1,
                    "timeout": 300,
                    "parallel": True,
                    "dependencies": [],
                    "environment": {},
                    "parameters": {"coverage_threshold": 80, "test_pattern": "test_*.py"},
                },
                "integration": {
                    "name": "Integration Tests",
                    "description": "Integration tests with external dependencies",
                    "enabled": True,
                    "priority": 2,
                    "timeout": 600,
                    "parallel": False,
                    "dependencies": ["unit"],
                    "environment": {"TESTCONTAINERS_RYUK_DISABLED": "true"},
                    "parameters": {"use_testcontainers": True},
                },
                "security": {
                    "name": "Security Tests",
                    "description": "Security and penetration tests",
                    "enabled": True,
                    "priority": 3,
                    "timeout": 900,
                    "parallel": False,
                    "dependencies": ["unit"],
                    "environment": {},
                    "parameters": {"scan_depth": "comprehensive"},
                },
                "performance": {
                    "name": "Performance Tests",
                    "description": "K6 performance and load tests",
                    "enabled": True,
                    "priority": 4,
                    "timeout": 1200,
                    "parallel": False,
                    "dependencies": ["unit", "integration"],
                    "environment": {"K6_VUS": "50", "K6_DURATION": "5m"},
                    "parameters": {"scenarios": ["baseline", "stress", "spike"]},
                },
                "e2e": {
                    "name": "End-to-End Tests",
                    "description": "End-to-end tests using Playwright",
                    "enabled": True,
                    "priority": 5,
                    "timeout": 1800,
                    "parallel": False,
                    "dependencies": ["unit", "integration"],
                    "environment": {"PLAYWRIGHT_BROWSERS_PATH": "0"},
                    "parameters": {"browser": "chromium", "headless": True},
                },
                "mutation": {
                    "name": "Mutation Tests",
                    "description": "Mutation testing to validate test quality",
                    "enabled": False,  # Disabled by default due to long runtime
                    "priority": 6,
                    "timeout": 3600,
                    "parallel": False,
                    "dependencies": ["unit"],
                    "environment": {},
                    "parameters": {"mutation_score_threshold": 80},
                },
                "compliance": {
                    "name": "Compliance Tests",
                    "description": "GDPR, SOC 2, and ISO 27001 compliance tests",
                    "enabled": True,
                    "priority": 7,
                    "timeout": 600,
                    "parallel": False,
                    "dependencies": ["security"],
                    "environment": {},
                    "parameters": {"standards": ["gdpr", "soc2", "iso27001"]},
                },
            },
            "global_settings": {
                "max_parallel_suites": 3,
                "continue_on_failure": True,
                "generate_reports": True,
                "cleanup_artifacts": False,
                "notification_webhook": None,
            },
            "reporting": {
                "formats": ["html", "json", "junit"],
                "output_directory": "tests/reports",
                "include_coverage": True,
                "include_performance_metrics": True,
            },
        }

    async def run_all_tests(
        self, suite_filter: list[str] | None = None, parallel: bool = False, fail_fast: bool = False
    ) -> dict[str, Any]:
        """Run all enabled test suites."""
        self.start_time = time.time()
        self.logger.info("Starting comprehensive test execution")

        # Filter and sort test suites
        suites_to_run = self._get_suites_to_run(suite_filter)

        if parallel and self.config["global_settings"]["max_parallel_suites"] > 1:
            await self._run_suites_parallel(suites_to_run, fail_fast)
        else:
            await self._run_suites_sequential(suites_to_run, fail_fast)

        self.end_time = time.time()

        # Generate comprehensive report
        report = await self._generate_comprehensive_report()

        # Send notifications if configured
        await self._send_notifications(report)

        return report

    def _get_suites_to_run(self, suite_filter: list[str] | None = None) -> list[TestSuiteConfig]:
        """Get filtered and sorted list of test suites to run."""
        suites = []

        for suite_name, suite_config in self.config["test_suites"].items():
            if suite_filter and suite_name not in suite_filter:
                continue

            if not suite_config.get("enabled", True):
                continue

            suites.append(
                TestSuiteConfig(
                    name=suite_name,
                    description=suite_config["description"],
                    enabled=suite_config["enabled"],
                    priority=suite_config["priority"],
                    timeout=suite_config["timeout"],
                    parallel=suite_config.get("parallel", False),
                    dependencies=suite_config.get("dependencies", []),
                    environment=suite_config.get("environment", {}),
                    parameters=suite_config.get("parameters", {}),
                )
            )

        # Sort by priority
        suites.sort(key=lambda x: x.priority)

        return suites

    async def _run_suites_sequential(self, suites: list[TestSuiteConfig], fail_fast: bool):
        """Run test suites sequentially."""
        for suite in suites:
            # Check dependencies
            if not self._check_dependencies(suite):
                self.logger.warning(f"Skipping {suite.name} due to failed dependencies")
                continue

            self.logger.info(f"Running {suite.name}")
            result = await self._run_single_suite(suite)
            self.results[suite.name] = result

            if fail_fast and not result.success:
                self.logger.error(f"Stopping execution due to failure in {suite.name}")
                break

    async def _run_suites_parallel(self, suites: list[TestSuiteConfig], fail_fast: bool):
        """Run test suites in parallel where possible."""
        max_parallel = self.config["global_settings"]["max_parallel_suites"]

        # Group suites by dependency levels
        dependency_levels = self._group_by_dependency_levels(suites)

        for level, level_suites in dependency_levels.items():
            self.logger.info(f"Running dependency level {level} suites")

            # Run suites in this level in parallel
            semaphore = asyncio.Semaphore(max_parallel)
            tasks = []

            for suite in level_suites:
                if not self._check_dependencies(suite):
                    continue

                task = asyncio.create_task(self._run_suite_with_semaphore(semaphore, suite))
                tasks.append(task)

            # Wait for all tasks in this level to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                suite = level_suites[i]
                if isinstance(result, Exception):
                    self.logger.error(f"Exception in {suite.name}: {result}")
                    self.results[suite.name] = TestExecutionResult(
                        suite_name=suite.name,
                        success=False,
                        duration=0,
                        tests_run=0,
                        tests_passed=0,
                        tests_failed=0,
                        coverage_percentage=0,
                        error_message=str(result),
                        artifacts=[],
                    )
                else:
                    self.results[suite.name] = result

                if fail_fast and not result.success:
                    self.logger.error(f"Stopping execution due to failure in {suite.name}")
                    return

    async def _run_suite_with_semaphore(
        self, semaphore: asyncio.Semaphore, suite: TestSuiteConfig
    ) -> TestExecutionResult:
        """Run a test suite with semaphore for concurrency control."""
        async with semaphore:
            return await self._run_single_suite(suite)

    async def _run_single_suite(self, suite: TestSuiteConfig) -> TestExecutionResult:
        """Run a single test suite."""
        start_time = time.time()

        try:
            # Set environment variables
            env = os.environ.copy()
            env.update(suite.environment)

            # Run the appropriate test suite
            if suite.name == "unit":
                result = await self._run_unit_tests(suite, env)
            elif suite.name == "integration":
                result = await self._run_integration_tests(suite, env)
            elif suite.name == "security":
                result = await self._run_security_tests(suite, env)
            elif suite.name == "performance":
                result = await self._run_performance_tests(suite, env)
            elif suite.name == "e2e":
                result = await self._run_e2e_tests(suite, env)
            elif suite.name == "mutation":
                result = await self._run_mutation_tests(suite, env)
            elif suite.name == "compliance":
                result = await self._run_compliance_tests(suite, env)
            else:
                raise ValueError(f"Unknown test suite: {suite.name}")

            duration = time.time() - start_time
            result.duration = duration

            return result

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Error running {suite.name}: {e}")

            return TestExecutionResult(
                suite_name=suite.name,
                success=False,
                duration=duration,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                coverage_percentage=0,
                error_message=str(e),
                artifacts=[],
            )

    async def _run_unit_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run unit tests."""
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "--cov=router_service,metrics,observability,monitoring,integrations",
            "--cov-report=xml",
            "--cov-report=html",
            "--junit-xml=tests/reports/unit-results.xml",
            "-x" if not self.config["global_settings"]["continue_on_failure"] else "",
            "--maxfail=5",
        ]

        # Filter out empty strings
        cmd = [arg for arg in cmd if arg]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, cwd=os.getcwd()
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=suite.timeout)

            # Parse pytest output
            output = stdout.decode("utf-8")
            success = process.returncode == 0

            # Extract test counts from output
            tests_run, tests_passed, tests_failed = self._parse_pytest_output(output)

            # Get coverage percentage
            coverage_pct = self._extract_coverage_percentage(output)

            return TestExecutionResult(
                suite_name=suite.name,
                success=success,
                duration=0,  # Will be set by caller
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                coverage_percentage=coverage_pct,
                error_message=stderr.decode("utf-8") if stderr else None,
                artifacts=["tests/reports/unit-results.xml", "htmlcov/"],
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

            return TestExecutionResult(
                suite_name=suite.name,
                success=False,
                duration=suite.timeout,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                coverage_percentage=0,
                error_message=f"Test suite timed out after {suite.timeout} seconds",
                artifacts=[],
            )

    async def _run_integration_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run integration tests."""
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/integration/",
            "-v",
            "--tb=short",
            "--junit-xml=tests/reports/integration-results.xml",
        ]

        return await self._run_pytest_command(cmd, suite, env)

    async def _run_security_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run security tests."""
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/security/",
            "-v",
            "--tb=short",
            "--junit-xml=tests/reports/security-results.xml",
        ]

        return await self._run_pytest_command(cmd, suite, env)

    async def _run_performance_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run performance tests using K6."""
        cmd = [
            "k6",
            "run",
            "tests/performance/k6_load_tests.js",
            "--out",
            "json=tests/reports/performance-results.json",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=suite.timeout)

            success = process.returncode == 0
            stdout.decode("utf-8")

            # Parse K6 output for metrics
            tests_run = 1  # K6 runs scenarios, not individual tests
            tests_passed = 1 if success else 0
            tests_failed = 0 if success else 1

            return TestExecutionResult(
                suite_name=suite.name,
                success=success,
                duration=0,
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                coverage_percentage=0,  # N/A for performance tests
                error_message=stderr.decode("utf-8") if stderr else None,
                artifacts=["tests/reports/performance-results.json"],
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

            return TestExecutionResult(
                suite_name=suite.name,
                success=False,
                duration=suite.timeout,
                tests_run=0,
                tests_passed=0,
                tests_failed=1,
                coverage_percentage=0,
                error_message="Performance tests timed out",
                artifacts=[],
            )

    async def _run_e2e_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run E2E tests using Playwright."""
        cmd = ["python", "-m", "pytest", "tests/e2e/", "-v", "--tb=short", "--junit-xml=tests/reports/e2e-results.xml"]

        return await self._run_pytest_command(cmd, suite, env)

    async def _run_mutation_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run mutation tests."""
        cmd = [
            "mutmut",
            "run",
            "--paths-to-mutate",
            "router_service,metrics,observability",
            "--runner",
            "python -m pytest tests/ -x --tb=short",
            "--use-coverage",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=suite.timeout)

            success = process.returncode == 0
            output = stdout.decode("utf-8")

            # Parse mutmut output
            mutation_score = self._extract_mutation_score(output)
            threshold = suite.parameters.get("mutation_score_threshold", 80)

            success = success and mutation_score >= threshold

            return TestExecutionResult(
                suite_name=suite.name,
                success=success,
                duration=0,
                tests_run=1,
                tests_passed=1 if success else 0,
                tests_failed=0 if success else 1,
                coverage_percentage=mutation_score,
                error_message=stderr.decode("utf-8") if stderr else None,
                artifacts=["mutmut-results.html"],
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

            return TestExecutionResult(
                suite_name=suite.name,
                success=False,
                duration=suite.timeout,
                tests_run=0,
                tests_passed=0,
                tests_failed=1,
                coverage_percentage=0,
                error_message="Mutation tests timed out",
                artifacts=[],
            )

    async def _run_compliance_tests(self, suite: TestSuiteConfig, env: dict[str, str]) -> TestExecutionResult:
        """Run compliance tests."""
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/security/",
            "-k",
            "compliance",
            "-v",
            "--tb=short",
            "--junit-xml=tests/reports/compliance-results.xml",
        ]

        return await self._run_pytest_command(cmd, suite, env)

    async def _run_pytest_command(
        self, cmd: list[str], suite: TestSuiteConfig, env: dict[str, str]
    ) -> TestExecutionResult:
        """Run a pytest command and parse results."""
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=suite.timeout)

            output = stdout.decode("utf-8")
            success = process.returncode == 0

            tests_run, tests_passed, tests_failed = self._parse_pytest_output(output)
            coverage_pct = self._extract_coverage_percentage(output)

            return TestExecutionResult(
                suite_name=suite.name,
                success=success,
                duration=0,
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                coverage_percentage=coverage_pct,
                error_message=stderr.decode("utf-8") if stderr else None,
                artifacts=[f"tests/reports/{suite.name}-results.xml"],
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

            return TestExecutionResult(
                suite_name=suite.name,
                success=False,
                duration=suite.timeout,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                coverage_percentage=0,
                error_message=f"Tests timed out after {suite.timeout} seconds",
                artifacts=[],
            )

    def _check_dependencies(self, suite: TestSuiteConfig) -> bool:
        """Check if suite dependencies have passed."""
        for dep in suite.dependencies:
            if dep not in self.results:
                return False
            if not self.results[dep].success:
                return False
        return True

    def _group_by_dependency_levels(self, suites: list[TestSuiteConfig]) -> dict[int, list[TestSuiteConfig]]:
        """Group suites by dependency levels for parallel execution."""
        levels = {}
        suite_levels = {}

        def get_level(suite: TestSuiteConfig) -> int:
            if suite.name in suite_levels:
                return suite_levels[suite.name]

            if not suite.dependencies:
                level = 0
            else:
                max_dep_level = 0
                for dep in suite.dependencies:
                    dep_suite = next((s for s in suites if s.name == dep), None)
                    if dep_suite:
                        max_dep_level = max(max_dep_level, get_level(dep_suite))
                level = max_dep_level + 1

            suite_levels[suite.name] = level
            return level

        for suite in suites:
            level = get_level(suite)
            if level not in levels:
                levels[level] = []
            levels[level].append(suite)

        return levels

    def _parse_pytest_output(self, output: str) -> tuple[int, int, int]:
        """Parse pytest output to extract test counts."""
        import re

        # Look for patterns like "5 passed, 2 failed"
        pattern = r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?"
        match = re.search(pattern, output)

        if match:
            passed = int(match.group(1))
            failed = int(match.group(2)) if match.group(2) else 0
            total = passed + failed
            return total, passed, failed

        return 0, 0, 0

    def _extract_coverage_percentage(self, output: str) -> float:
        """Extract coverage percentage from pytest output."""
        import re

        pattern = r"TOTAL\s+\d+\s+\d+\s+(\d+)%"
        match = re.search(pattern, output)

        if match:
            return float(match.group(1))

        return 0.0

    def _extract_mutation_score(self, output: str) -> float:
        """Extract mutation score from mutmut output."""
        import re

        pattern = r"Mutation score: (\d+\.\d+)%"
        match = re.search(pattern, output)

        if match:
            return float(match.group(1))

        return 0.0

    async def _generate_comprehensive_report(self) -> dict[str, Any]:
        """Generate comprehensive test execution report."""
        total_duration = self.end_time - self.start_time

        # Calculate overall statistics
        total_suites = len(self.results)
        passed_suites = sum(1 for r in self.results.values() if r.success)
        failed_suites = total_suites - passed_suites

        total_tests = sum(r.tests_run for r in self.results.values())
        total_passed = sum(r.tests_passed for r in self.results.values())
        total_failed = sum(r.tests_failed for r in self.results.values())

        # Calculate weighted coverage
        coverage_results = [r for r in self.results.values() if r.coverage_percentage > 0]
        avg_coverage = (
            sum(r.coverage_percentage for r in coverage_results) / len(coverage_results) if coverage_results else 0
        )

        report = {
            "execution_summary": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_duration": total_duration,
                "total_suites": total_suites,
                "passed_suites": passed_suites,
                "failed_suites": failed_suites,
                "suite_success_rate": (passed_suites / total_suites * 100) if total_suites > 0 else 0,
                "total_tests": total_tests,
                "total_passed": total_passed,
                "total_failed": total_failed,
                "test_success_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
                "average_coverage": avg_coverage,
            },
            "suite_results": {name: asdict(result) for name, result in self.results.items()},
            "quality_metrics": await self._calculate_quality_metrics(),
            "recommendations": self._generate_recommendations(),
            "artifacts": self._collect_artifacts(),
        }

        # Generate reports in configured formats
        await self._generate_reports(report)

        return report

    async def _calculate_quality_metrics(self) -> dict[str, Any]:
        """Calculate quality metrics across all test suites."""
        metrics = {
            "test_coverage": {"line_coverage": 0, "branch_coverage": 0, "function_coverage": 0},
            "security_score": 0,
            "performance_score": 0,
            "reliability_score": 0,
            "maintainability_score": 0,
        }

        # Calculate coverage metrics if coverage data exists
        if os.path.exists(".coverage"):
            analyzer = CoverageAnalyzer()
            coverage_analysis = analyzer.analyze_coverage()

            metrics["test_coverage"] = {
                "line_coverage": coverage_analysis["overall_metrics"]["line_coverage"],
                "branch_coverage": coverage_analysis["overall_metrics"]["branch_coverage"],
                "function_coverage": len(
                    [f for f in coverage_analysis.get("function_metrics", {}).values() for func in f if func.is_tested]
                )
                / max(1, len([f for f in coverage_analysis.get("function_metrics", {}).values() for func in f]))
                * 100,
            }

        # Calculate security score based on security test results
        security_result = self.results.get("security")
        if security_result:
            metrics["security_score"] = (security_result.tests_passed / max(1, security_result.tests_run)) * 100

        # Calculate performance score based on performance test results
        performance_result = self.results.get("performance")
        if performance_result:
            metrics["performance_score"] = 100 if performance_result.success else 0

        # Calculate reliability score based on overall test success
        total_tests = sum(r.tests_run for r in self.results.values())
        total_passed = sum(r.tests_passed for r in self.results.values())
        metrics["reliability_score"] = (total_passed / max(1, total_tests)) * 100

        # Calculate maintainability score based on mutation testing
        mutation_result = self.results.get("mutation")
        if mutation_result:
            metrics["maintainability_score"] = mutation_result.coverage_percentage
        else:
            metrics["maintainability_score"] = 75  # Default score if mutation testing not run

        return metrics

    def _generate_recommendations(self) -> list[dict[str, Any]]:
        """Generate recommendations based on test results."""
        recommendations = []

        # Check for failed test suites
        failed_suites = [name for name, result in self.results.items() if not result.success]
        if failed_suites:
            recommendations.append(
                {
                    "type": "test_failures",
                    "priority": "high",
                    "title": "Fix Failed Test Suites",
                    "description": f"The following test suites failed: {', '.join(failed_suites)}",
                    "action": "Review test failures and fix underlying issues",
                    "impact": "high",
                }
            )

        # Check coverage thresholds
        for name, result in self.results.items():
            if result.coverage_percentage > 0 and result.coverage_percentage < 80:
                recommendations.append(
                    {
                        "type": "coverage",
                        "priority": "medium",
                        "title": f"Improve Coverage for {name}",
                        "description": f"Coverage is {result.coverage_percentage:.1f}%, below 80% threshold",
                        "action": "Add more comprehensive tests",
                        "impact": "medium",
                    }
                )

        # Check for long-running tests
        slow_suites = [name for name, result in self.results.items() if result.duration > 600]  # 10 minutes
        if slow_suites:
            recommendations.append(
                {
                    "type": "performance",
                    "priority": "low",
                    "title": "Optimize Slow Test Suites",
                    "description": f"The following suites are slow: {', '.join(slow_suites)}",
                    "action": "Optimize test performance or consider parallelization",
                    "impact": "low",
                }
            )

        return recommendations

    def _collect_artifacts(self) -> list[str]:
        """Collect all test artifacts."""
        artifacts = []

        for result in self.results.values():
            artifacts.extend(result.artifacts)

        # Add generated reports
        report_dir = self.config["reporting"]["output_directory"]
        if os.path.exists(report_dir):
            for format_type in self.config["reporting"]["formats"]:
                artifact_path = f"{report_dir}/comprehensive-report.{format_type}"
                if os.path.exists(artifact_path):
                    artifacts.append(artifact_path)

        return artifacts

    async def _generate_reports(self, report: dict[str, Any]):
        """Generate reports in configured formats."""
        report_dir = Path(self.config["reporting"]["output_directory"])
        report_dir.mkdir(parents=True, exist_ok=True)

        for format_type in self.config["reporting"]["formats"]:
            if format_type == "json":
                async with aiofiles.open(report_dir / "comprehensive-report.json", "w") as f:
                    await f.write(json.dumps(report, indent=2, default=str))

            elif format_type == "html":
                html_content = self._generate_html_report(report)
                async with aiofiles.open(report_dir / "comprehensive-report.html", "w") as f:
                    await f.write(html_content)

            elif format_type == "junit":
                junit_content = self._generate_junit_report(report)
                async with aiofiles.open(report_dir / "comprehensive-report.xml", "w") as f:
                    await f.write(junit_content)

    def _generate_html_report(self, report: dict[str, Any]) -> str:
        """Generate HTML report."""
        summary = report["execution_summary"]

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ATP Comprehensive Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .success {{ color: #28a745; }}
        .failure {{ color: #dc3545; }}
        .warning {{ color: #ffc107; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .recommendation {{ margin: 10px 0; padding: 10px; border-left: 4px solid #007bff; background: #f8f9fa; }}
        .high-priority {{ border-left-color: #dc3545; }}
    </style>
</head>
<body>
    <h1>ATP Comprehensive Test Report</h1>
    
    <div class="summary">
        <h2>Execution Summary</h2>
        <div class="metric"><strong>Total Duration:</strong> {summary["total_duration"]:.2f}s</div>
        <div class="metric"><strong>Test Suites:</strong> {summary["total_suites"]}</div>
        <div class="metric"><strong>Suite Success Rate:</strong> {summary["suite_success_rate"]:.1f}%</div>
        <div class="metric"><strong>Total Tests:</strong> {summary["total_tests"]}</div>
        <div class="metric"><strong>Test Success Rate:</strong> {summary["test_success_rate"]:.1f}%</div>
        <div class="metric"><strong>Average Coverage:</strong> {summary["average_coverage"]:.1f}%</div>
    </div>
    
    <h2>Test Suite Results</h2>
    <table>
        <tr>
            <th>Suite</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Tests</th>
            <th>Coverage</th>
        </tr>
"""

        for suite_name, result in report["suite_results"].items():
            status_class = "success" if result["success"] else "failure"
            status_text = "PASSED" if result["success"] else "FAILED"

            html += f"""
        <tr>
            <td>{suite_name}</td>
            <td class="{status_class}">{status_text}</td>
            <td>{result["duration"]:.2f}s</td>
            <td>{result["tests_passed"]}/{result["tests_run"]}</td>
            <td>{result["coverage_percentage"]:.1f}%</td>
        </tr>
"""

        html += """
    </table>
    
    <h2>Quality Metrics</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Score</th>
        </tr>
"""

        for metric_name, metric_value in report["quality_metrics"].items():
            if isinstance(metric_value, dict):
                for sub_metric, sub_value in metric_value.items():
                    html += f"""
        <tr>
            <td>{metric_name.replace("_", " ").title()} - {sub_metric.replace("_", " ").title()}</td>
            <td>{sub_value:.1f}%</td>
        </tr>
"""
            else:
                html += f"""
        <tr>
            <td>{metric_name.replace("_", " ").title()}</td>
            <td>{metric_value:.1f}%</td>
        </tr>
"""

        html += """
    </table>
    
    <h2>Recommendations</h2>
"""

        for rec in report["recommendations"]:
            priority_class = "high-priority" if rec["priority"] == "high" else ""
            html += f"""
    <div class="recommendation {priority_class}">
        <strong>{rec["title"]}</strong> (Priority: {rec["priority"]})<br>
        {rec["description"]}<br>
        <em>Action: {rec["action"]}</em>
    </div>
"""

        html += """
</body>
</html>
"""

        return html

    def _generate_junit_report(self, report: dict[str, Any]) -> str:
        """Generate JUnit XML report."""
        from xml.dom import minidom
        from xml.etree.ElementTree import Element, SubElement, tostring

        testsuites = Element("testsuites")
        testsuites.set("name", "ATP Comprehensive Tests")
        testsuites.set("tests", str(report["execution_summary"]["total_tests"]))
        testsuites.set("failures", str(report["execution_summary"]["total_failed"]))
        testsuites.set("time", str(report["execution_summary"]["total_duration"]))

        for suite_name, result in report["suite_results"].items():
            testsuite = SubElement(testsuites, "testsuite")
            testsuite.set("name", suite_name)
            testsuite.set("tests", str(result["tests_run"]))
            testsuite.set("failures", str(result["tests_failed"]))
            testsuite.set("time", str(result["duration"]))

            # Add a test case for the suite
            testcase = SubElement(testsuite, "testcase")
            testcase.set("name", f"{suite_name}_execution")
            testcase.set("classname", f"ATP.{suite_name}")
            testcase.set("time", str(result["duration"]))

            if not result["success"]:
                failure = SubElement(testcase, "failure")
                failure.set("message", result.get("error_message", "Test suite failed"))
                failure.text = result.get("error_message", "")

        # Pretty print XML
        rough_string = tostring(testsuites, "utf-8")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    async def _send_notifications(self, report: dict[str, Any]):
        """Send notifications about test results."""
        webhook_url = self.config["global_settings"].get("notification_webhook")

        if not webhook_url:
            return

        # Prepare notification payload
        summary = report["execution_summary"]
        failed_suites = [name for name, result in report["suite_results"].items() if not result["success"]]

        payload = {
            "text": "ATP Test Execution Complete",
            "attachments": [
                {
                    "color": "danger" if failed_suites else "good",
                    "fields": [
                        {"title": "Duration", "value": f"{summary['total_duration']:.2f}s", "short": True},
                        {
                            "title": "Suite Success Rate",
                            "value": f"{summary['suite_success_rate']:.1f}%",
                            "short": True,
                        },
                        {"title": "Test Success Rate", "value": f"{summary['test_success_rate']:.1f}%", "short": True},
                        {"title": "Coverage", "value": f"{summary['average_coverage']:.1f}%", "short": True},
                    ],
                }
            ],
        }

        if failed_suites:
            payload["attachments"][0]["fields"].append(
                {"title": "Failed Suites", "value": ", ".join(failed_suites), "short": False}
            )

        # Send notification
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        self.logger.info("Notification sent successfully")
                    else:
                        self.logger.warning(f"Failed to send notification: {response.status}")
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")


async def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="ATP Test Orchestrator")
    parser.add_argument("--config", default="tests/config/test_orchestration.yaml", help="Configuration file")
    parser.add_argument("--suites", nargs="+", help="Specific test suites to run")
    parser.add_argument("--parallel", action="store_true", help="Run suites in parallel where possible")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--output", help="Output file for results")

    args = parser.parse_args()

    orchestrator = TestOrchestrator(args.config)

    try:
        report = await orchestrator.run_all_tests(
            suite_filter=args.suites, parallel=args.parallel, fail_fast=args.fail_fast
        )

        # Print summary
        summary = report["execution_summary"]
        print("\n" + "=" * 60)
        print("ATP COMPREHENSIVE TEST EXECUTION SUMMARY")
        print("=" * 60)
        print(f"Total Duration: {summary['total_duration']:.2f}s")
        print(f"Test Suites: {summary['passed_suites']}/{summary['total_suites']} passed")
        print(f"Individual Tests: {summary['total_passed']}/{summary['total_tests']} passed")
        print(f"Average Coverage: {summary['average_coverage']:.1f}%")

        # Print failed suites
        failed_suites = [name for name, result in report["suite_results"].items() if not result["success"]]
        if failed_suites:
            print(f"\nFailed Suites: {', '.join(failed_suites)}")

        # Print recommendations
        if report["recommendations"]:
            print(f"\nRecommendations: {len(report['recommendations'])}")
            for rec in report["recommendations"][:3]:  # Show top 3
                print(f"  - {rec['title']} ({rec['priority']} priority)")

        # Save results if requested
        if args.output:
            async with aiofiles.open(args.output, "w") as f:
                await f.write(json.dumps(report, indent=2, default=str))
            print(f"\nDetailed results saved to: {args.output}")

        # Exit with appropriate code
        exit_code = 0 if summary["failed_suites"] == 0 else 1
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error during test execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
