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
Mutation Testing Configuration
Configuration for mutation testing to validate test quality and coverage.
"""

# Mutation testing configuration for mutmut
MUTMUT_CONFIG = {
    # Paths to mutate
    "paths_to_mutate": ["router_service/", "metrics/", "observability/", "monitoring/", "integrations/"],
    # Paths to exclude from mutation
    "paths_to_exclude": ["tests/", "__pycache__/", ".git/", "venv/", ".venv/", "node_modules/", "build/", "dist/"],
    # Test command to run
    "test_command": "python -m pytest tests/ -x --tb=short",
    # Mutation operators to use
    "operators": [
        "arithmetic",  # +, -, *, /, //, %, **
        "comparison",  # <, <=, >, >=, ==, !=
        "logical",  # and, or, not
        "assignment",  # +=, -=, *=, /=, //=, %=, **=
        "unary",  # +x, -x
        "subscript",  # a[0] -> a[1]
        "slice",  # a[1:3] -> a[2:4]
        "decorator",  # @decorator removal
        "keyword",  # True/False, None
        "number",  # 0 -> 1, 1 -> 0, 2 -> 3
        "string",  # "a" -> "XX"
    ],
    # Minimum mutation score threshold
    "minimum_mutation_score": 80.0,
    # Maximum number of mutations to test (0 = unlimited)
    "max_mutations": 1000,
    # Timeout for each test run (seconds)
    "test_timeout": 300,
    # Parallel execution
    "parallel_processes": 4,
    # Files to always exclude
    "exclude_files": [
        "**/test_*.py",
        "**/*_test.py",
        "**/conftest.py",
        "**/__init__.py",
        "**/setup.py",
        "**/migrations/*.py",
    ],
    # Specific functions/methods to exclude
    "exclude_functions": ["__str__", "__repr__", "__eq__", "__hash__", "to_dict", "from_dict", "__init__"],
}

# Custom mutation operators for ATP-specific code
CUSTOM_MUTATIONS = {
    # HTTP status codes
    "http_status": {"200": ["201", "202", "204"], "400": ["401", "403", "404"], "500": ["502", "503", "504"]},
    # Common ATP constants
    "atp_constants": {
        "0.1": ["0.2", "0.5", "1.0"],
        "1000": ["100", "500", "2000"],
        "60": ["30", "120", "300"],
        "3600": ["1800", "7200", "86400"],
    },
    # Model names
    "model_names": {
        "gpt-4": ["gpt-3.5-turbo", "claude-3"],
        "gpt-3.5-turbo": ["gpt-4", "claude-3"],
        "claude-3": ["gpt-4", "gpt-3.5-turbo"],
    },
    # Provider names
    "providers": {
        "openai": ["anthropic", "google"],
        "anthropic": ["openai", "google"],
        "google": ["openai", "anthropic"],
    },
}


def should_mutate_line(line: str, file_path: str) -> bool:
    """
    Determine if a line should be mutated.

    Args:
        line: The line of code to potentially mutate
        file_path: Path to the file containing the line

    Returns:
        True if the line should be mutated, False otherwise
    """
    # Skip comments and docstrings
    stripped = line.strip()
    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
        return False

    # Skip logging statements
    if "logger." in line or "logging." in line:
        return False

    # Skip import statements
    if stripped.startswith("import ") or stripped.startswith("from "):
        return False

    # Skip configuration constants
    if "CONFIG" in line.upper() or "SETTINGS" in line.upper():
        return False

    # Skip test files
    if "test_" in file_path or "_test.py" in file_path:
        return False

    return True


def get_mutation_priority(file_path: str) -> int:
    """
    Get mutation priority for a file (higher = more important to test).

    Args:
        file_path: Path to the file

    Returns:
        Priority score (1-10)
    """
    # Core business logic gets highest priority
    if "router_service" in file_path:
        return 10

    # Enterprise features get high priority
    if any(component in file_path for component in ["metrics", "observability", "monitoring"]):
        return 8

    # Integrations get medium priority
    if "integrations" in file_path:
        return 6

    # Utilities get lower priority
    if "utils" in file_path or "helpers" in file_path:
        return 4

    # Default priority
    return 5


def generate_mutation_report(results: dict) -> str:
    """
    Generate a comprehensive mutation testing report.

    Args:
        results: Mutation testing results

    Returns:
        Formatted report string
    """
    total_mutations = results.get("total_mutations", 0)
    killed_mutations = results.get("killed_mutations", 0)
    survived_mutations = results.get("survived_mutations", 0)
    timeout_mutations = results.get("timeout_mutations", 0)

    if total_mutations == 0:
        mutation_score = 0
    else:
        mutation_score = (killed_mutations / total_mutations) * 100

    report = f"""
# Mutation Testing Report

## Summary
- **Total Mutations**: {total_mutations}
- **Killed Mutations**: {killed_mutations}
- **Survived Mutations**: {survived_mutations}
- **Timeout Mutations**: {timeout_mutations}
- **Mutation Score**: {mutation_score:.2f}%

## Analysis
"""

    if mutation_score >= MUTMUT_CONFIG["minimum_mutation_score"]:
        report += f"✅ **PASSED**: Mutation score ({mutation_score:.2f}%) meets minimum threshold ({MUTMUT_CONFIG['minimum_mutation_score']}%)\n\n"
    else:
        report += f"❌ **FAILED**: Mutation score ({mutation_score:.2f}%) below minimum threshold ({MUTMUT_CONFIG['minimum_mutation_score']}%)\n\n"

    # Add recommendations
    if survived_mutations > 0:
        report += "## Recommendations\n"
        report += f"- {survived_mutations} mutations survived, indicating potential gaps in test coverage\n"
        report += "- Review the survived mutations to identify missing test cases\n"
        report += "- Consider adding more edge case tests\n"
        report += "- Ensure all code paths are tested\n\n"

    if timeout_mutations > 0:
        report += f"- {timeout_mutations} mutations caused timeouts, consider optimizing test performance\n\n"

    # Add file-specific analysis
    if "file_results" in results:
        report += "## File Analysis\n"
        for file_path, file_results in results["file_results"].items():
            file_score = (file_results["killed"] / file_results["total"]) * 100 if file_results["total"] > 0 else 0
            status = "✅" if file_score >= MUTMUT_CONFIG["minimum_mutation_score"] else "❌"
            report += (
                f"- {status} `{file_path}`: {file_score:.1f}% ({file_results['killed']}/{file_results['total']})\n"
            )

    return report


# Pytest configuration for mutation testing
PYTEST_MUTATION_CONFIG = {
    "addopts": ["--tb=short", "--strict-markers", "--disable-warnings", "-q"],
    "testpaths": ["tests"],
    "python_files": ["test_*.py", "*_test.py"],
    "python_classes": ["Test*"],
    "python_functions": ["test_*"],
    "markers": [
        "unit: Unit tests",
        "integration: Integration tests",
        "mutation: Mutation tests",
        "slow: Slow running tests",
    ],
}

# Coverage configuration for mutation testing
COVERAGE_CONFIG = {
    "source": ["router_service", "metrics", "observability", "monitoring", "integrations"],
    "omit": ["*/tests/*", "*/test_*", "*/__pycache__/*", "*/migrations/*", "*/venv/*", "*/.venv/*"],
    "exclude_lines": [
        "pragma: no cover",
        "def __repr__",
        "def __str__",
        "raise AssertionError",
        "raise NotImplementedError",
        "if __name__ == .__main__.:",
        "if TYPE_CHECKING:",
        "@abstract",
    ],
    "show_missing": True,
    "skip_covered": False,
    "precision": 2,
}
