#!/usr/bin/env python3
"""
Tests for runbook validation and linting.
"""

import os
import tempfile
from pathlib import Path

from tools.runbook_linter import RunbookLinter


class TestRunbookLinter:
    """Test cases for the runbook linter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.linter = RunbookLinter(".")  # Path doesn't matter for unit tests

    def test_find_sections_complete_runbook(self):
        """Test finding sections in a complete runbook."""
        content = """# Test Runbook

## Description
This is a test runbook.

## Prerequisites
- Access to system
- Admin privileges

## Steps
1. Do something
2. Do another thing

## Verification
Check that it worked.

## Contacts
- Primary: Team A

## References
- Doc 1
- Doc 2
"""
        sections = self.linter._find_sections(content)
        expected = {"description", "prerequisites", "steps", "verification", "contacts", "references"}
        assert sections == expected

    def test_find_sections_missing_sections(self):
        """Test finding sections when some are missing."""
        content = """# Test Runbook

## Description
This is a test runbook.

## Steps
1. Do something
"""
        sections = self.linter._find_sections(content)
        expected = {"description", "steps"}
        assert sections == expected

    def test_validate_section_order_good_order(self):
        """Test section order validation with correct order."""
        content = """# Test Runbook

## Description
Desc

## Prerequisites
Pre

## Steps
Steps

## Verification
Verify
"""
        assert self.linter._validate_section_order(content)

    def test_validate_section_order_bad_order(self):
        """Test section order validation with incorrect order."""
        content = """# Test Runbook

## Steps
Steps

## Description
Desc
"""
        assert not self.linter._validate_section_order(content)

    def test_lint_runbook_complete(self):
        """Test linting a complete runbook."""
        content = """# Complete Test Runbook

## Description
This runbook is complete.

## Prerequisites
- Access required

## Steps
1. Step one
2. Step two

## Verification
Verify success.

## Contacts
- Team: ops@company.com

## References
- https://example.com
"""
        # Reset linter state
        self.linter.errors = []
        self.linter.warnings = []

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            temp_path = f.name

        try:
            result = self.linter.lint_runbook(Path(temp_path))
            assert result
            assert len(self.linter.errors) == 0
        finally:
            # Close any open file handles first
            import time

            time.sleep(0.1)  # Small delay to ensure file handles are released
            try:
                os.unlink(temp_path)
            except PermissionError:
                pass  # Ignore permission errors on Windows

    def test_lint_runbook_missing_title(self):
        """Test linting a runbook missing a title."""
        content = """## Description
Missing title runbook.

## Prerequisites
- Access

## Steps
1. Step

## Verification
Verify

## Contacts
Team

## References
None
"""
        # Reset linter state
        self.linter.errors = []
        self.linter.warnings = []

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            temp_path = f.name

        try:
            result = self.linter.lint_runbook(Path(temp_path))
            assert not result
            assert any("Missing title" in error for error in self.linter.errors)
        finally:
            import time

            time.sleep(0.1)
            try:
                os.unlink(temp_path)
            except PermissionError:
                pass

    def test_lint_runbook_missing_required_section(self):
        """Test linting a runbook missing a required section."""
        content = """# Missing Section Runbook

## Description
Missing prerequisites.

## Steps
1. Step

## Verification
Verify

## Contacts
Team

## References
None
"""
        # Reset linter state
        self.linter.errors = []
        self.linter.warnings = []

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            temp_path = f.name

        try:
            result = self.linter.lint_runbook(Path(temp_path))
            assert not result
            assert any("Missing required sections" in error for error in self.linter.errors)
        finally:
            import time

            time.sleep(0.1)
            try:
                os.unlink(temp_path)
            except PermissionError:
                pass


def test_runbook_template_exists():
    """Test that the standard runbook template exists."""
    template_path = Path("runbooks/templates/standard_runbook.md")
    assert template_path.exists()

    content = template_path.read_text()
    assert "# [Runbook Title]" in content
    assert "## Description" in content
    assert "## Prerequisites" in content
    assert "## Steps" in content
    assert "## Verification" in content
    assert "## Contacts" in content
    assert "## References" in content


def test_runbook_directories_exist():
    """Test that runbook directories exist."""
    directories = [
        "runbooks",
        "runbooks/templates",
        "runbooks/incident_response",
        "runbooks/maintenance",
        "runbooks/emergency",
    ]

    for directory in directories:
        assert Path(directory).exists(), f"Directory {directory} does not exist"


def test_runbook_linter_executable():
    """Test that the runbook linter is executable."""
    linter_path = Path("tools/runbook_linter.py")
    assert linter_path.exists()

    # Check that it's a valid Python file by reading with explicit encoding
    with open(linter_path, encoding="utf-8") as f:
        content = f.read()
    assert "def main():" in content
    assert "if __name__ == '__main__':" in content
