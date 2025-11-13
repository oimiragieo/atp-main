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
Comprehensive Test Runner for ATP Platform
Orchestrates all types of testing including unit, integration, E2E, performance, and security tests.
"""
import asyncio
import argparse
import logging
import os
import subprocess
import sys
import time
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
import concurrent.futures

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestSuite:
    """Test suite configuration."""
    
    def __init__(self, name: str, description: str, command: List[str], timeout: int = 300):
        self.name = name
        self.description = description
        self.command = command
        self.timeout = timeout
        self.result = None
        self.duration = 0
        self.output = ""
        self.error_output = ""

class ATPTestRunner:
    """Comprehensive test runner for ATP platform."""
    
    def __init__(self):
        self.test_suites: Dict[str, TestSuite] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
        self.start_time = 0
        self.end_time = 0
        
        # Initialize test suites
        self._initialize_test_suites()
    
    def _initialize_test_suites(self):
        """Initialize all test suites."""
        # Unit tests
        self.test_suites["unit"] = TestSuite(
            name="Unit Tests",
            description="Fast unit tests for individual components",
            command=["python", "-m", "pytest", "tests/unit/", "-v", "--tb=short", "--durations=10"],
            timeout=300
        )
        
        # Integration tests
        self.test_suites["integration"] = TestSuite(
            name="Integration Tests",
            description="Integration tests with external dependencies",
            command=["python", "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
            timeout=600
        )
        
        # E2E tests
        self.test_suites["e2e"] = TestSuite(
            name="End-to-End Tests",
            description="End-to-end tests using Playwright",
            command=["python", "-m", "pytest", "tests/e2e/", "-v", "--tb=short"],
            timeout=1200
        )
        
        # Performance tests
        self.test_suites["performance"] = TestSuite(
            name="Performance Tests",
            description="K6 performance and load tests",
            command=["k6", "run", "tests/performance/k6_load_tests.js"],
            timeout=900
        )
        
        # Security tests
        self.test_suites["security"] = TestSuite(
            name="Security Tests",
            description="Security and penetration tests",
            command=["python", "-m", "pytest", "tests/security/", "-v", "--tb=short"],
            timeout=600
        )
        
        # Mutation tests
        self.test_suites["mutation"] = TestSuite(
            name="Mutation Tests",
            description="Mutation testing to validate test quality",
            command=["mutmut", "run", "--paths-to-mutate", "router_service,metrics,observability"],
            timeout=3600
        )
        
        # Static analysis
        self.test_suites["static"] = TestSuite(
            name="Static Analysis",
            description="Static code analysis and linting",
            command=["python", "-m", "pytest", "tests/static/", "-v"],
            timeout=300
        )
        
        # Compliance tests
        self.test_suites["compliance"] = TestSuite(
            name="Compliance Tests",
            description="GDPR, SOC 2, and ISO 27001 compliance tests",
            command=["python", "-m", "pytest", "tests/security/", "-k", "compliance", "-v"],
            timeout=300
        )
    
    async def run_test_suite(self, suite_name: str) -> Dict[str, Any]:
        """Run a specific test suite."""
        if suite_name not in self.test_suites:
            raise ValueError(f"Test suite '{suite_name}' not found")
        
        suite = self.test_suites[suite_name]
        logger.info(f"Running {suite.name}: {suite.description}")
        
        start_time = time.time()
        
        try:
            # Run the test command
            process = await asyncio.create_subprocess_exec(
                *suite.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=suite.timeout
                )
                
                suite.output = stdout.decode('utf-8')
                suite.error_output = stderr.decode('utf-8')
                suite.result = process.returncode == 0
                
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                suite.result = False
                suite.error_output = f"Test suite timed out after {suite.timeout} seconds"
                
        except Exception as e:
            suite.result = False
            suite.error_output = str(e)
        
        suite.duration = time.time() - start_time
        
        # Store results
        result = {
            "name": suite.name,
            "description": suite.description,
            "success": suite.result,
            "duration": suite.duration,
            "output": suite.output,
            "error_output": suite.error_output,
            "command": " ".join(suite.command)
        }
        
        self.results[suite_name] = result
        
        status = "PASSED" if suite.result else "FAILED"
        logger.info(f"{suite.name} {status} in {suite.duration:.2f}s")
        
        return result
    
    async def run_all_tests(self, parallel: bool = False, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run all test suites."""
        exclude = exclude or []
        suites_to_run = [name for name in self.test_suites.keys() if name not in exclude]
        
        logger.info(f"Running {len(suites_to_run)} test suites: {', '.join(suites_to_run)}")
        
        self.start_time = time.time()
        
        if parallel:
            # Run test suites in parallel
            tasks = [self.run_test_suite(suite_name) for suite_name in suites_to_run]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    suite_name = suites_to_run[i]
                    self.results[suite_name] = {
                        "name": self.test_suites[suite_name].name,
                        "success": False,
                        "error": str(result),
                        "duration": 0
                    }
        else:
            # Run test suites sequentially
            for suite_name in suites_to_run:
                await self.run_test_suite(suite_name)
        
        self.end_time = time.time()
        
        return self.generate_summary()
    
    def run_specific_tests(self, test_types: List[str]) -> Dict[str, Any]:
        """Run specific test types."""
        logger.info(f"Running specific test types: {', '.join(test_types)}")
        
        self.start_time = time.time()
        
        # Run tests sequentially for specific types
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for test_type in test_types:
                if test_type in self.test_suites:
                    loop.run_until_complete(self.run_test_suite(test_type))
                else:
                    logger.warning(f"Test type '{test_type}' not found")
        finally:
            loop.close()
        
        self.end_time = time.time()
        
        return self.generate_summary()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test execution summary."""
        total_duration = self.end_time - self.start_time
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result.get("success", False))
        failed_tests = total_tests - passed_tests
        
        summary = {
            "execution_summary": {
                "total_duration": total_duration,
                "total_test_suites": total_tests,
                "passed_suites": passed_tests,
                "failed_suites": failed_tests,
                "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                "start_time": self.start_time,
                "end_time": self.end_time
            },
            "test_results": self.results,
            "recommendations": self._generate_recommendations()
        }
        
        return summary
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        # Check for failed test suites
        failed_suites = [name for name, result in self.results.items() if not result.get("success", False)]
        
        if failed_suites:
            recommendations.append(f"Fix failing test suites: {', '.join(failed_suites)}")
        
        # Check for slow test suites
        slow_suites = [
            name for name, result in self.results.items()
            if result.get("duration", 0) > 300  # 5 minutes
        ]
        
        if slow_suites:
            recommendations.append(f"Optimize slow test suites: {', '.join(slow_suites)}")
        
        # Check for security issues
        if "security" in self.results and not self.results["security"].get("success", False):
            recommendations.append("Address security test failures immediately")
        
        # Check for performance issues
        if "performance" in self.results and not self.results["performance"].get("success", False):
            recommendations.append("Investigate performance test failures")
        
        if not recommendations:
            recommendations.append("All tests passed successfully!")
        
        return recommendations
    
    def export_results(self, output_file: str, format_type: str = "json"):
        """Export test results to file."""
        summary = self.generate_summary()
        
        if format_type == "json":
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
        elif format_type == "html":
            html_content = self._generate_html_report(summary)
            with open(output_file, 'w') as f:
                f.write(html_content)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
        
        logger.info(f"Test results exported to {output_file}")
    
    def _generate_html_report(self, summary: Dict[str, Any]) -> str:
        """Generate HTML test report."""
        execution_summary = summary["execution_summary"]
        test_results = summary["test_results"]
        recommendations = summary["recommendations"]
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ATP Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .test-suite {{ margin: 15px 0; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        .passed {{ border-left: 5px solid #28a745; }}
        .failed {{ border-left: 5px solid #dc3545; }}
        .recommendations {{ background: #fff3cd; padding: 15px; border-radius: 5px; }}
        pre {{ background: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
    </style>
</head>
<body>
    <h1>ATP Platform Test Report</h1>
    
    <div class="summary">
        <h2>Execution Summary</h2>
        <div class="metric"><strong>Total Duration:</strong> {execution_summary['total_duration']:.2f}s</div>
        <div class="metric"><strong>Test Suites:</strong> {execution_summary['total_test_suites']}</div>
        <div class="metric"><strong>Passed:</strong> {execution_summary['passed_suites']}</div>
        <div class="metric"><strong>Failed:</strong> {execution_summary['failed_suites']}</div>
        <div class="metric"><strong>Success Rate:</strong> {execution_summary['success_rate']:.1f}%</div>
    </div>
    
    <h2>Test Suite Results</h2>
"""
        
        for suite_name, result in test_results.items():
            status_class = "passed" if result.get("success", False) else "failed"
            status_text = "PASSED" if result.get("success", False) else "FAILED"
            
            html += f"""
    <div class="test-suite {status_class}">
        <h3>{result['name']} - {status_text}</h3>
        <p>{result['description']}</p>
        <p><strong>Duration:</strong> {result['duration']:.2f}s</p>
        <p><strong>Command:</strong> <code>{result['command']}</code></p>
        
        {f'<details><summary>Output</summary><pre>{result["output"]}</pre></details>' if result.get("output") else ""}
        {f'<details><summary>Error Output</summary><pre>{result["error_output"]}</pre></details>' if result.get("error_output") else ""}
    </div>
"""
        
        if recommendations:
            html += f"""
    <div class="recommendations">
        <h2>Recommendations</h2>
        <ul>
            {''.join(f'<li>{rec}</li>' for rec in recommendations)}
        </ul>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        return html


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="ATP Platform Test Runner")
    parser.add_argument(
        "--suites",
        nargs="+",
        choices=["unit", "integration", "e2e", "performance", "security", "mutation", "static", "compliance"],
        help="Test suites to run (default: all except mutation)"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run test suites in parallel"
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=["mutation"],  # Exclude mutation tests by default (they're slow)
        help="Test suites to exclude"
    )
    parser.add_argument(
        "--output",
        help="Output file for test results"
    )
    parser.add_argument(
        "--format",
        choices=["json", "html"],
        default="json",
        help="Output format"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize test runner
    runner = ATPTestRunner()
    
    try:
        if args.suites:
            # Run specific test suites
            summary = runner.run_specific_tests(args.suites)
        else:
            # Run all tests (with exclusions)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                summary = loop.run_until_complete(
                    runner.run_all_tests(parallel=args.parallel, exclude=args.exclude)
                )
            finally:
                loop.close()
        
        # Print summary
        print("\n" + "="*60)
        print("TEST EXECUTION SUMMARY")
        print("="*60)
        
        exec_summary = summary["execution_summary"]
        print(f"Total Duration: {exec_summary['total_duration']:.2f}s")
        print(f"Test Suites: {exec_summary['total_test_suites']}")
        print(f"Passed: {exec_summary['passed_suites']}")
        print(f"Failed: {exec_summary['failed_suites']}")
        print(f"Success Rate: {exec_summary['success_rate']:.1f}%")
        
        # Print failed suites
        failed_suites = [
            name for name, result in summary["test_results"].items()
            if not result.get("success", False)
        ]
        
        if failed_suites:
            print(f"\nFailed Suites: {', '.join(failed_suites)}")
        
        # Print recommendations
        if summary["recommendations"]:
            print("\nRecommendations:")
            for rec in summary["recommendations"]:
                print(f"  - {rec}")
        
        # Export results if requested
        if args.output:
            runner.export_results(args.output, args.format)
        
        # Exit with appropriate code
        exit_code = 0 if exec_summary["failed_suites"] == 0 else 1
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()