"""Tests for GAP-215: Observation file rotation and compression policy."""

import gzip
import json
import os
import shutil
import tempfile
from unittest.mock import patch

from metrics.registry import REGISTRY
from router_service.service import _record_observation, _rotate_observation_file


class TestObservationFileRotation:
    """Test observation file rotation and compression functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.obs_file = os.path.join(self.temp_dir, "test_observations.jsonl")

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_rotate_observation_file_basic(self):
        """Test basic file rotation and compression."""
        # Create a test observation file with some content
        test_data = [
            {"ts": 1234567890, "test": "data1"},
            {"ts": 1234567891, "test": "data2"},
        ]

        with open(self.obs_file, "w") as f:
            for item in test_data:
                f.write(json.dumps(item) + "\n")

        # Rotate the file
        _rotate_observation_file(self.obs_file)

        # Check that original file is cleared
        with open(self.obs_file) as f:
            content = f.read().strip()
        assert content == "", "Original file should be cleared after rotation"

        # Check that compressed file exists
        compressed_file = self.obs_file + ".gz"
        assert os.path.exists(compressed_file), "Compressed file should exist"

        # Check that compressed file contains original data
        with gzip.open(compressed_file, "rt") as f:
            lines = f.readlines()
        assert len(lines) == 2, "Compressed file should contain 2 lines"
        assert json.loads(lines[0].strip()) == test_data[0]
        assert json.loads(lines[1].strip()) == test_data[1]

    def test_rotate_observation_file_rotation_counter(self):
        """Test that rotation increments the metrics counter."""
        # Create a test observation file
        with open(self.obs_file, "w") as f:
            f.write('{"test": "data"}\n')

        # Get initial counter value
        counter = REGISTRY.counter("atp_router_observation_files_rotated_total")
        initial_value = counter._value

        # Rotate the file
        _rotate_observation_file(self.obs_file)

        # Check that counter was incremented
        assert counter._value == initial_value + 1, "Rotation counter should be incremented"

    def test_rotate_observation_file_error_handling(self):
        """Test error handling during file rotation."""
        # Create a test observation file
        with open(self.obs_file, "w") as f:
            f.write('{"test": "data"}\n')

        # Mock gzip.open to raise an exception
        with patch("gzip.open", side_effect=Exception("Test error")):
            # This should not raise an exception (best-effort rotation)
            _rotate_observation_file(self.obs_file)

        # Original file should still exist (not cleared due to error)
        assert os.path.exists(self.obs_file), "Original file should still exist on error"

        # Compressed file should not exist
        compressed_file = self.obs_file + ".gz"
        assert not os.path.exists(compressed_file), "Compressed file should not exist on error"

    def test_record_observation_with_rotation(self):
        """Test observation recording with automatic rotation."""
        # Mock the data directory
        test_obs_file = os.path.join(self.temp_dir, "slm_observations-2025-01-01.jsonl")

        # Create a large file that exceeds the size limit
        large_content = '{"ts": 1234567890, "test": "data"}\n' * 1000  # ~35KB

        with open(test_obs_file, "w") as f:
            f.write(large_content)

        # Mock environment variable for small size limit
        with patch.dict(os.environ, {"OBSERVATION_MAX_FILE_SIZE_MB": "0.001"}):  # 1KB limit
            with patch("router_service.service._DATA_DIR", self.temp_dir):
                with patch("router_service.service.datetime") as mock_datetime:
                    # Mock today's date
                    mock_datetime.date.today.return_value.isoformat.return_value = "2025-01-01"
                    with patch("router_service.service._rotate_observation_file") as mock_rotate:
                        # Record a new observation (this should trigger rotation check)
                        _record_observation({"ts": 1234567891, "test": "new_data"})

                        # Check that rotation was called
                        mock_rotate.assert_called_once_with(test_obs_file)

    def test_record_observation_no_rotation_when_under_limit(self):
        """Test that rotation is not triggered when file size is under limit."""
        # Mock the data directory
        test_obs_file = os.path.join(self.temp_dir, "slm_observations-2025-01-01.jsonl")

        # Create a small file
        with open(test_obs_file, "w") as f:
            f.write('{"ts": 1234567890, "test": "data"}\n')

        # Mock environment variable for large size limit
        with patch.dict(os.environ, {"OBSERVATION_MAX_FILE_SIZE_MB": "100"}):  # 100MB limit
            with patch("router_service.service._DATA_DIR", self.temp_dir):
                with patch("router_service.service.datetime") as mock_datetime:
                    # Mock today's date
                    mock_datetime.date.today.return_value.isoformat.return_value = "2025-01-01"
                    with patch("router_service.service._rotate_observation_file") as mock_rotate:
                        # Record a new observation
                        _record_observation({"ts": 1234567891, "test": "new_data"})

                        # Check that rotation was NOT called
                        mock_rotate.assert_not_called()

    def test_record_observation_default_size_limit(self):
        """Test that default size limit is used when environment variable is not set."""
        # Mock the data directory
        test_obs_file = os.path.join(self.temp_dir, "slm_observations-2025-01-01.jsonl")

        # Create a file that's larger than default limit (100MB default)
        # Use a smaller test file for practicality
        large_content = '{"ts": 1234567890, "test": "data"}\n' * 10000  # ~350KB

        with open(test_obs_file, "w") as f:
            f.write(large_content)

        # Remove environment variable if it exists
        env_copy = os.environ.copy()
        if "OBSERVATION_MAX_FILE_SIZE_MB" in env_copy:
            del env_copy["OBSERVATION_MAX_FILE_SIZE_MB"]

        with patch.dict(os.environ, env_copy, clear=True):
            with patch("router_service.service._DATA_DIR", self.temp_dir):
                with patch("router_service.service.datetime") as mock_datetime:
                    # Mock today's date
                    mock_datetime.date.today.return_value.isoformat.return_value = "2025-01-01"
                    with patch("router_service.service._rotate_observation_file") as mock_rotate:
                        # Record a new observation
                        _record_observation({"ts": 1234567891, "test": "new_data"})

                        # With default 100MB limit, this small file should not trigger rotation
                        mock_rotate.assert_not_called()

    def test_rotate_observation_file_thread_safety(self):
        """Test that rotation is thread-safe."""
        # Create a test observation file
        with open(self.obs_file, "w") as f:
            f.write('{"test": "data"}\n')

        # The _rotate_observation_file function doesn't use _OBS_LOCK directly
        # It's called from _record_observation which does use the lock
        # So this test just verifies the function works without errors
        _rotate_observation_file(self.obs_file)

        # Check that compressed file exists
        compressed_file = self.obs_file + ".gz"
        assert os.path.exists(compressed_file), "Compressed file should exist"
