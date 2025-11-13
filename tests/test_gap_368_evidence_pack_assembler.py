"""Tests for GAP-368: Evidence pack assembly pipeline."""

import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from router_service.evidence_pack_assembler import (
    EvidencePackAssembler,
    EvidencePackConfig,
    create_evidence_pack,
    get_evidence_pack_info,
)


class TestEvidencePackAssembler(unittest.TestCase):
    """Test cases for the evidence pack assembler."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = EvidencePackConfig(
            policies_dir=str(self.temp_dir / "policies"),
            audit_logs_dir=str(self.temp_dir / "audit"),
            dp_ledger_dir=str(self.temp_dir / "dp"),
            retention_logs_dir=str(self.temp_dir / "retention"),
            slo_reports_dir=str(self.temp_dir / "slo"),
            output_dir=str(self.temp_dir / "output"),
            days_back=7,
        )
        self.assembler = EvidencePackAssembler(self.config)

        # Create test directories
        for dir_name in ["policies", "audit", "dp", "retention", "slo", "output"]:
            (self.temp_dir / dir_name).mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_config_initialization(self):
        """Test evidence pack config initialization."""
        config = EvidencePackConfig()

        self.assertEqual(config.days_back, 30)
        self.assertEqual(config.compression_level, 6)
        self.assertIsNotNone(config.policy_patterns)
        self.assertIsNotNone(config.audit_patterns)
        self.assertIn("policy*.yaml", config.policy_patterns)
        self.assertIn("*audit*.jsonl", config.audit_patterns)

    def test_assemble_pack_basic(self):
        """Test basic evidence pack assembly."""
        # Create test policy file
        policy_file = self.temp_dir / "policies" / "policy_test.yaml"
        policy_content = {"rules": [{"match": {"tenant": "*"}, "effect": "allow"}]}
        import yaml

        with open(policy_file, "w") as f:
            yaml.dump(policy_content, f)

        pack = self.assembler.assemble_pack("test-pack-001")

        self.assertEqual(pack.manifest.pack_id, "test-pack-001")
        self.assertIn("policy_test.yaml", pack.policies)
        self.assertIsInstance(pack.audit_chain, list)
        self.assertIsInstance(pack.dp_ledger, list)
        self.assertIsInstance(pack.retention_logs, list)
        self.assertIsInstance(pack.slo_reports, dict)

    def test_collect_policies(self):
        """Test policy collection from files."""
        # Create test policy files that match the default patterns
        yaml_policy = self.temp_dir / "policies" / "policy_test.yaml"
        json_policy = self.temp_dir / "policies" / "policy_test.json"

        yaml_content = {"rules": [{"match": {"tenant": "acme"}, "effect": "allow"}]}
        json_content = {"rules": [{"match": {"tenant": "*"}, "effect": "deny"}]}

        import yaml

        with open(yaml_policy, "w") as f:
            yaml.dump(yaml_content, f)

        with open(json_policy, "w") as f:
            json.dump(json_content, f)

        policies = self.assembler._collect_policies()

        self.assertEqual(len(policies), 2)
        self.assertIn("policy_test.yaml", policies)
        self.assertIn("policy_test.json", policies)
        self.assertEqual(policies["policy_test.yaml"], yaml_content)
        self.assertEqual(policies["policy_test.json"], json_content)

    def test_collect_audit_chain(self):
        """Test audit chain collection with time filtering."""
        # Create test audit file
        audit_file = self.temp_dir / "audit" / "test_audit.jsonl"
        now = datetime.now()

        audit_entries = [
            {"timestamp": (now - timedelta(days=1)).isoformat(), "event": "login", "user": "alice"},
            {"timestamp": (now - timedelta(days=10)).isoformat(), "event": "logout", "user": "bob"},
            {"time": now.isoformat(), "event": "access", "user": "charlie"},
        ]

        with open(audit_file, "w") as f:
            for entry in audit_entries:
                f.write(json.dumps(entry) + "\n")

        time_range = {"start": (now - timedelta(days=2)).isoformat(), "end": now.isoformat()}

        audit_chain = self.assembler._collect_audit_chain(time_range)

        # Should include entries from last 2 days
        self.assertEqual(len(audit_chain), 2)
        events = [entry["event"] for entry in audit_chain]
        self.assertIn("login", events)
        self.assertIn("access", events)
        self.assertNotIn("logout", events)  # Too old

    def test_collect_dp_ledger(self):
        """Test DP ledger collection."""
        # Create test DP ledger file
        dp_file = self.temp_dir / "dp" / "test_dp.jsonl"
        now = datetime.now()

        dp_entries = [
            {"timestamp": now.isoformat(), "privacy_budget_used": 0.1, "query_type": "count"},
            {"timestamp": (now - timedelta(days=1)).isoformat(), "privacy_budget_used": 0.2, "query_type": "sum"},
        ]

        with open(dp_file, "w") as f:
            for entry in dp_entries:
                f.write(json.dumps(entry) + "\n")

        time_range = {"start": (now - timedelta(days=2)).isoformat(), "end": now.isoformat()}

        dp_ledger = self.assembler._collect_dp_ledger(time_range)

        self.assertEqual(len(dp_ledger), 2)
        query_types = [entry["query_type"] for entry in dp_ledger]
        self.assertIn("count", query_types)
        self.assertIn("sum", query_types)

    def test_collect_retention_logs(self):
        """Test retention logs collection."""
        # Create test retention log file
        retention_file = self.temp_dir / "retention" / "test_retention.jsonl"
        now = datetime.now()

        retention_entries = [
            {"timestamp": now.isoformat(), "action": "delete", "data_type": "logs", "age_days": 90},
            {
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "action": "archive",
                "data_type": "metrics",
                "age_days": 30,
            },
        ]

        with open(retention_file, "w") as f:
            for entry in retention_entries:
                f.write(json.dumps(entry) + "\n")

        time_range = {"start": (now - timedelta(days=2)).isoformat(), "end": now.isoformat()}

        retention_logs = self.assembler._collect_retention_logs(time_range)

        self.assertEqual(len(retention_logs), 2)
        actions = [entry["action"] for entry in retention_logs]
        self.assertIn("delete", actions)
        self.assertIn("archive", actions)

    def test_collect_slo_reports(self):
        """Test SLO reports collection."""
        # Create test SLM observations file
        slm_file = self.temp_dir / "slo" / "slm_observations_test.jsonl"
        now = datetime.now()

        slm_entries = [
            {"timestamp": now.isoformat(), "service": "router", "latency_p95": 150, "error_rate": 0.02},
            {
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "service": "memory",
                "latency_p95": 200,
                "error_rate": 0.01,
            },
        ]

        with open(slm_file, "w") as f:
            for entry in slm_entries:
                f.write(json.dumps(entry) + "\n")

        # Create test counters file
        counters_file = self.temp_dir / "slo" / "test_counters.json"
        counters_data = {"requests_total": 10000, "errors_total": 200, "latency_sum": 1500000}

        with open(counters_file, "w") as f:
            json.dump(counters_data, f)

        time_range = {"start": (now - timedelta(days=2)).isoformat(), "end": now.isoformat()}

        slo_reports = self.assembler._collect_slo_reports(time_range)

        self.assertIn("slm_observations", slo_reports)
        self.assertEqual(len(slo_reports["slm_observations"]), 2)
        self.assertIn("counters_test_counters", slo_reports)
        self.assertEqual(slo_reports["counters_test_counters"]["requests_total"], 10000)

    def test_save_pack(self):
        """Test saving evidence pack to disk."""
        # Create a simple pack
        pack = self.assembler.assemble_pack("test-save-pack")

        output_path = self.assembler.save_pack(pack)

        # Verify the zip file was created
        self.assertTrue(os.path.exists(output_path))

        # Verify contents
        with zipfile.ZipFile(output_path, "r") as zf:
            files = zf.namelist()
            self.assertIn("manifest.json", files)

            # Read manifest
            with zf.open("manifest.json") as f:
                manifest = json.load(f)
                self.assertEqual(manifest["pack_id"], "test-save-pack")
                self.assertIn("components", manifest)

    def test_get_evidence_pack_info(self):
        """Test getting information about an evidence pack."""
        # Create and save a pack
        pack = self.assembler.assemble_pack("test-info-pack")
        pack_path = self.assembler.save_pack(pack)

        # Get pack info
        info = get_evidence_pack_info(pack_path)

        self.assertIn("manifest", info)
        self.assertIn("files", info)
        self.assertIn("total_size", info)
        self.assertEqual(info["manifest"]["pack_id"], "test-info-pack")
        self.assertIsInstance(info["files"], list)
        self.assertGreater(info["total_size"], 0)

    def test_time_range_calculation(self):
        """Test time range calculation."""
        time_range = self.assembler._calculate_time_range()

        self.assertIn("start", time_range)
        self.assertIn("end", time_range)

        start_time = datetime.fromisoformat(time_range["start"])
        end_time = datetime.fromisoformat(time_range["end"])

        # Should be approximately config.days_back apart
        time_diff = end_time - start_time
        expected_diff = timedelta(days=self.config.days_back)
        self.assertAlmostEqual(time_diff.total_seconds(), expected_diff.total_seconds(), delta=60)  # 1 minute tolerance

    def test_entry_time_filtering(self):
        """Test filtering entries by time range."""
        now = datetime.now()
        start_time = now - timedelta(days=1)
        end_time = now

        # Test entry with timestamp field
        entry_with_timestamp = {"timestamp": now.isoformat(), "event": "test"}
        self.assertTrue(self.assembler._entry_in_time_range(entry_with_timestamp, start_time, end_time))

        # Test entry with time field
        entry_with_time = {"time": (now - timedelta(hours=1)).isoformat(), "event": "test"}
        self.assertTrue(self.assembler._entry_in_time_range(entry_with_time, start_time, end_time))

        # Test entry outside time range
        old_entry = {"timestamp": (now - timedelta(days=2)).isoformat(), "event": "test"}
        self.assertFalse(self.assembler._entry_in_time_range(old_entry, start_time, end_time))

        # Test entry without timestamp (should be included)
        entry_no_timestamp = {"event": "test", "data": "value"}
        self.assertTrue(self.assembler._entry_in_time_range(entry_no_timestamp, start_time, end_time))

    def test_custom_time_range(self):
        """Test using custom time range for pack assembly."""
        custom_time_range = {"start": "2024-01-01T00:00:00", "end": "2024-01-31T23:59:59"}

        pack = self.assembler.assemble_pack("custom-time-pack", custom_time_range)

        self.assertEqual(pack.manifest.time_range, custom_time_range)

    def test_missing_directories(self):
        """Test handling of missing data directories."""
        # Use non-existent directories
        config = EvidencePackConfig(
            policies_dir="/non/existent/policies",
            audit_logs_dir="/non/existent/audit",
            dp_ledger_dir="/non/existent/dp",
            retention_logs_dir="/non/existent/retention",
            slo_reports_dir="/non/existent/slo",
        )
        assembler = EvidencePackAssembler(config)

        pack = assembler.assemble_pack("missing-dirs-pack")

        # Should still create pack with empty components
        self.assertEqual(len(pack.policies), 0)
        self.assertEqual(len(pack.audit_chain), 0)
        self.assertEqual(len(pack.dp_ledger), 0)
        self.assertEqual(len(pack.retention_logs), 0)
        self.assertEqual(len(pack.slo_reports), 0)

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON files."""
        # Create file with invalid JSON
        bad_file = self.temp_dir / "policies" / "bad_policy.json"
        with open(bad_file, "w") as f:
            f.write("invalid json content {")

        policies = self.assembler._collect_policies()

        # Should handle error gracefully and continue
        self.assertIsInstance(policies, dict)
        # bad_policy.json should not be included due to parsing error

    def test_create_evidence_pack_function(self):
        """Test the convenience function for creating evidence packs."""
        pack = create_evidence_pack("convenience-pack", save_to_disk=False)

        self.assertEqual(pack.manifest.pack_id, "convenience-pack")
        self.assertIsInstance(pack.policies, dict)
        self.assertIsInstance(pack.audit_chain, list)

    def test_manifest_structure(self):
        """Test evidence pack manifest structure."""
        pack = self.assembler.assemble_pack("manifest-test-pack")

        manifest = pack.manifest
        self.assertEqual(manifest.pack_id, "manifest-test-pack")
        self.assertEqual(manifest.version, "1.0")
        self.assertIsInstance(manifest.created_at, str)  # created_at is a string timestamp
        self.assertIn("start", manifest.time_range)
        self.assertIn("end", manifest.time_range)
        self.assertIsInstance(manifest.components, dict)

        # Check components structure
        self.assertIn("policies", manifest.components)
        self.assertIn("audit_chain", manifest.components)
        self.assertIn("dp_ledger", manifest.components)
        self.assertIn("retention_logs", manifest.components)
        self.assertIn("slo_reports", manifest.components)


class TestEvidencePackConfig(unittest.TestCase):
    """Test cases for EvidencePackConfig."""

    def test_default_patterns(self):
        """Test default file patterns in config."""
        config = EvidencePackConfig()

        self.assertIn("policy*.yaml", config.policy_patterns)
        self.assertIn("policy*.json", config.policy_patterns)
        self.assertIn("*audit*.jsonl", config.audit_patterns)
        self.assertIn("admin_audit.jsonl", config.audit_patterns)
        self.assertIn("*dp*.jsonl", config.dp_patterns)
        self.assertIn("lifecycle*.jsonl", config.retention_patterns)
        self.assertIn("slm_observations*.jsonl", config.slo_patterns)

    def test_custom_patterns(self):
        """Test custom file patterns."""
        custom_patterns = ["custom*.yaml"]
        config = EvidencePackConfig(policy_patterns=custom_patterns)

        self.assertEqual(config.policy_patterns, custom_patterns)


if __name__ == "__main__":
    unittest.main()
