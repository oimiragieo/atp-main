#!/usr/bin/env python3
"""
Enterprise Cleanup - File Classification Engine

This module scans the entire codebase and classifies files based on their
production relevance, type, and cleanup requirements.
"""

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class FileClassification:
    """Classification result for a single file."""

    file_path: str
    category: str  # 'core', 'dev', 'test', 'config', 'doc', 'temp', 'debug'
    subcategory: str
    production_relevance: int  # 1-10 scale
    security_risk: int  # 1-10 scale
    file_size: int
    last_modified: str
    dependencies: list[str]
    cleanup_action: str  # 'keep', 'remove', 'relocate', 'refactor'
    target_path: str | None = None
    reason: str = ""


class FileClassifier:
    """Main file classification engine."""

    def __init__(self, root_path: str = "."):
        self.root_path = Path(root_path).resolve()
        self.classifications: list[FileClassification] = []

        # Define file patterns for different categories
        self.debug_patterns = [
            "debug_*.py",
            "temp_*.py",
            "*.tmp",
            "*_debug.py",
            "test_debug_*.py",
            "debug*.log",
            "*.debug",
        ]

        self.temp_patterns = [
            "temp_*.py",
            "*.tmp",
            "*.temp",
            "*_temp.*",
            "temporary_*",
            "scratch_*",
            "*.bak",
            "*.backup",
        ]

        self.test_patterns = [
            "test_*.py",
            "*_test.py",
            "tests/*.py",
            "test/*.py",
            "*.test.js",
            "*.test.ts",
            "*.spec.js",
            "*.spec.ts",
        ]

        self.config_patterns = [
            "*.yml",
            "*.yaml",
            "*.json",
            "*.toml",
            "*.ini",
            "*.env",
            "*.conf",
            "*.config",
            "Dockerfile*",
            "docker-compose*.yml",
            "*.tf",
            "*.tfvars",
        ]

        self.doc_patterns = [
            "*.md",
            "*.rst",
            "*.txt",
            "*.pdf",
            "docs/*",
            "README*",
            "CHANGELOG*",
            "LICENSE*",
            "CONTRIBUTING*",
        ]

        self.core_service_patterns = [
            "router_service/*.py",
            "memory-gateway/*.py",
            "adapters/*/adapter.py",
            "services/*/*.py",
        ]

        # Security risk patterns
        self.secret_patterns = [
            r"sk-[a-zA-Z0-9]{48}",  # OpenAI API keys
            r"AIza[0-9A-Za-z-_]{35}",  # Google API keys
            r'password\s*=\s*["\'][^"\']+["\']',  # Hardcoded passwords
            r'secret\s*=\s*["\'][^"\']+["\']',  # Hardcoded secrets
            r'token\s*=\s*["\'][^"\']+["\']',  # Hardcoded tokens
            r'api_key\s*=\s*["\'][^"\']+["\']',  # API keys
        ]

        # Directories to skip
        self.skip_dirs = {
            "__pycache__",
            ".git",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".hypothesis",
            ".build_cache",
            "node_modules",
            ".vscode",
            ".idea",
            "venv",
            "env",
            ".env",
        }

        # Files to skip
        self.skip_files = {".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.pyd"}

    def scan_codebase(self) -> dict[str, any]:
        """Scan the entire codebase and classify all files."""
        print(f"Scanning codebase from: {self.root_path}")

        total_files = 0
        processed_files = 0

        for root, dirs, files in os.walk(self.root_path):
            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]

            for file in files:
                total_files += 1
                file_path = Path(root) / file
                relative_path = file_path.relative_to(self.root_path)

                # Skip certain files
                if any(fnmatch.fnmatch(file, pattern) for pattern in self.skip_files):
                    continue

                try:
                    classification = self._classify_file(relative_path)
                    self.classifications.append(classification)
                    processed_files += 1

                    if processed_files % 100 == 0:
                        print(f"Processed {processed_files}/{total_files} files...")

                except Exception as e:
                    print(f"Error processing {relative_path}: {e}")

        print(f"Classification complete: {processed_files} files processed")
        return self._generate_report()

    def _classify_file(self, file_path: Path) -> FileClassification:
        """Classify a single file."""
        full_path = self.root_path / file_path
        str_path = str(file_path)

        # Get file stats
        stat = full_path.stat()
        file_size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # Determine category and subcategory
        category, subcategory = self._determine_category(str_path)

        # Calculate production relevance
        production_relevance = self._calculate_production_relevance(str_path, category)

        # Calculate security risk
        security_risk = self._calculate_security_risk(full_path, str_path)

        # Find dependencies
        dependencies = self._find_dependencies(full_path)

        # Determine cleanup action
        cleanup_action, target_path, reason = self._determine_cleanup_action(
            str_path, category, production_relevance, security_risk
        )

        return FileClassification(
            file_path=str_path,
            category=category,
            subcategory=subcategory,
            production_relevance=production_relevance,
            security_risk=security_risk,
            file_size=file_size,
            last_modified=last_modified,
            dependencies=dependencies,
            cleanup_action=cleanup_action,
            target_path=target_path,
            reason=reason,
        )

    def _determine_category(self, file_path: str) -> tuple[str, str]:
        """Determine the category and subcategory of a file."""

        # Debug files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.debug_patterns):
            return "debug", "debug_utility"

        # Temporary files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.temp_patterns):
            return "temp", "temporary_file"

        # Test files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.test_patterns):
            if "poc" in file_path.lower() or "experiment" in file_path.lower():
                return "test", "poc_test"
            return "test", "production_test"

        # Configuration files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.config_patterns):
            if "example" in file_path.lower() or "sample" in file_path.lower():
                return "config", "example_config"
            return "config", "production_config"

        # Documentation files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.doc_patterns):
            return "doc", "documentation"

        # Core service files
        if any(fnmatch.fnmatch(file_path, pattern) for pattern in self.core_service_patterns):
            return "core", "service"

        # Python files
        if file_path.endswith(".py"):
            if "router_service" in file_path or "memory-gateway" in file_path:
                return "core", "service"
            elif "adapters" in file_path:
                return "core", "adapter"
            elif "tools" in file_path or "scripts" in file_path:
                return "dev", "utility"
            else:
                return "dev", "misc_python"

        # JavaScript/TypeScript files
        if file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
            if "sdk" in file_path:
                return "core", "sdk"
            return "dev", "frontend"

        # Default category
        return "dev", "misc"

    def _calculate_production_relevance(self, file_path: str, category: str) -> int:
        """Calculate production relevance score (1-10)."""

        # Core services are highly relevant
        if category == "core":
            return 10

        # Debug and temp files are not relevant
        if category in ["debug", "temp"]:
            return 1

        # Production configs are highly relevant
        if category == "config" and "production" in file_path.lower():
            return 9

        # Example configs are less relevant
        if category == "config" and ("example" in file_path.lower() or "sample" in file_path.lower()):
            return 3

        # Production tests are moderately relevant
        if category == "test" and "poc" not in file_path.lower():
            return 6

        # POC tests are not relevant
        if category == "test" and "poc" in file_path.lower():
            return 2

        # Documentation is moderately relevant
        if category == "doc":
            if any(keyword in file_path.lower() for keyword in ["deployment", "production", "api"]):
                return 7
            return 5

        # Development utilities are less relevant
        if category == "dev":
            return 4

        return 5  # Default

    def _calculate_security_risk(self, full_path: Path, file_path: str) -> int:
        """Calculate security risk score (1-10)."""
        risk_score = 1

        try:
            if full_path.is_file() and full_path.suffix in [".py", ".js", ".ts", ".yml", ".yaml", ".json", ".env"]:
                content = full_path.read_text(encoding="utf-8", errors="ignore")

                # Check for secret patterns
                for pattern in self.secret_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        risk_score = max(risk_score, 9)

                # Check for other security risks
                if "password" in content.lower() and "=" in content:
                    risk_score = max(risk_score, 7)

                if "secret" in content.lower() and "=" in content:
                    risk_score = max(risk_score, 7)

                if "localhost" in content.lower() or "127.0.0.1" in content:
                    risk_score = max(risk_score, 4)

                # Test files with realistic data
                if "test" in file_path.lower() and any(
                    keyword in content.lower() for keyword in ["email", "phone", "address"]
                ):
                    risk_score = max(risk_score, 6)

        except Exception:
            pass  # Ignore files that can't be read

        return risk_score

    def _find_dependencies(self, full_path: Path) -> list[str]:
        """Find dependencies for a file."""
        dependencies = []

        try:
            if full_path.suffix == ".py":
                content = full_path.read_text(encoding="utf-8", errors="ignore")

                # Find import statements
                import_pattern = r"^(?:from\s+(\S+)\s+import|import\s+(\S+))"
                for match in re.finditer(import_pattern, content, re.MULTILINE):
                    module = match.group(1) or match.group(2)
                    if module and not module.startswith("."):
                        dependencies.append(module.split(".")[0])

        except Exception:
            pass

        return list(set(dependencies))

    def _determine_cleanup_action(
        self, file_path: str, category: str, production_relevance: int, security_risk: int
    ) -> tuple[str, str | None, str]:
        """Determine what cleanup action to take for a file."""

        # Remove debug and temp files
        if category in ["debug", "temp"]:
            return "remove", None, "Debug/temporary file not needed for production"

        # Remove high security risk files
        if security_risk >= 8:
            return "remove", None, f"High security risk (score: {security_risk})"

        # Remove low relevance files
        if production_relevance <= 2:
            return "remove", None, f"Low production relevance (score: {production_relevance})"

        # Relocate POC and experimental files
        if "poc" in file_path.lower() or "experiment" in file_path.lower():
            target = f"research/poc/{file_path}"
            return "relocate", target, "POC/experimental code should be archived"

        # Relocate development utilities
        if category == "dev" and ("tool" in file_path.lower() or "script" in file_path.lower()):
            target = f"tools/dev/{Path(file_path).name}"
            return "relocate", target, "Development utility should be organized"

        # Refactor mixed files
        if security_risk >= 5 and production_relevance >= 7:
            return "refactor", None, "Contains security risks but needed for production"

        # Keep core files
        if category == "core" or production_relevance >= 8:
            return "keep", None, "Essential for production"

        # Default action
        return "keep", None, "Default keep action"

    def _generate_report(self) -> dict[str, any]:
        """Generate comprehensive analysis report."""

        # Count by category
        category_counts = {}
        for classification in self.classifications:
            category = classification.category
            category_counts[category] = category_counts.get(category, 0) + 1

        # Count by cleanup action
        action_counts = {}
        for classification in self.classifications:
            action = classification.cleanup_action
            action_counts[action] = action_counts.get(action, 0) + 1

        # Calculate total file size
        total_size = sum(c.file_size for c in self.classifications)
        remove_size = sum(c.file_size for c in self.classifications if c.cleanup_action == "remove")

        # Find high-risk files
        high_risk_files = [c for c in self.classifications if c.security_risk >= 7]

        # Find files to remove
        files_to_remove = [c for c in self.classifications if c.cleanup_action == "remove"]

        # Find files to relocate
        files_to_relocate = [c for c in self.classifications if c.cleanup_action == "relocate"]

        report = {
            "scan_timestamp": datetime.now().isoformat(),
            "total_files": len(self.classifications),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "category_breakdown": category_counts,
            "cleanup_actions": action_counts,
            "estimated_size_reduction": {
                "bytes": remove_size,
                "mb": round(remove_size / (1024 * 1024), 2),
                "percentage": round((remove_size / total_size) * 100, 1) if total_size > 0 else 0,
            },
            "high_risk_files": len(high_risk_files),
            "files_to_remove": len(files_to_remove),
            "files_to_relocate": len(files_to_relocate),
            "detailed_classifications": [asdict(c) for c in self.classifications],
        }

        return report

    def save_report(self, output_file: str = "cleanup_analysis.json"):
        """Save the analysis report to a JSON file."""
        report = self._generate_report()

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Analysis report saved to: {output_path}")
        return report

    def print_summary(self):
        """Print a summary of the analysis."""
        report = self._generate_report()

        print("\n" + "=" * 60)
        print("ENTERPRISE CLEANUP - CODEBASE ANALYSIS SUMMARY")
        print("=" * 60)

        print(f"Total files analyzed: {report['total_files']}")
        print(f"Total size: {report['total_size_mb']} MB")

        print("\nFiles by category:")
        for category, count in sorted(report["category_breakdown"].items()):
            print(f"  {category}: {count}")

        print("\nCleanup actions:")
        for action, count in sorted(report["cleanup_actions"].items()):
            print(f"  {action}: {count}")

        print("\nEstimated cleanup benefits:")
        print(f"  Files to remove: {report['files_to_remove']}")
        print(
            f"  Size reduction: {report['estimated_size_reduction']['mb']} MB ({report['estimated_size_reduction']['percentage']}%)"
        )
        print(f"  High-risk files found: {report['high_risk_files']}")

        print("\n" + "=" * 60)


def main():
    """Main execution function."""
    classifier = FileClassifier()

    print("Starting enterprise cleanup analysis...")
    classifier.scan_codebase()

    # Save detailed report
    report = classifier.save_report("tools/cleanup/cleanup_analysis.json")

    # Print summary
    classifier.print_summary()

    # Save files to remove list
    files_to_remove = [c["file_path"] for c in report["detailed_classifications"] if c["cleanup_action"] == "remove"]

    with open("tools/cleanup/files_to_remove.txt", "w") as f:
        for file_path in sorted(files_to_remove):
            f.write(f"{file_path}\n")

    print("\nFiles to remove list saved to: tools/cleanup/files_to_remove.txt")

    # Save files to relocate list
    files_to_relocate = [
        (c["file_path"], c["target_path"])
        for c in report["detailed_classifications"]
        if c["cleanup_action"] == "relocate" and c["target_path"]
    ]

    with open("tools/cleanup/files_to_relocate.txt", "w") as f:
        for source, target in sorted(files_to_relocate):
            f.write(f"{source} -> {target}\n")

    print("Files to relocate list saved to: tools/cleanup/files_to_relocate.txt")


if __name__ == "__main__":
    main()
