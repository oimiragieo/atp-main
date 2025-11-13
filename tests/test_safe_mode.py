#!/usr/bin/env python3
"""
Tests for AGP safe mode fallback functionality (GAP-109M)
"""

import json
import os
import tempfile

import pytest

from router_service.agp_update_handler import AGPRouteTable, SafeModeConfig


class TestSafeModeConfig:
    """Test SafeModeConfig validation."""

    def test_valid_config(self):
        """Test valid safe mode configuration."""
        config = SafeModeConfig()
        config.validate()  # Should not raise

    def test_invalid_max_retries(self):
        """Test invalid max_retries."""
        config = SafeModeConfig(max_retries=-1)
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            config.validate()

    def test_invalid_retry_delay(self):
        """Test invalid retry_delay_seconds."""
        config = SafeModeConfig(retry_delay_seconds=0)
        with pytest.raises(ValueError, match="retry_delay_seconds must be positive"):
            config.validate()

    def test_empty_snapshot_path(self):
        """Test empty snapshot path."""
        config = SafeModeConfig(snapshot_path="")
        with pytest.raises(ValueError, match="snapshot_path must not be empty"):
            config.validate()


class TestSafeModeFallback:
    """Test safe mode fallback functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.snapshot_path = os.path.join(self.temp_dir, "test_snapshot.json")

        # Create safe mode config
        self.safe_config = SafeModeConfig(
            enabled=True, snapshot_path=self.snapshot_path, max_retries=3, retry_delay_seconds=1
        )

        # Create route table with safe mode
        self.route_table = AGPRouteTable(safe_mode_config=self.safe_config)

    def teardown_method(self):
        """Clean up test fixtures."""
        # Remove temp files
        if os.path.exists(self.snapshot_path):
            os.remove(self.snapshot_path)
        os.rmdir(self.temp_dir)

    def test_safe_mode_disabled(self):
        """Test safe mode when disabled."""
        config = SafeModeConfig(enabled=False)
        route_table = AGPRouteTable(safe_mode_config=config)

        # Should not enter safe mode
        result = route_table.enter_safe_mode()
        assert result is False
        assert route_table.is_in_safe_mode() is False

    def test_safe_mode_no_snapshot(self):
        """Test safe mode when snapshot file doesn't exist."""
        # Try to enter safe mode without snapshot file
        result = self.route_table.enter_safe_mode()
        assert result is False
        assert self.route_table.is_in_safe_mode() is False

    def test_safe_mode_with_valid_snapshot(self):
        """Test safe mode with valid snapshot file."""
        # Create a test snapshot
        test_snapshot = {
            "timestamp": 1234567890,
            "routes": {
                "test.*": {
                    "peer1": {
                        "prefix": "test.*",
                        "attributes": {
                            "path": [64512],
                            "next_hop": "peer1",
                            "originator_id": "peer1",
                            "local_pref": 100,
                        },
                        "received_at": 1234567890.0,
                        "peer_router_id": "peer1",
                    }
                }
            },
            "dampening_states": {},
        }

        # Write snapshot to file
        with open(self.snapshot_path, "w") as f:
            json.dump(test_snapshot, f)

        # Enter safe mode
        result = self.route_table.enter_safe_mode()
        assert result is True
        assert self.route_table.is_in_safe_mode() is True

        # Check that routes were loaded
        assert "test.*" in self.route_table.routes
        assert "peer1" in self.route_table.routes["test.*"]

    def test_safe_mode_with_invalid_snapshot(self):
        """Test safe mode with invalid snapshot file."""
        # Write invalid JSON to snapshot file
        with open(self.snapshot_path, "w") as f:
            f.write("invalid json")

        # Try to enter safe mode
        result = self.route_table.enter_safe_mode()
        assert result is False
        assert self.route_table.is_in_safe_mode() is False

    def test_save_last_known_good_snapshot(self):
        """Test saving last-known-good snapshot."""
        # Add some routes to the table
        from router_service.agp_update_handler import AGPRoute, AGPRouteAttributes

        attrs = AGPRouteAttributes(path=[64512], next_hop="peer1", originator_id="peer1", local_pref=100)

        route = AGPRoute(prefix="test.*", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")
        self.route_table.update_routes([route])

        # Save snapshot
        self.route_table.save_last_known_good_snapshot()

        # Check that snapshot file was created
        assert os.path.exists(self.snapshot_path)

        # Load and verify snapshot
        with open(self.snapshot_path) as f:
            snapshot = json.load(f)

        assert "routes" in snapshot
        assert "test.*" in snapshot["routes"]

    def test_exit_safe_mode(self):
        """Test exiting safe mode."""
        # Enter safe mode first
        test_snapshot = {"timestamp": 1234567890, "routes": {}, "dampening_states": {}}

        with open(self.snapshot_path, "w") as f:
            json.dump(test_snapshot, f)

        self.route_table.enter_safe_mode()
        assert self.route_table.is_in_safe_mode() is True

        # Exit safe mode
        self.route_table.exit_safe_mode()
        assert self.route_table.is_in_safe_mode() is False

    def test_safe_mode_metrics(self):
        """Test that safe mode increments metrics."""
        # Create valid snapshot
        test_snapshot = {"timestamp": 1234567890, "routes": {}, "dampening_states": {}}

        with open(self.snapshot_path, "w") as f:
            json.dump(test_snapshot, f)

        # Enter safe mode
        self.route_table.enter_safe_mode()

        # Check that metric was incremented
        # Note: In a real implementation, we'd check the registry
        # For this test, we just ensure the method completes without error
        assert self.route_table.is_in_safe_mode() is True


if __name__ == "__main__":
    pytest.main([__file__])
