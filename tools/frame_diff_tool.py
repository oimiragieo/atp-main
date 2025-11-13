"""Cross-Version Frame Diff Tool (GAP-335)

Compares ATP frame structures between versions to detect breaking changes
and generate upgrade checklists for protocol evolution.
"""

import sys
from dataclasses import dataclass
from typing import Any

from metrics.registry import REGISTRY
from router_service.frame import Frame, Meta, Payload, Window


@dataclass
class FieldChange:
    """Represents a change in a field between versions."""

    field_path: str
    change_type: str  # 'added', 'removed', 'type_changed', 'validation_changed'
    old_value: Any = None
    new_value: Any = None
    breaking: bool = False
    description: str = ""


@dataclass
class FrameDiff:
    """Result of comparing two frame versions."""

    version_old: str
    version_new: str
    changes: list[FieldChange]
    breaking_changes: int
    total_changes: int
    compatibility_score: float  # 0.0 (breaking) to 1.0 (fully compatible)


class FrameDiffAnalyzer:
    """Analyzes differences between frame versions."""

    def __init__(self):
        self.breaking_changes_detected = REGISTRY.counter("frame_diff_breaking_changes_total")

    def compare_frames(
        self,
        frame_old: dict[str, Any],
        frame_new: dict[str, Any],
        version_old: str = "vCurrent",
        version_new: str = "vNext",
    ) -> FrameDiff:
        """Compare two frame dictionaries and return detailed diff."""

        changes = []
        breaking_count = 0

        # Compare top-level fields
        all_fields = set(frame_old.keys()) | set(frame_new.keys())

        for field in sorted(all_fields):
            field_changes = self._compare_field(field, frame_old.get(field), frame_new.get(field))
            changes.extend(field_changes)

        breaking_count = sum(1 for change in changes if change.breaking)

        # Calculate compatibility score (1.0 = no breaking changes)
        total_fields = len(all_fields)
        compatibility_score = 1.0 - (breaking_count / max(total_fields, 1))

        diff = FrameDiff(
            version_old=version_old,
            version_new=version_new,
            changes=changes,
            breaking_changes=breaking_count,
            total_changes=len(changes),
            compatibility_score=max(0.0, compatibility_score),
        )

        # Update metrics
        self.breaking_changes_detected.inc(breaking_count)

        return diff

    def _compare_field(self, field_path: str, old_value: Any, new_value: Any) -> list[FieldChange]:
        """Compare a single field between versions."""
        changes = []

        # Field added
        if old_value is None and new_value is not None:
            changes.append(
                FieldChange(
                    field_path=field_path,
                    change_type="added",
                    new_value=new_value,
                    breaking=self._is_breaking_addition(field_path, new_value),
                    description=f"New field '{field_path}' added",
                )
            )

        # Field removed
        elif old_value is not None and new_value is None:
            changes.append(
                FieldChange(
                    field_path=field_path,
                    change_type="removed",
                    old_value=old_value,
                    breaking=self._is_breaking_removal(field_path, old_value),
                    description=f"Field '{field_path}' removed",
                )
            )

        # Field modified
        elif old_value != new_value:
            changes.extend(self._compare_field_values(field_path, old_value, new_value))

        return changes

    def _compare_field_values(self, field_path: str, old_value: Any, new_value: Any) -> list[FieldChange]:
        """Compare field values for type and validation changes."""
        changes = []

        # Type change
        if type(old_value) is not type(new_value):
            changes.append(
                FieldChange(
                    field_path=field_path,
                    change_type="type_changed",
                    old_value=type(old_value).__name__,
                    new_value=type(new_value).__name__,
                    breaking=self._is_breaking_type_change(field_path, old_value, new_value),
                    description=f"Type changed from {type(old_value).__name__} to {type(new_value).__name__}",
                )
            )

        # Dictionary comparison
        elif isinstance(old_value, dict) and isinstance(new_value, dict):
            changes.extend(self._compare_dicts(field_path, old_value, new_value))

        # List comparison
        elif isinstance(old_value, list) and isinstance(new_value, list):
            changes.extend(self._compare_lists(field_path, old_value, new_value))

        # Value change
        else:
            changes.append(
                FieldChange(
                    field_path=field_path,
                    change_type="value_changed",
                    old_value=old_value,
                    new_value=new_value,
                    breaking=self._is_breaking_value_change(field_path, old_value, new_value),
                    description=f"Value changed from {old_value} to {new_value}",
                )
            )

        return changes

    def _compare_dicts(self, base_path: str, old_dict: dict, new_dict: dict) -> list[FieldChange]:
        """Compare dictionary structures."""
        changes = []
        all_keys = set(old_dict.keys()) | set(new_dict.keys())

        for key in sorted(all_keys):
            field_path = f"{base_path}.{key}"
            changes.extend(self._compare_field(field_path, old_dict.get(key), new_dict.get(key)))

        return changes

    def _compare_lists(self, base_path: str, old_list: list, new_list: list) -> list[FieldChange]:
        """Compare list structures (simplified - just length and type checks)."""
        changes = []

        if len(old_list) != len(new_list):
            changes.append(
                FieldChange(
                    field_path=base_path,
                    change_type="list_length_changed",
                    old_value=len(old_list),
                    new_value=len(new_list),
                    breaking=self._is_breaking_list_change(base_path),
                    description=f"List length changed from {len(old_list)} to {len(new_list)}",
                )
            )

        # Check if item types are consistent
        if old_list and new_list:
            old_types = {type(item).__name__ for item in old_list}
            new_types = {type(item).__name__ for item in new_list}

            if old_types != new_types:
                changes.append(
                    FieldChange(
                        field_path=base_path,
                        change_type="list_item_types_changed",
                        old_value=old_types,
                        new_value=new_types,
                        breaking=True,
                        description=f"List item types changed from {old_types} to {new_types}",
                    )
                )

        return changes

    def _is_breaking_addition(self, field_path: str, new_value: Any) -> bool:
        """Determine if adding a field is breaking."""
        # Required fields are breaking if added
        required_fields = {"v", "session_id", "stream_id", "msg_seq", "qos", "window"}
        return any(field in field_path for field in required_fields)

    def _is_breaking_removal(self, field_path: str, old_value: Any) -> bool:
        """Determine if removing a field is breaking."""
        # Most field removals are breaking
        return True

    def _is_breaking_type_change(self, field_path: str, old_value: Any, new_value: Any) -> bool:
        """Determine if a type change is breaking."""
        # Type changes are generally breaking
        return True

    def _is_breaking_value_change(self, field_path: str, old_value: Any, new_value: Any) -> bool:
        """Determine if a value change is breaking."""
        # Changes to critical fields are breaking
        critical_fields = {"v", "qos"}
        return any(field in field_path for field in critical_fields)

    def _is_breaking_list_change(self, field_path: str) -> bool:
        """Determine if list changes are breaking."""
        return True

    def generate_upgrade_checklist(self, diff: FrameDiff) -> str:
        """Generate a human-readable upgrade checklist from the diff."""
        lines = []
        lines.append("# Frame Protocol Upgrade Checklist")
        lines.append(f"## {diff.version_old} → {diff.version_new}")
        lines.append(f"**Compatibility Score: {diff.compatibility_score:.2f}**")
        lines.append(f"**Breaking Changes: {diff.breaking_changes}**")
        lines.append("")

        if diff.breaking_changes > 0:
            lines.append("## 🚨 Breaking Changes (Require Code Changes)")
            for change in diff.changes:
                if change.breaking:
                    lines.append(f"- **{change.change_type.upper()}**: {change.description}")
            lines.append("")

        if diff.changes:
            lines.append("## 📋 All Changes")
            for change in diff.changes:
                status = "🚨" if change.breaking else "✅"
                lines.append(f"- {status} {change.description}")
            lines.append("")

        lines.append("## 🔧 Migration Steps")
        if diff.breaking_changes > 0:
            lines.append("1. Update frame parsing code to handle new/changed fields")
            lines.append("2. Update validation logic for type changes")
            lines.append("3. Test with both old and new frame formats")
            lines.append("4. Update client libraries and documentation")
        else:
            lines.append("1. Deploy new version (backward compatible)")
            lines.append("2. Monitor for any runtime issues")
            lines.append("3. Update documentation")

        return "\n".join(lines)


