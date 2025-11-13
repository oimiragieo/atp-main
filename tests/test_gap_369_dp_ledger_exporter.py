"""Tests for GAP-369: Differential Privacy Ledger Exporter."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from router_service.dp_ledger_exporter import (
    DpLedgerEntry,
    DpLedgerExporter,
    get_dp_ledger_exporter,
    initialize_dp_ledger_exporter,
)


class TestDpLedgerEntry(unittest.TestCase):
    """Test cases for DP ledger entry."""

    def test_entry_creation(self):
        """Test basic ledger entry creation."""
        timestamp = datetime.now()
        entry = DpLedgerEntry(
            entry_id="test_001",
            tenant_id="tenant1",
            event_type="request_count",
            timestamp=timestamp,
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0,
            sequence_number=1,
            previous_hash="abc123"
        )

        self.assertEqual(entry.entry_id, "test_001")
        self.assertEqual(entry.tenant_id, "tenant1")
        self.assertEqual(entry.event_type, "request_count")
        self.assertEqual(entry.dp_value, 95.2)
        self.assertEqual(entry.epsilon_used, 0.5)
        self.assertEqual(entry.sensitivity, 1.0)
        self.assertEqual(entry.sequence_number, 1)
        self.assertEqual(entry.previous_hash, "abc123")

    def test_entry_hash_computation(self):
        """Test cryptographic hash computation for entry integrity."""
        entry = DpLedgerEntry(
            entry_id="test_001",
            tenant_id="tenant1",
            event_type="request_count",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0,
            sequence_number=1,
            previous_hash="abc123"
        )

        hash_value = entry.compute_hash()
        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)  # SHA-256 hex length

        # Hash should be deterministic
        hash_value2 = entry.compute_hash()
        self.assertEqual(hash_value, hash_value2)

    def test_entry_serialization(self):
        """Test entry serialization to/from dictionary."""
        original_entry = DpLedgerEntry(
            entry_id="test_001",
            tenant_id="tenant1",
            event_type="request_count",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0,
            sequence_number=1,
            previous_hash="abc123",
            metadata={"source": "test"}
        )

        # Serialize to dict
        entry_dict = original_entry.to_dict()

        # Deserialize from dict
        restored_entry = DpLedgerEntry.from_dict(entry_dict)

        # Verify all fields match
        self.assertEqual(original_entry.entry_id, restored_entry.entry_id)
        self.assertEqual(original_entry.tenant_id, restored_entry.tenant_id)
        self.assertEqual(original_entry.event_type, restored_entry.event_type)
        self.assertEqual(original_entry.dp_value, restored_entry.dp_value)
        self.assertEqual(original_entry.epsilon_used, restored_entry.epsilon_used)
        self.assertEqual(original_entry.sensitivity, restored_entry.sensitivity)
        self.assertEqual(original_entry.sequence_number, restored_entry.sequence_number)
        self.assertEqual(original_entry.previous_hash, restored_entry.previous_hash)
        self.assertEqual(original_entry.metadata, restored_entry.metadata)

    def test_hash_chain_integrity(self):
        """Test that hash chain maintains integrity."""
        # Create first entry
        entry1 = DpLedgerEntry(
            entry_id="test_001",
            tenant_id="tenant1",
            event_type="request_count",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0,
            sequence_number=1,
            previous_hash="0" * 64
        )
        hash1 = entry1.compute_hash()

        # Create second entry that references first
        entry2 = DpLedgerEntry(
            entry_id="test_002",
            tenant_id="tenant1",
            event_type="latency",
            timestamp=datetime(2024, 1, 1, 12, 1, 0),
            dp_value=45.7,
            epsilon_used=0.3,
            sensitivity=1.0,
            sequence_number=2,
            previous_hash=hash1
        )
        hash2 = entry2.compute_hash()

        # Verify chain
        self.assertEqual(entry2.previous_hash, hash1)
        self.assertNotEqual(hash1, hash2)


class TestDpLedgerExporter(unittest.TestCase):
    """Test cases for DP ledger exporter."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.exporter = DpLedgerExporter(
            ledger_path=str(self.temp_dir),
            max_epsilon_per_tenant=2.0
        )

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_exporter_initialization(self):
        """Test exporter initialization."""
        self.assertEqual(self.exporter.max_epsilon_per_tenant, 2.0)
        self.assertEqual(self.exporter.current_sequence, 0)
        self.assertEqual(self.exporter.last_hash, "0" * 64)

    def test_add_entry_success(self):
        """Test successful addition of ledger entry."""
        success = self.exporter.add_entry(
            tenant_id="tenant1",
            event_type="request_count",
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0
        )

        self.assertTrue(success)
        self.assertEqual(self.exporter.current_sequence, 1)
        self.assertNotEqual(self.exporter.last_hash, "0" * 64)

        # Check epsilon usage
        budget_status = self.exporter.get_budget_status("tenant1")
        self.assertEqual(budget_status["epsilon_used"], 0.5)
        self.assertEqual(budget_status["epsilon_remaining"], 1.5)

    def test_add_entry_budget_exceeded(self):
        """Test budget exceeded rejection."""
        # Use up the budget
        self.exporter.add_entry("tenant1", "request_count", 95.2, 2.0, 1.0)

        # This should fail
        success = self.exporter.add_entry(
            tenant_id="tenant1",
            event_type="latency",
            dp_value=45.7,
            epsilon_used=0.1,
            sensitivity=1.0
        )

        self.assertFalse(success)

        # Check that sequence number didn't increment
        self.assertEqual(self.exporter.current_sequence, 1)

    def test_multiple_tenants(self):
        """Test multiple tenants with separate budgets."""
        # Add entries for different tenants
        self.exporter.add_entry("tenant1", "request_count", 95.2, 0.5, 1.0)
        self.exporter.add_entry("tenant2", "request_count", 87.3, 0.7, 1.0)
        self.exporter.add_entry("tenant1", "latency", 45.7, 0.3, 1.0)

        # Check budgets
        budget1 = self.exporter.get_budget_status("tenant1")
        budget2 = self.exporter.get_budget_status("tenant2")

        self.assertEqual(budget1["epsilon_used"], 0.8)
        self.assertEqual(budget2["epsilon_used"], 0.7)

        self.assertEqual(self.exporter.current_sequence, 3)

    def test_ledger_persistence(self):
        """Test ledger persistence across exporter instances."""
        # Add some entries
        self.exporter.add_entry("tenant1", "request_count", 95.2, 0.5, 1.0)
        self.exporter.add_entry("tenant1", "latency", 45.7, 0.3, 1.0)

        # Create new exporter instance (simulating restart)
        new_exporter = DpLedgerExporter(
            ledger_path=str(self.temp_dir),
            max_epsilon_per_tenant=2.0
        )

        # Should have loaded the state
        self.assertEqual(new_exporter.current_sequence, 2)
        self.assertNotEqual(new_exporter.last_hash, "0" * 64)

        # Budget should be restored
        budget = new_exporter.get_budget_status("tenant1")
        self.assertEqual(budget["epsilon_used"], 0.8)

    def test_ledger_export_jsonl(self):
        """Test ledger export in JSONL format."""
        # Add some entries
        self.exporter.add_entry("tenant1", "request_count", 95.2, 0.5, 1.0)
        self.exporter.add_entry("tenant2", "latency", 45.7, 0.3, 1.0)

        # Export
        export_path = self.exporter.export_ledger("jsonl")

        # Verify export file exists
        self.assertTrue(os.path.exists(export_path))

        # Verify contents
        with open(export_path) as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)

            # Parse first entry
            entry1 = json.loads(lines[0].strip())
            self.assertEqual(entry1["tenant_id"], "tenant1")
            self.assertEqual(entry1["event_type"], "request_count")
            self.assertEqual(entry1["dp_value"], 95.2)
            self.assertIn("entry_hash", entry1)

    def test_ledger_export_json(self):
        """Test ledger export in JSON format."""
        # Add some entries
        self.exporter.add_entry("tenant1", "request_count", 95.2, 0.5, 1.0)

        # Export
        export_path = self.exporter.export_ledger("json")

        # Verify export file exists
        self.assertTrue(os.path.exists(export_path))

        # Verify contents
        with open(export_path) as f:
            data = json.load(f)

            self.assertIn("export_timestamp", data)
            self.assertEqual(data["total_entries"], 1)
            self.assertIn("ledger_integrity", data)
            self.assertEqual(len(data["entries"]), 1)

            entry = data["entries"][0]
            self.assertEqual(entry["tenant_id"], "tenant1")
            self.assertEqual(entry["dp_value"], 95.2)

    def test_ledger_integrity_verification(self):
        """Test ledger integrity verification."""
        # Add some entries
        self.exporter.add_entry("tenant1", "request_count", 95.2, 0.5, 1.0)
        self.exporter.add_entry("tenant1", "latency", 45.7, 0.3, 1.0)

        # Verify integrity
        stats = self.exporter.get_ledger_stats()
        integrity = stats["ledger_integrity"]

        self.assertTrue(integrity["valid"])
        self.assertEqual(integrity["entries_checked"], 2)
        self.assertEqual(integrity["corrupt_entries"], 0)

    def test_metadata_support(self):
        """Test metadata support in ledger entries."""
        metadata = {"source": "test", "version": "1.0"}

        success = self.exporter.add_entry(
            tenant_id="tenant1",
            event_type="request_count",
            dp_value=95.2,
            epsilon_used=0.5,
            sensitivity=1.0,
            metadata=metadata
        )

        self.assertTrue(success)

        # Export and verify metadata is preserved
        export_path = self.exporter.export_ledger("json")
        with open(export_path) as f:
            data = json.load(f)
            entry = data["entries"][0]
            self.assertEqual(entry["metadata"], metadata)

    def test_empty_ledger_operations(self):
        """Test operations on empty ledger."""
        # Export empty ledger
        export_path = self.exporter.export_ledger("json")
        self.assertTrue(os.path.exists(export_path))

        # Check stats
        stats = self.exporter.get_ledger_stats()
        self.assertEqual(stats["total_entries"], 0)
        self.assertEqual(stats["active_tenants"], 0)

        # Verify integrity of empty ledger
        integrity = stats["ledger_integrity"]
        self.assertTrue(integrity["valid"])
        self.assertEqual(integrity["entries_checked"], 0)


class TestDpLedgerGlobalFunctions(unittest.TestCase):
    """Test global DP ledger functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_global_exporter_initialization(self):
        """Test global exporter initialization."""
        exporter = initialize_dp_ledger_exporter(
            ledger_path=str(self.temp_dir),
            max_epsilon_per_tenant=1.5
        )

        self.assertIsNotNone(exporter)
        self.assertEqual(exporter.max_epsilon_per_tenant, 1.5)

        # Test getter
        global_exporter = get_dp_ledger_exporter()
        self.assertEqual(global_exporter, exporter)


if __name__ == "__main__":
    unittest.main()
