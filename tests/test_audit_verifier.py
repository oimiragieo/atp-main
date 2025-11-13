#!/usr/bin/env python3
"""
Tests for the audit hash verification CLI tool.
"""

import json
import os

# Add the memory-gateway directory to Python path
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory-gateway"))

import audit_log

from tools.audit_verifier import AuditVerifier


class TestAuditVerifier:
    """Test cases for the AuditVerifier class."""

    def test_verify_single_log_valid(self):
        """Test verifying a valid audit log."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_file = f.name

        try:
            # Create a valid audit log
            secret = b"test-secret"
            events = [
                {"event_type": "test1", "data": "value1"},
                {"event_type": "test2", "data": "value2"},
                {"event_type": "test3", "data": "value3"},
            ]

            prev_hash = None
            for event in events:
                prev_hash = audit_log.append_event(temp_file, event, secret, prev_hash)

            # Verify the log
            verifier = AuditVerifier(secret)
            assert verifier.verify_single_log(temp_file) is True

        finally:
            os.unlink(temp_file)

    def test_verify_single_log_invalid_secret(self):
        """Test verifying a log with wrong secret fails."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_file = f.name

        try:
            # Create a valid audit log
            secret = b"correct-secret"
            event = {"event_type": "test", "data": "value"}
            audit_log.append_event(temp_file, event, secret, None)

            # Try to verify with wrong secret
            verifier = AuditVerifier(b"wrong-secret")
            assert verifier.verify_single_log(temp_file) is False

        finally:
            os.unlink(temp_file)

    def test_verify_single_log_tampered(self):
        """Test that tampered log is detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_file = f.name

        try:
            # Create a valid audit log
            secret = b"test-secret"
            event = {"event_type": "test", "data": "value"}
            audit_log.append_event(temp_file, event, secret, None)

            # Tamper with the file
            with open(temp_file) as f:
                lines = f.readlines()
            tampered_record = json.loads(lines[0])
            tampered_record["event"]["data"] = "tampered"
            with open(temp_file, "w") as f:
                f.write(json.dumps(tampered_record) + "\n")

            # Verify should fail
            verifier = AuditVerifier(secret)
            assert verifier.verify_single_log(temp_file) is False

        finally:
            os.unlink(temp_file)

    def test_verify_batch_logs(self):
        """Test batch verification of multiple log files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create multiple valid log files
            secret = b"test-secret"
            log_files = []

            for i in range(3):
                log_path = os.path.join(temp_dir, f"audit_{i}.jsonl")
                log_files.append(log_path)
                event = {"event_type": f"test{i}", "data": f"value{i}"}
                audit_log.append_event(log_path, event, secret, None)

            # Create one invalid log file
            invalid_log = os.path.join(temp_dir, "invalid.jsonl")
            with open(invalid_log, "w") as f:
                f.write('{"invalid": "json"}\n')

            # Verify batch
            verifier = AuditVerifier(secret)
            verified, failed = verifier.verify_batch_logs(temp_dir)

            assert verified == 3  # 3 valid files
            assert failed == 1  # 1 invalid file

    def test_verify_single_log_file_not_found(self):
        """Test handling of non-existent file."""
        verifier = AuditVerifier()
        assert verifier.verify_single_log("/non/existent/file.jsonl") is False

    def test_verify_batch_logs_directory_not_found(self):
        """Test handling of non-existent directory."""
        verifier = AuditVerifier()
        verified, failed = verifier.verify_batch_logs("/non/existent/directory")
        assert verified == 0
        assert failed == 0

    def test_verify_batch_logs_no_log_files(self):
        """Test batch verification with no log files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a non-log file
            with open(os.path.join(temp_dir, "not_a_log.txt"), "w") as f:
                f.write("not a log file")

            verifier = AuditVerifier()
            verified, failed = verifier.verify_batch_logs(temp_dir)
            assert verified == 0
            assert failed == 0

    @patch("builtins.print")
    def test_print_log_stats(self, mock_print):
        """Test that log statistics are printed correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            temp_file = f.name

        try:
            # Create a log with multiple events
            secret = b"test-secret"
            events = [
                {"event_type": "test1", "data": "value1"},
                {"event_type": "test2", "data": "value2"},
                {"event_type": "test3", "data": "value3"},
            ]

            prev_hash = None
            for event in events:
                prev_hash = audit_log.append_event(temp_file, event, secret, prev_hash)

            verifier = AuditVerifier(secret)
            verifier.verify_single_log(temp_file)

            # Check that stats were printed
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any("Events: 3" in call for call in print_calls)
            assert any("Latest hash:" in call for call in print_calls)

        finally:
            os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__])
