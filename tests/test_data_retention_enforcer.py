#!/usr/bin/env python3
"""
Tests for Data Retention Enforcement System
"""

import json
import tempfile
import time
from pathlib import Path

import pytest

from tools.data_retention_enforcer import RetentionConfig, RetentionEnforcer


class TestRetentionConfig:
    """Test cases for RetentionConfig."""

    def test_default_policies(self):
        """Test that default policies are loaded correctly."""
        config = RetentionConfig()
        assert "lifecycle" in config.policies
        assert "admin_audit" in config.policies
        assert "reconciliation_audit" in config.policies
        assert "slm_observations" in config.policies

        # Check specific values
        assert config.policies["lifecycle"].max_age_days == 90
        assert config.policies["admin_audit"].max_age_days == 365
        assert config.policies["reconciliation_audit"].max_age_days == 180
        assert config.policies["slm_observations"].max_age_days == 30

    def test_load_from_file(self):
        """Test loading configuration from file."""
        config_data = {
            "policies": {"test_data": {"data_type": "test_data", "max_age_days": 7, "enabled": True, "dry_run": False}}
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            config = RetentionConfig(config_file)
            assert "test_data" in config.policies
            assert config.policies["test_data"].max_age_days == 7
        finally:
            Path(config_file).unlink()

    def test_get_policy(self):
        """Test getting a specific policy."""
        config = RetentionConfig()
        policy = config.get_policy("lifecycle")
        assert policy is not None
        assert policy.data_type == "lifecycle"
        assert policy.max_age_days == 90

        # Test non-existent policy
        assert config.get_policy("nonexistent") is None


class TestRetentionEnforcer:
    """Test cases for RetentionEnforcer."""

    def test_init(self):
        """Test enforcer initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)
            assert enforcer.data_dir == Path(temp_dir)
            assert enforcer.config == config

    def test_purge_old_data_no_policy(self):
        """Test purging data type with no policy."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            result = enforcer.purge_old_data("nonexistent_type")
            assert result["status"] == "skipped"
            assert result["reason"] == "no_policy"

    def test_purge_old_data_disabled_policy(self):
        """Test purging data type with disabled policy."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            config.policies["lifecycle"].enabled = False
            enforcer = RetentionEnforcer(temp_dir, config)

            result = enforcer.purge_old_data("lifecycle")
            assert result["status"] == "skipped"
            assert result["reason"] == "no_policy"

    def test_purge_old_data_no_files(self):
        """Test purging when no files match the pattern."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            result = enforcer.purge_old_data("lifecycle")
            assert result["status"] == "no_files"
            assert "lifecycle" in result["pattern"]

    def test_purge_old_data_dry_run(self):
        """Test dry run purging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            # Create a test file with old data
            test_file = Path(temp_dir) / "lifecycle-2020-01-01.jsonl"
            old_timestamp = time.time() - (100 * 24 * 60 * 60)  # 100 days ago

            with open(test_file, "w") as f:
                # Create records with old timestamps
                for i in range(5):
                    record = {"timestamp": old_timestamp + i, "event": f"test_event_{i}", "data": f"test_data_{i}"}
                    f.write(json.dumps(record) + "\n")

            # Test dry run
            result = enforcer.purge_old_data("lifecycle", dry_run=True)
            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert result["records_purged"] == 5  # All records should be candidates

            # File should still exist and have all records
            assert test_file.exists()
            with open(test_file) as f:
                lines = f.readlines()
                assert len(lines) == 5

    def test_purge_old_data_actual_deletion(self):
        """Test actual data deletion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            # Create a test file with old data
            test_file = Path(temp_dir) / "lifecycle-2020-01-01.jsonl"
            old_timestamp = time.time() - (100 * 24 * 60 * 60)  # 100 days ago

            with open(test_file, "w") as f:
                # Create records with old timestamps
                for i in range(5):
                    record = {"timestamp": old_timestamp + i, "event": f"test_event_{i}", "data": f"test_data_{i}"}
                    f.write(json.dumps(record) + "\n")

            # Test actual deletion
            result = enforcer.purge_old_data("lifecycle", dry_run=False)
            assert result["status"] == "completed"
            assert result["dry_run"] is False
            assert result["records_purged"] == 5

            # File should be empty or not exist
            if test_file.exists():
                with open(test_file) as f:
                    content = f.read().strip()
                    assert content == ""  # Should be empty

    def test_purge_old_data_mixed_ages(self):
        """Test purging with mixed old and new records."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            # Create a test file with mixed data
            test_file = Path(temp_dir) / "lifecycle-2020-01-01.jsonl"
            old_timestamp = time.time() - (100 * 24 * 60 * 60)  # 100 days ago
            new_timestamp = time.time() - (10 * 24 * 60 * 60)  # 10 days ago

            with open(test_file, "w") as f:
                # Old records (should be purged)
                for i in range(3):
                    record = {"timestamp": old_timestamp + i, "event": f"old_event_{i}", "data": f"old_data_{i}"}
                    f.write(json.dumps(record) + "\n")

                # New records (should be kept)
                for i in range(2):
                    record = {"timestamp": new_timestamp + i, "event": f"new_event_{i}", "data": f"new_data_{i}"}
                    f.write(json.dumps(record) + "\n")

            # Test dry run
            result = enforcer.purge_old_data("lifecycle", dry_run=True)
            assert result["status"] == "completed"
            assert result["records_purged"] == 3  # Only old records

            # File should still have all records (dry run doesn't modify)
            with open(test_file) as f:
                lines = f.readlines()
                assert len(lines) == 5  # All records still there

    def test_run_full_purge(self):
        """Test full purge across all data types."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            # Create test files for different data types
            old_timestamp = time.time() - (100 * 24 * 60 * 60)  # 100 days ago

            for data_type in ["lifecycle", "admin_audit"]:
                test_file = Path(temp_dir) / f"{data_type}-2020-01-01.jsonl"
                with open(test_file, "w") as f:
                    for i in range(2):
                        record = {
                            "timestamp": old_timestamp + i,
                            "event": f"{data_type}_event_{i}",
                            "data": f"{data_type}_data_{i}",
                        }
                        f.write(json.dumps(record) + "\n")

            # Test full purge dry run
            result = enforcer.run_full_purge(dry_run=True)
            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert "lifecycle" in result["results"]
            assert "admin_audit" in result["results"]

    def test_get_stats(self):
        """Test getting statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = RetentionConfig()
            enforcer = RetentionEnforcer(temp_dir, config)

            stats = enforcer.get_stats()
            assert isinstance(stats, dict)
            assert "records_purged" in stats
            assert "bytes_freed" in stats
            assert "files_processed" in stats
            assert "errors" in stats


if __name__ == "__main__":
    pytest.main([__file__])
