"""Tests for GAP-216: Lifecycle history append-only log."""

import json
import os
import tempfile
from unittest.mock import patch

from metrics.registry import REGISTRY
from router_service.service import _DATA_DIR, _persist_lifecycle


class TestLifecycleHistory:
    """Test lifecycle history append-only logging functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_data_dir = _DATA_DIR
        # Mock the data directory for testing
        with patch("router_service.service._DATA_DIR", self.temp_dir):
            # Reset the lifecycle file path
            global _LIFECYCLE_FILE
            _LIFECYCLE_FILE = os.path.join(self.temp_dir, "lifecycle.jsonl")

    def teardown_method(self):
        """Clean up test environment."""
        # Clean up any files created
        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")
        if os.path.exists(lifecycle_file):
            os.remove(lifecycle_file)
        os.rmdir(self.temp_dir)

    def test_persist_lifecycle_basic(self):
        """Test basic lifecycle event persistence."""
        test_event = {"ts": 1234567890.123, "event": "promotion", "model": "test-model", "cluster": "test-cluster"}

        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")
        with patch("router_service.service._LIFECYCLE_FILE", lifecycle_file):
            _persist_lifecycle(test_event)

        # Check that file was created and contains the event
        assert os.path.exists(lifecycle_file), "Lifecycle file should be created"

        with open(lifecycle_file) as f:
            lines = f.readlines()

        assert len(lines) == 1, "Should have one line in the file"
        parsed_event = json.loads(lines[0].strip())
        assert parsed_event == test_event, "Event should be correctly persisted"

    def test_persist_lifecycle_multiple_events(self):
        """Test persistence of multiple lifecycle events."""
        events = [
            {"ts": 1234567890, "event": "promotion", "model": "model1", "cluster": "cluster1"},
            {"ts": 1234567891, "event": "demotion", "model": "model2", "cluster": "cluster2"},
            {"ts": 1234567892, "event": "promotion", "model": "model3", "cluster": "cluster3"},
        ]

        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")
        with patch("router_service.service._LIFECYCLE_FILE", lifecycle_file):
            for event in events:
                _persist_lifecycle(event)

        # Check that all events were persisted
        with open(lifecycle_file) as f:
            lines = f.readlines()

        assert len(lines) == 3, "Should have three lines in the file"
        for i, line in enumerate(lines):
            parsed_event = json.loads(line.strip())
            assert parsed_event == events[i], f"Event {i} should match"

    def test_persist_lifecycle_counter_increment(self):
        """Test that lifecycle events counter is incremented."""
        test_event = {"ts": 1234567890, "event": "promotion", "model": "test-model"}

        # Get initial counter value
        counter = REGISTRY.counter("atp_router_lifecycle_events_total")
        initial_value = counter._value

        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")
        with patch("router_service.service._LIFECYCLE_FILE", lifecycle_file):
            _persist_lifecycle(test_event)

        # Check that counter was incremented
        assert counter._value == initial_value + 1, "Lifecycle events counter should be incremented"

    def test_lifecycle_history_replay(self):
        """Test that lifecycle history can be replayed from the JSONL file."""
        # Create some test events
        events = [
            {"ts": 1234567890, "event": "promotion", "model": "model1", "cluster": "cluster1"},
            {"ts": 1234567891, "event": "demotion", "model": "model2", "cluster": "cluster2", "baseline": "model1"},
            {"ts": 1234567892, "event": "promotion", "model": "model3", "cluster": "cluster3"},
        ]

        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")

        # Write events directly to file (simulating historical data)
        with open(lifecycle_file, "w") as f:
            for event in events:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")

        # Replay the events from the file
        replayed_events = []
        with open(lifecycle_file) as f:
            for line in f:
                replayed_events.append(json.loads(line.strip()))

        # Verify replay correctness
        assert len(replayed_events) == len(events), "Should replay all events"
        for original, replayed in zip(events, replayed_events):
            assert original == replayed, "Replayed event should match original"

    def test_lifecycle_history_append_only(self):
        """Test that lifecycle file is append-only."""
        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")

        # Write initial content
        initial_event = {"ts": 1234567890, "event": "promotion", "model": "initial-model"}
        with open(lifecycle_file, "w") as f:
            f.write(json.dumps(initial_event, separators=(",", ":")) + "\n")

        # Append more events
        additional_events = [
            {"ts": 1234567891, "event": "demotion", "model": "model1"},
            {"ts": 1234567892, "event": "promotion", "model": "model2"},
        ]

        with patch("router_service.service._LIFECYCLE_FILE", lifecycle_file):
            for event in additional_events:
                _persist_lifecycle(event)

        # Verify all events are present
        with open(lifecycle_file) as f:
            lines = f.readlines()

        assert len(lines) == 3, "Should have all events"

        all_events = [initial_event] + additional_events
        for i, line in enumerate(lines):
            parsed_event = json.loads(line.strip())
            assert parsed_event == all_events[i], f"Event {i} should be correct"

    def test_persist_lifecycle_error_handling(self):
        """Test error handling in lifecycle persistence."""
        test_event = {"ts": 1234567890, "event": "promotion", "model": "test-model"}

        # Mock os.makedirs to raise an exception
        with patch("os.makedirs", side_effect=OSError("Permission denied")):
            # Should not raise exception (best-effort)
            _persist_lifecycle(test_event)

        # File should not exist due to error
        lifecycle_file = os.path.join(self.temp_dir, "lifecycle.jsonl")
        assert not os.path.exists(lifecycle_file), "File should not exist on error"
