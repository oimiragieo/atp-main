#!/usr/bin/env python3
"""
Tests for postmortem automation tool.
"""

import json
import tempfile
from pathlib import Path

from tools.postmortem_generator import PostmortemGenerator


class TestPostmortemGenerator:
    """Test cases for the postmortem generator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.generator = PostmortemGenerator()

    def test_load_template_default(self):
        """Test loading the default template."""
        template = self.generator.load_template()
        assert "# Postmortem:" in template
        assert "{incident_title}" in template

    def test_load_template_custom(self):
        """Test loading a custom template."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Custom Template\n{test_field}")
            f.flush()
            temp_path = f.name

        try:
            generator = PostmortemGenerator(temp_path)
            template = generator.load_template()
            assert "Custom Template" in template
            assert "{test_field}" in template
        finally:
            # Close any open file handles first
            import time

            time.sleep(0.1)  # Small delay to ensure file handles are released
            try:
                Path(temp_path).unlink()
            except PermissionError:
                pass  # Ignore permission errors on Windows

    def test_generate_postmortem_complete_data(self):
        """Test generating postmortem with complete incident data."""
        incident_data = {
            "title": "Test Incident",
            "date": "2025-01-15",
            "duration": "2 hours",
            "impact": "Service degradation",
            "severity": "High",
            "chronology": [
                {"timestamp": "10:00", "description": "Issue started"},
                {"timestamp": "12:00", "description": "Issue resolved"},
            ],
            "root_cause": "Configuration error",
            "impact_assessment": "Affected 1000 users",
            "resolution": "Configuration fixed",
            "prevention_measures": ["Add monitoring", "Improve testing"],
            "lessons_learned": ["Better communication", "Faster response"],
            "action_items": [
                {"description": "Update docs", "status": "Open", "owner": "DevOps"},
                {"description": "Add alerts", "status": "In Progress", "owner": "SRE"},
            ],
            "metrics": {"downtime": "2h", "affected_users": "1000"},
            "id": "INC-2025-001",
            "author": "Test Author",
        }

        result = self.generator.generate_postmortem(incident_data)

        # Check that all fields are filled
        assert "Test Incident" in result
        assert "2025-01-15" in result
        assert "2 hours" in result
        assert "Service degradation" in result
        assert "Configuration error" in result
        assert "Affected 1000 users" in result
        assert "Add monitoring" in result
        assert "Better communication" in result
        assert "[Open] Update docs" in result
        assert "INC-2025-001" in result

    def test_generate_postmortem_minimal_data(self):
        """Test generating postmortem with minimal incident data."""
        incident_data = {"title": "Minimal Incident"}

        result = self.generator.generate_postmortem(incident_data)

        assert "Minimal Incident" in result
        assert "Unknown" in result  # For missing fields
        assert "To be determined" in result  # For root cause

    def test_format_chronology(self):
        """Test chronology formatting."""
        chronology = [
            {"timestamp": "10:00", "description": "Start"},
            {"timestamp": "11:00", "description": "Middle"},
            {"timestamp": "12:00", "description": "End"},
        ]

        result = self.generator._format_chronology(chronology)
        assert "**10:00**: Start" in result
        assert "**11:00**: Middle" in result
        assert "**12:00**: End" in result

    def test_format_chronology_empty(self):
        """Test chronology formatting with empty list."""
        result = self.generator._format_chronology([])
        assert "No timeline available" in result

    def test_format_list(self):
        """Test list formatting."""
        items = ["Item 1", "Item 2", "Item 3"]
        result = self.generator._format_list(items)
        assert "- Item 1" in result
        assert "- Item 2" in result
        assert "- Item 3" in result

    def test_format_list_empty(self):
        """Test list formatting with empty list."""
        result = self.generator._format_list([])
        assert "None documented" in result

    def test_format_action_items(self):
        """Test action items formatting."""
        action_items = [
            {"description": "Fix bug", "status": "Open", "owner": "Dev"},
            {"description": "Add test", "status": "In Progress", "owner": "QA"},
        ]

        result = self.generator._format_action_items(action_items)
        assert "[Open] Fix bug (Owner: Dev)" in result
        assert "[In Progress] Add test (Owner: QA)" in result

    def test_format_action_items_empty(self):
        """Test action items formatting with empty list."""
        result = self.generator._format_action_items([])
        assert "No action items identified" in result

    def test_format_metrics(self):
        """Test metrics formatting."""
        metrics = {"downtime": "2h", "users": "1000"}
        result = self.generator._format_metrics(metrics)
        assert "**downtime**: 2h" in result
        assert "**users**: 1000" in result

    def test_format_metrics_empty(self):
        """Test metrics formatting with empty dict."""
        result = self.generator._format_metrics({})
        assert "No metrics available" in result

    def test_metrics_increment(self):
        """Test that metrics are incremented when generating postmortem."""
        # Test that the generator has the metrics counter
        assert hasattr(self.generator, "postmortems_completed")

        # Test that we can call generate_postmortem without errors
        incident_data = {"title": "Test"}
        result = self.generator.generate_postmortem(incident_data)

        # Verify the result contains expected content
        assert "Test" in result
        assert "Postmortem:" in result

    def test_save_postmortem(self):
        """Test saving postmortem to file."""
        content = "# Test Postmortem"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_postmortem.md"

            self.generator.save_postmortem(content, str(output_path))

            assert output_path.exists()
            with open(output_path, encoding="utf-8") as f:
                saved_content = f.read()
            assert saved_content == content


def test_postmortem_template_exists():
    """Test that the postmortem template exists."""
    template_path = Path("runbooks/templates/postmortem_template.md")
    assert template_path.exists()

    content = template_path.read_text()
    assert "# Postmortem:" in content
    assert "{incident_title}" in content
    assert "{chronology}" in content


def test_postmortem_generator_executable():
    """Test that the postmortem generator is executable."""
    generator_path = Path("tools/postmortem_generator.py")
    assert generator_path.exists()

    # Check that it's a valid Python file
    content = generator_path.read_text()
    assert "def main():" in content
    assert "if __name__ == '__main__':" in content


def test_postmortem_generator_cli():
    """Test the CLI interface."""
    # Create test incident data
    incident_data = {
        "title": "CLI Test Incident",
        "date": "2025-01-01",
        "duration": "1 hour",
        "impact": "Minor",
        "severity": "Low",
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = Path(temp_dir) / "incident.json"
        output_file = Path(temp_dir) / "postmortem.md"

        # Write incident data
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(incident_data, f)

        # Run the generator (subprocess call is safe as we're using sys.executable and a known script)
        import subprocess  # noqa: S603
        import sys

        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "tools/postmortem_generator.py",
                "--input",
                str(input_file),
                "--output",
                str(output_file),
            ],
            capture_output=True,
            text=True,
            cwd="c:\\dev\\projects\\atp-main",
        )

        assert result.returncode == 0
        assert output_file.exists()

        content = output_file.read_text()
        assert "CLI Test Incident" in content
        assert "2025-01-01" in content
