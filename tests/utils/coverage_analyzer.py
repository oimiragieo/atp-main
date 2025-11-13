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
Test Coverage Analyzer
Advanced test coverage analysis and reporting for enterprise components.
"""

import ast
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

import coverage

logger = logging.getLogger(__name__)


@dataclass
class CoverageMetrics:
    """Coverage metrics for a file or module."""

    lines_total: int
    lines_covered: int
    lines_missing: list[int]
    branches_total: int
    branches_covered: int
    branches_missing: list[tuple[int, int]]
    coverage_percentage: float
    branch_coverage_percentage: float


@dataclass
class FunctionCoverage:
    """Coverage metrics for a specific function."""

    name: str
    line_start: int
    line_end: int
    lines_covered: int
    lines_total: int
    coverage_percentage: float
    is_tested: bool


@dataclass
class ClassCoverage:
    """Coverage metrics for a specific class."""

    name: str
    line_start: int
    line_end: int
    methods: list[FunctionCoverage]
    lines_covered: int
    lines_total: int
    coverage_percentage: float


class CoverageAnalyzer:
    """Advanced coverage analyzer for ATP codebase."""

    def __init__(self, source_dirs: list[str] = None):
        """Initialize coverage analyzer."""
        self.source_dirs = source_dirs or ["router_service", "metrics", "observability", "monitoring", "integrations"]
        self.coverage_data = {}
        self.ast_cache = {}

    def analyze_coverage(self, coverage_file: str = ".coverage") -> dict[str, Any]:
        """Analyze test coverage comprehensively."""
        # Load coverage data
        cov = coverage.Coverage(data_file=coverage_file)
        cov.load()

        analysis_results = {
            "overall_metrics": self._calculate_overall_metrics(cov),
            "file_metrics": self._analyze_file_coverage(cov),
            "function_metrics": self._analyze_function_coverage(cov),
            "class_metrics": self._analyze_class_coverage(cov),
            "complexity_analysis": self._analyze_complexity_coverage(cov),
            "critical_gaps": self._identify_critical_gaps(cov),
            "recommendations": self._generate_recommendations(cov),
        }

        return analysis_results

    def _calculate_overall_metrics(self, cov: coverage.Coverage) -> dict[str, Any]:
        """Calculate overall coverage metrics."""
        total_lines = 0
        covered_lines = 0
        total_branches = 0
        covered_branches = 0

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                analysis = cov.analysis2(filename)
                total_lines += len(analysis.statements)
                covered_lines += len(analysis.statements) - len(analysis.missing)

                # Branch coverage if available
                if hasattr(analysis, "branch_lines"):
                    total_branches += len(analysis.branch_lines())
                    covered_branches += len(analysis.branch_lines()) - len(analysis.missing_branch_lines())

        line_coverage = (covered_lines / total_lines * 100) if total_lines > 0 else 0
        branch_coverage = (covered_branches / total_branches * 100) if total_branches > 0 else 0

        return {
            "line_coverage": line_coverage,
            "branch_coverage": branch_coverage,
            "total_lines": total_lines,
            "covered_lines": covered_lines,
            "missing_lines": total_lines - covered_lines,
            "total_branches": total_branches,
            "covered_branches": covered_branches,
            "missing_branches": total_branches - covered_branches,
        }

    def _analyze_file_coverage(self, cov: coverage.Coverage) -> dict[str, CoverageMetrics]:
        """Analyze coverage for each file."""
        file_metrics = {}

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                analysis = cov.analysis2(filename)

                lines_total = len(analysis.statements)
                lines_covered = lines_total - len(analysis.missing)
                coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 0

                # Branch coverage
                branches_total = 0
                branches_covered = 0
                branches_missing = []

                if hasattr(analysis, "branch_lines"):
                    branch_lines = analysis.branch_lines()
                    branches_total = len(branch_lines)
                    missing_branches = analysis.missing_branch_lines()
                    branches_covered = branches_total - len(missing_branches)
                    branches_missing = list(missing_branches)

                branch_coverage_pct = (branches_covered / branches_total * 100) if branches_total > 0 else 0

                file_metrics[filename] = CoverageMetrics(
                    lines_total=lines_total,
                    lines_covered=lines_covered,
                    lines_missing=list(analysis.missing),
                    branches_total=branches_total,
                    branches_covered=branches_covered,
                    branches_missing=branches_missing,
                    coverage_percentage=coverage_pct,
                    branch_coverage_percentage=branch_coverage_pct,
                )

        return file_metrics

    def _analyze_function_coverage(self, cov: coverage.Coverage) -> dict[str, list[FunctionCoverage]]:
        """Analyze coverage for each function."""
        function_metrics = {}

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                functions = self._extract_functions_from_file(filename)
                analysis = cov.analysis2(filename)

                file_functions = []
                for func_name, line_start, line_end in functions:
                    func_lines = set(range(line_start, line_end + 1))
                    statement_lines = set(analysis.statements)
                    missing_lines = set(analysis.missing)

                    func_statements = func_lines.intersection(statement_lines)
                    func_missing = func_lines.intersection(missing_lines)

                    lines_total = len(func_statements)
                    lines_covered = lines_total - len(func_missing)
                    coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 100

                    file_functions.append(
                        FunctionCoverage(
                            name=func_name,
                            line_start=line_start,
                            line_end=line_end,
                            lines_covered=lines_covered,
                            lines_total=lines_total,
                            coverage_percentage=coverage_pct,
                            is_tested=coverage_pct > 0,
                        )
                    )

                function_metrics[filename] = file_functions

        return function_metrics

    def _analyze_class_coverage(self, cov: coverage.Coverage) -> dict[str, list[ClassCoverage]]:
        """Analyze coverage for each class."""
        class_metrics = {}

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                classes = self._extract_classes_from_file(filename)
                analysis = cov.analysis2(filename)

                file_classes = []
                for class_name, line_start, line_end, methods in classes:
                    class_lines = set(range(line_start, line_end + 1))
                    statement_lines = set(analysis.statements)
                    missing_lines = set(analysis.missing)

                    class_statements = class_lines.intersection(statement_lines)
                    class_missing = class_lines.intersection(missing_lines)

                    lines_total = len(class_statements)
                    lines_covered = lines_total - len(class_missing)
                    coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 100

                    # Analyze method coverage
                    method_coverages = []
                    for method_name, method_start, method_end in methods:
                        method_lines = set(range(method_start, method_end + 1))
                        method_statements = method_lines.intersection(statement_lines)
                        method_missing = method_lines.intersection(missing_lines)

                        method_lines_total = len(method_statements)
                        method_lines_covered = method_lines_total - len(method_missing)
                        method_coverage_pct = (
                            (method_lines_covered / method_lines_total * 100) if method_lines_total > 0 else 100
                        )

                        method_coverages.append(
                            FunctionCoverage(
                                name=method_name,
                                line_start=method_start,
                                line_end=method_end,
                                lines_covered=method_lines_covered,
                                lines_total=method_lines_total,
                                coverage_percentage=method_coverage_pct,
                                is_tested=method_coverage_pct > 0,
                            )
                        )

                    file_classes.append(
                        ClassCoverage(
                            name=class_name,
                            line_start=line_start,
                            line_end=line_end,
                            methods=method_coverages,
                            lines_covered=lines_covered,
                            lines_total=lines_total,
                            coverage_percentage=coverage_pct,
                        )
                    )

                class_metrics[filename] = file_classes

        return class_metrics

    def _analyze_complexity_coverage(self, cov: coverage.Coverage) -> dict[str, Any]:
        """Analyze coverage vs complexity correlation."""
        complexity_analysis = {
            "high_complexity_low_coverage": [],
            "complexity_coverage_correlation": {},
            "risk_assessment": {},
        }

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                complexity_data = self._calculate_cyclomatic_complexity(filename)
                analysis = cov.analysis2(filename)

                lines_total = len(analysis.statements)
                lines_covered = lines_total - len(analysis.missing)
                coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 0

                # Identify high complexity, low coverage functions
                for func_name, complexity in complexity_data.items():
                    if complexity > 10 and coverage_pct < 80:
                        complexity_analysis["high_complexity_low_coverage"].append(
                            {
                                "file": filename,
                                "function": func_name,
                                "complexity": complexity,
                                "coverage": coverage_pct,
                                "risk_score": complexity * (100 - coverage_pct) / 100,
                            }
                        )

                complexity_analysis["complexity_coverage_correlation"][filename] = {
                    "avg_complexity": sum(complexity_data.values()) / len(complexity_data) if complexity_data else 0,
                    "coverage_percentage": coverage_pct,
                    "total_functions": len(complexity_data),
                }

        return complexity_analysis

    def _identify_critical_gaps(self, cov: coverage.Coverage) -> list[dict[str, Any]]:
        """Identify critical coverage gaps."""
        critical_gaps = []

        for filename in cov.get_data().measured_files():
            if self._should_include_file(filename):
                analysis = cov.analysis2(filename)

                lines_total = len(analysis.statements)
                lines_covered = lines_total - len(analysis.missing)
                coverage_pct = (lines_covered / lines_total * 100) if lines_total > 0 else 0

                # Identify critical files with low coverage
                if coverage_pct < 70 and self._is_critical_file(filename):
                    critical_gaps.append(
                        {
                            "file": filename,
                            "coverage_percentage": coverage_pct,
                            "missing_lines": len(analysis.missing),
                            "total_lines": lines_total,
                            "criticality": self._assess_file_criticality(filename),
                            "priority": "high" if coverage_pct < 50 else "medium",
                        }
                    )

                # Identify untested functions in critical files
                functions = self._extract_functions_from_file(filename)
                for func_name, line_start, line_end in functions:
                    func_lines = set(range(line_start, line_end + 1))
                    statement_lines = set(analysis.statements)
                    missing_lines = set(analysis.missing)

                    func_statements = func_lines.intersection(statement_lines)
                    func_missing = func_lines.intersection(missing_lines)

                    if len(func_statements) > 0 and len(func_missing) == len(func_statements):
                        critical_gaps.append(
                            {
                                "file": filename,
                                "function": func_name,
                                "coverage_percentage": 0,
                                "lines": f"{line_start}-{line_end}",
                                "criticality": self._assess_function_criticality(filename, func_name),
                                "priority": "high",
                            }
                        )

        return sorted(critical_gaps, key=lambda x: x.get("criticality", 0), reverse=True)

    def _generate_recommendations(self, cov: coverage.Coverage) -> list[dict[str, Any]]:
        """Generate coverage improvement recommendations."""
        recommendations = []

        overall_metrics = self._calculate_overall_metrics(cov)

        # Overall coverage recommendations
        if overall_metrics["line_coverage"] < 80:
            recommendations.append(
                {
                    "type": "overall_coverage",
                    "priority": "high",
                    "title": "Improve Overall Test Coverage",
                    "description": f"Current line coverage is {overall_metrics['line_coverage']:.1f}%. Target is 80%+.",
                    "action": "Add tests for uncovered code paths",
                    "impact": "high",
                }
            )

        if overall_metrics["branch_coverage"] < 70:
            recommendations.append(
                {
                    "type": "branch_coverage",
                    "priority": "medium",
                    "title": "Improve Branch Coverage",
                    "description": f"Current branch coverage is {overall_metrics['branch_coverage']:.1f}%. Target is 70%+.",
                    "action": "Add tests for conditional branches and edge cases",
                    "impact": "medium",
                }
            )

        # File-specific recommendations
        file_metrics = self._analyze_file_coverage(cov)
        low_coverage_files = [
            (filename, metrics)
            for filename, metrics in file_metrics.items()
            if metrics.coverage_percentage < 70 and self._is_critical_file(filename)
        ]

        for filename, metrics in low_coverage_files[:5]:  # Top 5 priority files
            recommendations.append(
                {
                    "type": "file_coverage",
                    "priority": "high" if metrics.coverage_percentage < 50 else "medium",
                    "title": f"Improve Coverage for {os.path.basename(filename)}",
                    "description": f"File has {metrics.coverage_percentage:.1f}% coverage with {len(metrics.lines_missing)} uncovered lines.",
                    "action": f"Add tests covering lines: {', '.join(map(str, metrics.lines_missing[:10]))}{'...' if len(metrics.lines_missing) > 10 else ''}",
                    "impact": "high" if self._is_critical_file(filename) else "medium",
                    "file": filename,
                }
            )

        # Function-specific recommendations
        function_metrics = self._analyze_function_coverage(cov)
        untested_functions = []

        for filename, functions in function_metrics.items():
            for func in functions:
                if not func.is_tested and self._is_critical_file(filename):
                    untested_functions.append((filename, func))

        for filename, func in untested_functions[:10]:  # Top 10 priority functions
            recommendations.append(
                {
                    "type": "function_coverage",
                    "priority": "medium",
                    "title": f"Add Tests for {func.name}()",
                    "description": f"Function {func.name} in {os.path.basename(filename)} has no test coverage.",
                    "action": f"Create unit tests for {func.name}() covering lines {func.line_start}-{func.line_end}",
                    "impact": "medium",
                    "file": filename,
                    "function": func.name,
                }
            )

        return recommendations

    def _should_include_file(self, filename: str) -> bool:
        """Check if file should be included in coverage analysis."""
        # Include files from source directories
        for source_dir in self.source_dirs:
            if source_dir in filename:
                return True

        # Exclude test files, migrations, etc.
        exclude_patterns = ["/test_", "_test.py", "/tests/", "__pycache__", "/migrations/", "/venv/", "/.venv/"]

        for pattern in exclude_patterns:
            if pattern in filename:
                return False

        return False

    def _is_critical_file(self, filename: str) -> bool:
        """Determine if a file is critical for the system."""
        critical_patterns = [
            "router_service/service.py",
            "router_service/choose_model.py",
            "metrics/registry.py",
            "observability/tracing.py",
            "monitoring/alert_manager.py",
            "/api/",
            "/core/",
            "/security/",
        ]

        for pattern in critical_patterns:
            if pattern in filename:
                return True

        return False

    def _assess_file_criticality(self, filename: str) -> int:
        """Assess file criticality on a scale of 1-10."""
        if "router_service/service.py" in filename:
            return 10
        elif "router_service/" in filename:
            return 8
        elif any(comp in filename for comp in ["metrics", "observability", "monitoring"]):
            return 7
        elif "integrations" in filename:
            return 5
        else:
            return 3

    def _assess_function_criticality(self, filename: str, function_name: str) -> int:
        """Assess function criticality on a scale of 1-10."""
        base_criticality = self._assess_file_criticality(filename)

        # Boost criticality for important function types
        if any(keyword in function_name.lower() for keyword in ["route", "select", "choose"]):
            return min(10, base_criticality + 2)
        elif any(keyword in function_name.lower() for keyword in ["auth", "security", "validate"]):
            return min(10, base_criticality + 1)
        elif function_name.startswith("_"):
            return max(1, base_criticality - 2)

        return base_criticality

    def _extract_functions_from_file(self, filename: str) -> list[tuple[str, int, int]]:
        """Extract function definitions from a Python file."""
        if filename in self.ast_cache:
            return self.ast_cache[filename]["functions"]

        try:
            with open(filename, encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            functions = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append((node.name, node.lineno, node.end_lineno or node.lineno))

            if filename not in self.ast_cache:
                self.ast_cache[filename] = {}
            self.ast_cache[filename]["functions"] = functions

            return functions
        except Exception:
            return []

    def _extract_classes_from_file(self, filename: str) -> list[tuple[str, int, int, list[tuple[str, int, int]]]]:
        """Extract class definitions and their methods from a Python file."""
        if filename in self.ast_cache and "classes" in self.ast_cache[filename]:
            return self.ast_cache[filename]["classes"]

        try:
            with open(filename, encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            methods.append((item.name, item.lineno, item.end_lineno or item.lineno))

                    classes.append((node.name, node.lineno, node.end_lineno or node.lineno, methods))

            if filename not in self.ast_cache:
                self.ast_cache[filename] = {}
            self.ast_cache[filename]["classes"] = classes

            return classes
        except Exception:
            return []

    def _calculate_cyclomatic_complexity(self, filename: str) -> dict[str, int]:
        """Calculate cyclomatic complexity for functions in a file."""
        try:
            # Use radon or similar tool to calculate complexity
            result = subprocess.run(["radon", "cc", filename, "-j"], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                complexity_data = {}

                for file_data in data.values():
                    for item in file_data:
                        if item["type"] == "function":
                            complexity_data[item["name"]] = item["complexity"]

                return complexity_data
        except Exception as e:
            logger.debug(f"Complexity calculation failed for {filename}: {e}")

        # Fallback: simple complexity estimation
        functions = self._extract_functions_from_file(filename)
        return {func_name: 1 for func_name, _, _ in functions}

    def generate_html_report(self, analysis_results: dict[str, Any], output_file: str):
        """Generate HTML coverage report."""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ATP Test Coverage Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .high {{ color: #28a745; }}
        .medium {{ color: #ffc107; }}
        .low {{ color: #dc3545; }}
        .recommendation {{ margin: 10px 0; padding: 10px; border-left: 4px solid #007bff; background: #f8f9fa; }}
        .critical {{ border-left-color: #dc3545; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .progress {{ width: 100px; height: 20px; background: #e9ecef; border-radius: 3px; }}
        .progress-bar {{ height: 100%; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>ATP Test Coverage Report</h1>
    
    <div class="summary">
        <h2>Overall Coverage</h2>
        <div class="metric"><strong>Line Coverage:</strong> {analysis_results["overall_metrics"]["line_coverage"]:.1f}%</div>
        <div class="metric"><strong>Branch Coverage:</strong> {analysis_results["overall_metrics"]["branch_coverage"]:.1f}%</div>
        <div class="metric"><strong>Total Lines:</strong> {analysis_results["overall_metrics"]["total_lines"]}</div>
        <div class="metric"><strong>Covered Lines:</strong> {analysis_results["overall_metrics"]["covered_lines"]}</div>
    </div>
    
    <h2>File Coverage</h2>
    <table>
        <tr>
            <th>File</th>
            <th>Coverage</th>
            <th>Lines</th>
            <th>Missing</th>
            <th>Branches</th>
        </tr>
"""

        for filename, metrics in analysis_results["file_metrics"].items():
            coverage_class = (
                "high"
                if metrics.coverage_percentage >= 80
                else "medium"
                if metrics.coverage_percentage >= 60
                else "low"
            )
            html_content += f"""
        <tr>
            <td>{os.path.basename(filename)}</td>
            <td class="{coverage_class}">{metrics.coverage_percentage:.1f}%</td>
            <td>{metrics.lines_covered}/{metrics.lines_total}</td>
            <td>{len(metrics.lines_missing)}</td>
            <td>{metrics.branch_coverage_percentage:.1f}%</td>
        </tr>
"""

        html_content += """
    </table>
    
    <h2>Critical Coverage Gaps</h2>
"""

        for gap in analysis_results["critical_gaps"][:10]:
            priority_class = "critical" if gap["priority"] == "high" else ""
            html_content += f"""
    <div class="recommendation {priority_class}">
        <strong>{gap.get("function", os.path.basename(gap["file"]))}</strong><br>
        Coverage: {gap["coverage_percentage"]:.1f}% | Priority: {gap["priority"]} | Criticality: {gap["criticality"]}
    </div>
"""

        html_content += """
    <h2>Recommendations</h2>
"""

        for rec in analysis_results["recommendations"][:15]:
            priority_class = "critical" if rec["priority"] == "high" else ""
            html_content += f"""
    <div class="recommendation {priority_class}">
        <strong>{rec["title"]}</strong><br>
        {rec["description"]}<br>
        <em>Action: {rec["action"]}</em>
    </div>
"""

        html_content += """
</body>
</html>
"""

        with open(output_file, "w") as f:
            f.write(html_content)

    def export_json_report(self, analysis_results: dict[str, Any], output_file: str):
        """Export coverage analysis as JSON."""
        # Convert dataclasses to dictionaries for JSON serialization
        json_results = {}

        for key, value in analysis_results.items():
            if key == "file_metrics":
                json_results[key] = {
                    filename: {
                        "lines_total": metrics.lines_total,
                        "lines_covered": metrics.lines_covered,
                        "lines_missing": metrics.lines_missing,
                        "coverage_percentage": metrics.coverage_percentage,
                        "branch_coverage_percentage": metrics.branch_coverage_percentage,
                    }
                    for filename, metrics in value.items()
                }
            elif key in ["function_metrics", "class_metrics"]:
                json_results[key] = {
                    filename: [
                        {
                            "name": item.name,
                            "line_start": item.line_start,
                            "line_end": item.line_end,
                            "coverage_percentage": item.coverage_percentage,
                            "is_tested": getattr(item, "is_tested", True),
                        }
                        for item in items
                    ]
                    for filename, items in value.items()
                }
            else:
                json_results[key] = value

        with open(output_file, "w") as f:
            json.dump(json_results, f, indent=2)


def main():
    """Main function for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="ATP Coverage Analyzer")
    parser.add_argument("--coverage-file", default=".coverage", help="Coverage data file")
    parser.add_argument("--html-report", help="Generate HTML report")
    parser.add_argument("--json-report", help="Generate JSON report")
    parser.add_argument("--source-dirs", nargs="+", help="Source directories to analyze")

    args = parser.parse_args()

    analyzer = CoverageAnalyzer(source_dirs=args.source_dirs)
    results = analyzer.analyze_coverage(args.coverage_file)

    # Print summary
    print("ATP Test Coverage Analysis")
    print("=" * 50)
    print(f"Line Coverage: {results['overall_metrics']['line_coverage']:.1f}%")
    print(f"Branch Coverage: {results['overall_metrics']['branch_coverage']:.1f}%")
    print(f"Critical Gaps: {len(results['critical_gaps'])}")
    print(f"Recommendations: {len(results['recommendations'])}")

    if args.html_report:
        analyzer.generate_html_report(results, args.html_report)
        print(f"HTML report generated: {args.html_report}")

    if args.json_report:
        analyzer.export_json_report(results, args.json_report)
        print(f"JSON report generated: {args.json_report}")


if __name__ == "__main__":
    main()
