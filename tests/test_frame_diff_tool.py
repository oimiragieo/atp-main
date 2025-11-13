"""Tests for Cross-Version Frame Diff Tool (GAP-335)

Tests the frame comparison functionality including:
- Field addition/removal detection
- Type change detection
- Breaking change classification
- Upgrade checklist generation
"""

from unittest.mock import patch

import pytest

from router_service.frame import Frame, Meta, Payload, Window
from tools.frame_diff_tool import FrameDiffAnalyzer


class TestFrameDiffAnalyzer:
    """Test suite for frame diff analyzer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = FrameDiffAnalyzer()

    def test_compare_identical_frames(self):
        """Test comparison of identical frames."""
        frame = Frame(
            v=1,
            session_id="test",
            stream_id="stream",
            msg_seq=1,
            frag_seq=0,
            flags=["SYN"],
            qos="gold",
            ttl=255,
            window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=5000000),
            meta=Meta(task_type="chat"),
            payload=Payload(type="agent.request", content={"query": "Hello"})
        )

        frame_dict = frame.to_public_dict()
        diff = self.analyzer.compare_frames(frame_dict, frame_dict)

        assert diff.breaking_changes == 0
        assert diff.total_changes == 0
        assert diff.compatibility_score == 1.0

    def test_detect_field_addition(self):
        """Test detection of added fields."""
        old_frame = {
            "v": 1,
            "session_id": "test",
            "qos": "gold"
        }

        new_frame = {
            "v": 1,
            "session_id": "test",
            "qos": "gold",
            "new_field": "value"
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "added"
        assert diff.changes[0].field_path == "new_field"
        assert not diff.changes[0].breaking  # Non-critical field addition

    def test_detect_breaking_field_addition(self):
        """Test detection of breaking field additions."""
        old_frame = {
            "v": 1,
            "session_id": "test"
        }

        new_frame = {
            "v": 1,
            "session_id": "test",
            "qos": "gold"  # Adding required field
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].breaking
        assert diff.breaking_changes == 1

    def test_detect_field_removal(self):
        """Test detection of removed fields."""
        old_frame = {
            "v": 1,
            "session_id": "test",
            "old_field": "value"
        }

        new_frame = {
            "v": 1,
            "session_id": "test"
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "removed"
        assert diff.changes[0].field_path == "old_field"
        assert diff.changes[0].breaking  # Field removal is always breaking

    def test_detect_type_change(self):
        """Test detection of type changes."""
        old_frame = {
            "v": 1,
            "count": 42
        }

        new_frame = {
            "v": 1,
            "count": "42"
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "type_changed"
        assert diff.changes[0].old_value == "int"
        assert diff.changes[0].new_value == "str"
        assert diff.changes[0].breaking  # Type changes are breaking

    def test_detect_breaking_value_change(self):
        """Test detection of breaking value changes."""
        old_frame = {
            "v": 1,
            "qos": "gold"
        }

        new_frame = {
            "v": 1,
            "qos": "silver"
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "value_changed"
        assert diff.changes[0].breaking  # QoS change is breaking

    def test_compare_nested_dicts(self):
        """Test comparison of nested dictionary structures."""
        old_frame = {
            "meta": {
                "task_type": "chat",
                "languages": ["en"]
            }
        }

        new_frame = {
            "meta": {
                "task_type": "chat",
                "languages": ["en", "es"]  # Added language
            }
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        # Should detect the list length change
        assert len(diff.changes) > 0
        assert any(change.change_type == "list_length_changed" for change in diff.changes)

    def test_compare_lists(self):
        """Test comparison of list structures."""
        old_frame = {
            "flags": ["SYN"]
        }

        new_frame = {
            "flags": ["SYN", "ACK"]
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "list_length_changed"
        assert diff.changes[0].breaking  # List changes are breaking

    def test_compatibility_score_calculation(self):
        """Test compatibility score calculation."""
        # Frame with 4 fields, 1 breaking change
        old_frame = {
            "v": 1,
            "session_id": "test",
            "qos": "gold",
            "ttl": 255
        }

        new_frame = {
            "v": 1,
            "session_id": "test",
            "qos": "silver",  # Breaking change
            "ttl": 255
        }

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        # 1 breaking change out of 4 fields = 0.75 compatibility
        assert diff.compatibility_score == 0.75

    def test_generate_upgrade_checklist(self):
        """Test upgrade checklist generation."""
        old_frame = {"v": 1, "qos": "gold"}
        new_frame = {"v": 1, "qos": "silver"}

        diff = self.analyzer.compare_frames(old_frame, new_frame, "v1.0", "v1.1")
        checklist = self.analyzer.generate_upgrade_checklist(diff)

        assert "Frame Protocol Upgrade Checklist" in checklist
        assert "v1.0 → v1.1" in checklist
        assert "🚨 Breaking Changes" in checklist
        assert "🔧 Migration Steps" in checklist

    def test_metrics_integration(self):
        """Test metrics are properly updated."""
        # Create a breaking change
        old_frame = {"v": 1}
        new_frame = {"v": 2}  # Version change is breaking

        initial_count = self.analyzer.breaking_changes_detected._value
        diff = self.analyzer.compare_frames(old_frame, new_frame)
        final_count = self.analyzer.breaking_changes_detected._value

        assert final_count > initial_count
        assert diff.breaking_changes > 0

    def test_complex_frame_comparison(self):
        """Test comparison of complex frame structures."""
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
            payload=Payload(type="agent.request", content={"query": "Hello"})
        )

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
            meta=Meta(task_type="chat", languages=["en"]),  # Added field
            payload=Payload(
                type="agent.request",
                content={"query": "Hello"},
                confidence=0.95  # Added field
            )
        )

        diff = self.analyzer.compare_frames(
            old_frame.to_public_dict(),
            new_frame.to_public_dict(),
            "v1.0",
            "v1.1"
        )

        # Should detect additions but not breaking changes
        assert diff.total_changes > 0
        assert diff.breaking_changes == 0  # These additions are not breaking
        assert diff.compatibility_score == 1.0

    def test_empty_frame_comparison(self):
        """Test comparison with empty frames."""
        old_frame = {}
        new_frame = {"v": 1}

        diff = self.analyzer.compare_frames(old_frame, new_frame)

        assert len(diff.changes) == 1
        assert diff.changes[0].change_type == "added"
        assert diff.changes[0].field_path == "v"


def test_cli_compare_frames():
    """Test CLI interface for frame comparison."""
    from tools.frame_diff_tool import main

    # Mock sys.argv for testing
    with patch('sys.argv', ['frame_diff_tool.py', 'compare-frames']):
        with patch('builtins.print') as mock_print:
            main()
            # Should print comparison results
            assert mock_print.called


def test_cli_generate_checklist():
    """Test CLI interface for checklist generation."""
    from tools.frame_diff_tool import main

    with patch('sys.argv', ['frame_diff_tool.py', 'generate-checklist']):
        with patch('builtins.print') as mock_print:
            main()
            # Should print checklist
            assert mock_print.called


def test_create_sample_frames():
    """Test sample frame creation utility."""
    from tools.frame_diff_tool import create_sample_frames

    old_frame, new_frame = create_sample_frames()

    assert isinstance(old_frame, dict)
    assert isinstance(new_frame, dict)
    assert old_frame["v"] == 1
    assert new_frame["v"] == 1

    # New frame should have additional fields
    assert len(new_frame["meta"]) >= len(old_frame["meta"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