def create_sample_frames() -> tuple[dict[str, Any], dict[str, Any]]:
    """Create sample frames for testing (old vs new versions)."""

    # "Old" version frame
    old_frame = Frame(
        v=1,
        session_id="session-001",
        stream_id="stream-001",
        msg_seq=1,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=255,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=5000000),
        meta=Meta(task_type="chat"),
        payload=Payload(type="agent.request", content={"query": "Hello"}),
    )

    # "New" version frame (with some changes)
    new_frame = Frame(
        v=1,
        session_id="session-001",
        stream_id="stream-001",
        msg_seq=1,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=255,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=5000000),
        meta=Meta(task_type="chat", languages=["en"]),  # Added languages field
        payload=Payload(
            type="agent.request",
            content={"query": "Hello"},
            confidence=0.95,  # Added confidence field
        ),
    )

    return old_frame.to_public_dict(), new_frame.to_public_dict()


def main():
    """CLI interface for the frame diff tool."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tools/frame_diff_tool.py compare-frames")
        print("  python tools/frame_diff_tool.py generate-checklist")
        return

    command = sys.argv[1]

    analyzer = FrameDiffAnalyzer()

    if command == "compare-frames":
        old_frame, new_frame = create_sample_frames()
        diff = analyzer.compare_frames(old_frame, new_frame, "v1.0", "v1.1")

        print(f"Frame Comparison: {diff.version_old} → {diff.version_new}")
        print(f"Breaking Changes: {diff.breaking_changes}")
        print(f"Total Changes: {diff.total_changes}")
        print(f"Compatibility Score: {diff.compatibility_score:.2f}")
        print("\nChanges:")
        for change in diff.changes:
            status = "🚨 BREAKING" if change.breaking else "✅ Compatible"
            print(f"  {status}: {change.description}")

    elif command == "generate-checklist":
        old_frame, new_frame = create_sample_frames()
        diff = analyzer.compare_frames(old_frame, new_frame, "v1.0", "v1.1")
        checklist = analyzer.generate_upgrade_checklist(diff)
        print(checklist)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
