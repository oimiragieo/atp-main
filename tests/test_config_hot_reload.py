"""
Tests for Configuration Hot-Reloading System

GAP-4: Test configuration hot-reloading functionality
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from router_service.config_hot_reload import (
    ConfigHotReloader,
    get_config_hot_reloader,
    init_config_hot_reload,
    shutdown_config_hot_reload,
)


class TestConfigHotReloader:
    """Test ConfigHotReloader functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_file = self.temp_dir / "test_config.json"
        self.config_data = {"test_key": "test_value", "number": 42}

        # Create initial config file
        with open(self.config_file, 'w') as f:
            json.dump(self.config_data, f)

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp files
        if self.config_file.exists():
            self.config_file.unlink()
        self.temp_dir.rmdir()

    def test_initial_load(self):
        """Test initial config loading."""
        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(self.config_file), callback_mock)

        # Should load config on first check
        config = reloader._load_config()
        assert config == self.config_data

    def test_file_change_detection(self):
        """Test detection of file changes."""
        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(self.config_file), callback_mock, check_interval=0.1)

        # Initial state
        initial_hash = reloader._get_file_hash()
        initial_mtime = reloader._get_file_mtime()

        # Modify file
        new_data = {"test_key": "new_value", "number": 43}
        with open(self.config_file, 'w') as f:
            json.dump(new_data, f)

        # Should detect change
        new_hash = reloader._get_file_hash()
        new_mtime = reloader._get_file_mtime()

        assert new_hash != initial_hash
        assert new_mtime != initial_mtime

    @pytest.mark.asyncio
    async def test_hot_reload_workflow(self):
        """Test full hot-reload workflow."""
        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(self.config_file), callback_mock, check_interval=0.1)

        # Start watcher
        reloader.start()

        try:
            # Wait a bit for initial setup
            await asyncio.sleep(0.2)

            # Modify config
            new_data = {"test_key": "updated_value", "number": 100}
            import aiofiles
            async with aiofiles.open(self.config_file, 'w') as f:
                await f.write(json.dumps(new_data))

            # Wait for detection and reload
            await asyncio.sleep(0.3)

            # Should have called callback with initial config and then updated config
            assert callback_mock.call_count == 2
            callback_mock.assert_any_call(self.config_data)  # Initial load
            callback_mock.assert_called_with(new_data)  # Updated config

        finally:
            await reloader.stop()

    def test_force_reload(self):
        """Test force reload functionality."""
        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(self.config_file), callback_mock)

        # Modify config
        new_data = {"test_key": "force_reloaded", "number": 999}
        with open(self.config_file, 'w') as f:
            json.dump(new_data, f)

        # Force reload
        result = reloader.force_reload()

        assert result is True
        callback_mock.assert_called_once_with(new_data)

    def test_missing_config_file(self):
        """Test handling of missing config file."""
        missing_file = self.temp_dir / "missing.json"
        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(missing_file), callback_mock)

        config = reloader._load_config()
        assert config is None

        hash_val = reloader._get_file_hash()
        assert hash_val is None

    def test_invalid_json_config(self):
        """Test handling of invalid JSON in config file."""
        # Write invalid JSON
        with open(self.config_file, 'w') as f:
            f.write("invalid json content {")

        callback_mock = MagicMock()
        reloader = ConfigHotReloader(str(self.config_file), callback_mock)

        config = reloader._load_config()
        assert config is None

    @pytest.mark.asyncio
    async def test_callback_exception_handling(self):
        """Test that callback exceptions don't crash the watcher."""
        def failing_callback(config):
            raise ValueError("Callback failed")

        reloader = ConfigHotReloader(str(self.config_file), failing_callback, check_interval=0.1)

        # Start watcher
        reloader.start()

        try:
            # Wait for initial setup
            await asyncio.sleep(0.2)

            # Modify config (should trigger callback exception)
            new_data = {"test_key": "exception_test"}
            import aiofiles
            async with aiofiles.open(self.config_file, 'w') as f:
                await f.write(json.dumps(new_data))

            # Wait for detection
            await asyncio.sleep(0.3)

            # Watcher should still be running despite callback failure
            assert reloader._running

        finally:
            await reloader.stop()


class TestGlobalConfigHotReload:
    """Test global config hot-reload functions."""

    def test_init_and_get(self):
        """Test global initialization and access."""
        callback_mock = MagicMock()

        # Should return None initially
        assert get_config_hot_reloader() is None

        # Initialize
        reloader = init_config_hot_reload("/tmp/test.json", callback_mock)

        # Should return the instance
        assert get_config_hot_reloader() is reloader

    @pytest.mark.asyncio
    async def test_global_shutdown(self):
        """Test global shutdown functionality."""
        callback_mock = MagicMock()

        # Initialize
        reloader = init_config_hot_reload("/tmp/test.json", callback_mock)
        reloader.start()

        # Shutdown
        await shutdown_config_hot_reload()

        # Should be None after shutdown
        assert get_config_hot_reloader() is None
        assert not reloader._running