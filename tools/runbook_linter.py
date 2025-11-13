#!/usr/bin/env python3
"""
Runbook Linter

Validates runbook files for required sections and formatting.
"""

import re
import sys
from pathlib import Path


class RunbookLinter:
    """Linter for runbook markdown files."""

    REQUIRED_SECTIONS = {"description", "prerequisites", "steps", "verification", "contacts", "references"}

    OPTIONAL_SECTIONS = {"rollback"}

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def lint_runbook(self, file_path: Path) -> bool:
        """Lint a single runbook file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.errors.append(f"Failed to read {file_path}: {e}")
            return False

        # Check for title
        if not re.search(r"^#\s+.+", content, re.MULTILINE):
            self.errors.append(f"{file_path}: Missing title (H1 header)")

        # Check for required sections
        found_sections = self._find_sections(content)
        missing_required = self.REQUIRED_SECTIONS - found_sections
        if missing_required:
            self.errors.append(f"{file_path}: Missing required sections: {', '.join(missing_required)}")

        # Check section order (basic validation)
        if not self._validate_section_order(content):
            self.warnings.append(f"{file_path}: Sections may not be in standard order")

        return len(self.errors) == 0

    def _find_sections(self, content: str) -> set[str]:
        """Find all sections in the content."""
        sections = set()
        # Look for H2 headers (## Section Name)
        for match in re.finditer(r"^##\s+(.+)", content, re.MULTILINE):
            section_name = match.group(1).strip().lower()
            # Normalize section names
            if "description" in section_name:
                sections.add("description")
            elif "prerequisites" in section_name or "prereq" in section_name:
                sections.add("prerequisites")
            elif "step" in section_name:
                sections.add("steps")
            elif "verification" in section_name or "verify" in section_name:
                sections.add("verification")
            elif "rollback" in section_name:
                sections.add("rollback")
            elif "contact" in section_name:
                sections.add("contacts")
            elif "reference" in section_name:
                sections.add("references")

        return sections

    def _validate_section_order(self, content: str) -> bool:
        """Validate that sections appear in a logical order."""
        lines = content.split("\n")
        section_order = []
        for line in lines:
            if line.startswith("## "):
                section = line[3:].strip().lower()
                section_order.append(section)

        # Expected order (flexible)
        expected_patterns = [
            ["description", "prerequisites", "steps"],
            ["description", "prerequisites", "steps", "verification"],
        ]

        for pattern in expected_patterns:
            if all(s in section_order for s in pattern):
                return True

        return False

    def lint_directory(self, directory: Path) -> bool:
        """Lint all runbook files in a directory."""
        success = True
        for file_path in directory.rglob("*.md"):
            if file_path.name == "README.md":
                continue  # Skip README files
            if not self.lint_runbook(file_path):
                success = False
        return success

    def run(self) -> int:
        """Run the linter on the runbooks directory."""
        if not self.base_path.exists():
            print(f"Error: {self.base_path} does not exist")
            return 1

        print(f"Linting runbooks in {self.base_path}")

        # Lint all subdirectories
        for subdir in ["incident_response", "maintenance", "emergency"]:
            dir_path = self.base_path / subdir
            if dir_path.exists():
                print(f"Checking {subdir}...")
                self.lint_directory(dir_path)

        # Report results
        if self.errors:
            print("\nErrors:")
            for error in self.errors:
                print(f"  ❌ {error}")

        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")

        if not self.errors and not self.warnings:
            print("✅ All runbooks passed validation!")
            return 0
        elif self.errors:
            print(f"\n❌ Found {len(self.errors)} errors")
            return 1
        else:
            print(f"\n⚠️  Found {len(self.warnings)} warnings")
            return 0


def main():
    if len(sys.argv) != 2:
        print("Usage: python runbook_linter.py <runbooks_directory>")
        sys.exit(1)

    linter = RunbookLinter(sys.argv[1])
    sys.exit(linter.run())


if __name__ == "__main__":
    main()
