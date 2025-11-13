#!/usr/bin/env python3
"""
Postmortem Automation Tool

Generates postmortem documents from incident data using templates.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from metrics.registry import REGISTRY
except ImportError:
    # Mock registry for testing
    class MockRegistry:
        def counter(self, name):
            return MockCounter()

    class MockCounter:
        def inc(self, amount=1):
            pass

    REGISTRY = MockRegistry()


class PostmortemGenerator:
    """Generates postmortem documents from incident data."""

    def __init__(self, template_path: Optional[str] = None):
        self.template_path = template_path or "runbooks/templates/postmortem_template.md"
        self.postmortems_completed = REGISTRY.counter("postmortems_completed")

    def load_template(self) -> str:
        """Load the postmortem template."""
        try:
            with open(self.template_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            # Create default template if it doesn't exist
            return self._create_default_template()

    def _create_default_template(self) -> str:
        """Create a default postmortem template."""
        template = """# Postmortem: {incident_title}

## Incident Summary
**Date:** {incident_date}
**Duration:** {duration}
**Impact:** {impact}
**Severity:** {severity}

## Timeline
{chronology}

## Root Cause
{root_cause}

## Impact Assessment
{impact_assessment}

## Resolution
{resolution}

## Prevention Measures
{prevention_measures}

## Lessons Learned
{lessons_learned}

## Action Items
{action_items}

## Metrics & KPIs
{metrics}

---
**Generated:** {generation_date}
**Incident ID:** {incident_id}
**Postmortem Author:** {author}
"""
        return template

    def generate_postmortem(self, incident_data: dict[str, Any]) -> str:
        """Generate a postmortem document from incident data."""
        template = self.load_template()

        # Fill template with incident data
        filled_template = template.format(
            incident_title=incident_data.get("title", "Unknown Incident"),
            incident_date=incident_data.get("date", datetime.now().strftime("%Y-%m-%d")),
            duration=incident_data.get("duration", "Unknown"),
            impact=incident_data.get("impact", "Unknown"),
            severity=incident_data.get("severity", "Unknown"),
            chronology=self._format_chronology(incident_data.get("chronology", [])),
            root_cause=incident_data.get("root_cause", "To be determined"),
            impact_assessment=incident_data.get("impact_assessment", "To be assessed"),
            resolution=incident_data.get("resolution", "To be documented"),
            prevention_measures=self._format_list(incident_data.get("prevention_measures", [])),
            lessons_learned=self._format_list(incident_data.get("lessons_learned", [])),
            action_items=self._format_action_items(incident_data.get("action_items", [])),
            metrics=self._format_metrics(incident_data.get("metrics", {})),
            generation_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            incident_id=incident_data.get("id", "Unknown"),
            author=incident_data.get("author", "Automated Generation"),
        )

        # Increment metrics
        self.postmortems_completed.inc()

        return filled_template

    def _format_chronology(self, chronology: list) -> str:
        """Format chronology as markdown list."""
        if not chronology:
            return "- No timeline available"

        lines = []
        for event in chronology:
            timestamp = event.get("timestamp", "Unknown")
            description = event.get("description", "Unknown event")
            lines.append(f"- **{timestamp}**: {description}")

        return "\n".join(lines)

    def _format_list(self, items: list) -> str:
        """Format list as markdown list."""
        if not items:
            return "- None documented"

        return "\n".join(f"- {item}" for item in items)

    def _format_action_items(self, action_items: list) -> str:
        """Format action items as markdown list with status."""
        if not action_items:
            return "- No action items identified"

        lines = []
        for item in action_items:
            status = item.get("status", "Open")
            description = item.get("description", "Unknown action")
            owner = item.get("owner", "Unassigned")
            lines.append(f"- [{status}] {description} (Owner: {owner})")

        return "\n".join(lines)

    def _format_metrics(self, metrics: dict[str, Any]) -> str:
        """Format metrics as markdown list."""
        if not metrics:
            return "- No metrics available"

        lines = []
        for key, value in metrics.items():
            lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)

    def save_postmortem(self, content: str, output_path: str) -> None:
        """Save postmortem to file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Postmortem saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate postmortem documents")
    parser.add_argument("--template", help="Path to postmortem template")
    parser.add_argument("--input", required=True, help="Path to incident data JSON file")
    parser.add_argument("--output", required=True, help="Output path for postmortem document")

    args = parser.parse_args()

    # Load incident data
    try:
        with open(args.input, encoding="utf-8") as f:
            incident_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Incident data file not found: {args.input}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in incident data file: {e}")
        sys.exit(1)

    # Generate postmortem
    generator = PostmortemGenerator(args.template)
    postmortem_content = generator.generate_postmortem(incident_data)

    # Save to file
    generator.save_postmortem(postmortem_content, args.output)


if __name__ == "__main__":
    main()
