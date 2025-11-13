"""
Tests for GAP-310: Cross-namespace access audit & anomaly detection.
"""

import importlib.util
import os
import sys
import tempfile
import types
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from metrics import MEMORY_ACCESS_ANOMALIES_TOTAL

# Set up environment variables before importing modules
os.environ["AUDIT_SECRET"] = "test-secret-key"  # noqa: S105
os.environ["ANOMALY_THRESHOLD"] = "5"  # Lower threshold for testing

# Create temporary audit log file
temp_audit_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
temp_audit_file.close()
os.environ["AUDIT_PATH"] = temp_audit_file.name

# Import memory_gateway modules using importlib due to hyphen in directory name
memory_gateway_path = os.path.join(os.path.dirname(__file__), "..", "memory-gateway")

# Create a fake memory_gateway module
memory_gateway = types.ModuleType("memory_gateway")
sys.modules["memory_gateway"] = memory_gateway

# Import audit_log first
spec = importlib.util.spec_from_file_location(
    "memory_gateway.audit_log", os.path.join(memory_gateway_path, "audit_log.py")
)
memory_gateway_audit = importlib.util.module_from_spec(spec)
sys.modules["memory_gateway.audit_log"] = memory_gateway_audit
spec.loader.exec_module(memory_gateway_audit)

# Import app
spec = importlib.util.spec_from_file_location("memory_gateway.app", os.path.join(memory_gateway_path, "app.py"))
memory_gateway_app = importlib.util.module_from_spec(spec)
sys.modules["memory_gateway.app"] = memory_gateway_app
spec.loader.exec_module(memory_gateway_app)

app = memory_gateway_app.app
verify_log = memory_gateway_audit.verify_log


class TestCrossNamespaceAudit:
    """Test cases for cross-namespace access audit and anomaly detection."""

    @pytest.fixture
    def client(self):
        """Create test client with temporary audit log."""
        # Reset global state for clean test environment
        memory_gateway_app.PREV_HASH = None
        memory_gateway_app.TENANT_ACCESS_HISTORY.clear()
        memory_gateway_app.NAMESPACE_ACCESS_PATTERNS.clear()

        # Environment variables are already set at module level
        client = TestClient(app)

        yield client

        # Cleanup - remove the temporary audit file
        try:
            os.unlink(temp_audit_file.name)
        except OSError:
            pass

    def test_basic_memory_operations_with_audit(self, client):
        """Test that basic memory operations create audit entries."""
        # Test PUT operation
        response = client.put(
            "/v1/memory/test_ns/test_key", json={"object": {"data": "test_value"}}, headers={"x-tenant-id": "tenant1"}
        )
        assert response.status_code == 200

        # Test GET operation
        response = client.get("/v1/memory/test_ns/test_key", headers={"x-tenant-id": "tenant1"})
        assert response.status_code == 200
        assert response.json()["object"]["data"] == "test_value"

    def test_namespace_lineage_tracking(self, client):
        """Test that namespace access patterns are tracked."""
        from memory_gateway.app import NAMESPACE_ACCESS_PATTERNS

        # Clear any existing patterns
        NAMESPACE_ACCESS_PATTERNS.clear()

        # Perform operations across different namespaces
        client.put("/v1/memory/ns1/key1", json={"object": {"data": "value1"}}, headers={"x-tenant-id": "tenant1"})

        client.put("/v1/memory/ns2/key2", json={"object": {"data": "value2"}}, headers={"x-tenant-id": "tenant1"})

        # Check that access patterns are recorded
        assert NAMESPACE_ACCESS_PATTERNS["tenant1"]["ns1"] == 1
        assert NAMESPACE_ACCESS_PATTERNS["tenant1"]["ns2"] == 1

    def test_anomaly_detection_cross_namespace_access(self, client):
        """Test anomaly detection for unusual cross-namespace access patterns."""
        # Clear history
        memory_gateway_app.TENANT_ACCESS_HISTORY.clear()

        # Set low threshold for testing
        original_threshold = memory_gateway_app.ANOMALY_THRESHOLD
        try:
            memory_gateway_app.ANOMALY_THRESHOLD = 3  # Low threshold for testing

            # Reset metric counter
            initial_count = MEMORY_ACCESS_ANOMALIES_TOTAL.value

            # Perform many accesses to different namespaces quickly
            for i in range(6):  # More than threshold
                ns = f"ns{i}"
                client.put(
                    f"/v1/memory/{ns}/key",
                    json={"object": {"data": f"value{i}"}},
                    headers={"x-tenant-id": "suspicious_tenant"},
                )

            # Check that anomaly was detected
            final_count = MEMORY_ACCESS_ANOMALIES_TOTAL.value
            assert final_count > initial_count, "Anomaly should have been detected"

        finally:
            # Restore original threshold
            memory_gateway_app.ANOMALY_THRESHOLD = original_threshold

    def test_audit_log_integrity(self, client):
        """Test that audit log maintains integrity and can be verified."""
        # Reset the global PREV_HASH for this test
        memory_gateway_app.PREV_HASH = None

        # Perform some operations to create audit entries
        client.put(
            "/v1/memory/test_ns/test_key", json={"object": {"data": "test_value"}}, headers={"x-tenant-id": "tenant1"}
        )

        # Verify audit log integrity
        secret = os.environ["AUDIT_SECRET"].encode()
        assert verify_log(temp_audit_file.name, secret), "Audit log should be verifiable"

    def test_tenant_isolation_in_audit(self, client):
        """Test that different tenants are properly isolated in audit logs."""
        # Operations by different tenants
        client.put(
            "/v1/memory/shared_ns/key1", json={"object": {"data": "tenant1_data"}}, headers={"x-tenant-id": "tenant1"}
        )

        client.put(
            "/v1/memory/shared_ns/key2", json={"object": {"data": "tenant2_data"}}, headers={"x-tenant-id": "tenant2"}
        )

        # Each should be recorded separately in audit
        from memory_gateway.app import NAMESPACE_ACCESS_PATTERNS

        assert NAMESPACE_ACCESS_PATTERNS["tenant1"]["shared_ns"] == 1
        assert NAMESPACE_ACCESS_PATTERNS["tenant2"]["shared_ns"] == 1

    def test_get_not_found_audit(self, client):
        """Test that GET operations for non-existent keys are audited."""
        response = client.get("/v1/memory/test_ns/nonexistent_key", headers={"x-tenant-id": "tenant1"})
        assert response.status_code == 200
        assert response.json()["error"] == "not_found"

        # Should still be recorded in access patterns
        from memory_gateway.app import NAMESPACE_ACCESS_PATTERNS

        assert NAMESPACE_ACCESS_PATTERNS["tenant1"]["test_ns"] >= 1

    def test_anomaly_metric_increment(self, client):
        """Test that anomaly detection properly increments metrics."""
        # Clear history
        memory_gateway_app.TENANT_ACCESS_HISTORY.clear()

        # Mock the metric
        with patch.object(memory_gateway_app, "MEMORY_ACCESS_ANOMALIES_TOTAL") as mock_metric:
            # Trigger anomaly condition
            original_threshold = memory_gateway_app.ANOMALY_THRESHOLD
            try:
                memory_gateway_app.ANOMALY_THRESHOLD = 1  # Very low threshold

                # Perform multiple namespace accesses quickly (more than 5 to trigger anomaly)
                for i in range(7):
                    client.put(
                        f"/v1/memory/ns{i}/key",
                        json={"object": {"data": f"value{i}"}},
                        headers={"x-tenant-id": "test_tenant"},
                    )

                # Verify metric was incremented
                mock_metric.inc.assert_called()

            finally:
                memory_gateway_app.ANOMALY_THRESHOLD = original_threshold

    def test_audit_event_structure(self, client):
        """Test that audit events have the correct structure."""
        import json

        # Perform operation
        client.put(
            "/v1/memory/test_ns/test_key", json={"object": {"data": "test_value"}}, headers={"x-tenant-id": "tenant1"}
        )

        # Read audit log and check structure
        with open(temp_audit_file.name) as f:
            lines = f.readlines()
            assert len(lines) > 0

            # Parse last audit entry
            last_entry = json.loads(lines[-1])
            assert "event" in last_entry
            assert "prev" in last_entry
            assert "hmac" in last_entry
            assert "hash" in last_entry

    def test_input_validation_invalid_namespace(self, client):
        """Test input validation for invalid namespace."""
        # Test empty namespace
        response = client.put("/v1/memory//test_key", json={"object": {"data": "test"}})
        assert response.status_code == 404  # FastAPI handles empty path parameters as 404

        # Test namespace with invalid characters
        response = client.put(
            "/v1/memory/invalid@namespace/test_key",
            json={"object": {"data": "test"}},
            headers={"x-tenant-id": "tenant1"},
        )
        assert response.status_code == 400
        assert "invalid characters" in response.json()["detail"]

        # Test overly long namespace
        long_ns = "a" * 101
        response = client.put(
            f"/v1/memory/{long_ns}/test_key", json={"object": {"data": "test"}}, headers={"x-tenant-id": "tenant1"}
        )
        assert response.status_code == 400
        assert "too long" in response.json()["detail"]

    def test_input_validation_invalid_key(self, client):
        """Test input validation for invalid key."""
        # Test empty key
        response = client.put("/v1/memory/test_ns/", json={"object": {"data": "test"}})
        assert response.status_code == 404  # FastAPI handles empty path parameters as 404

        # Test key with invalid characters
        response = client.put(
            "/v1/memory/test_ns/invalid@key", json={"object": {"data": "test"}}, headers={"x-tenant-id": "tenant1"}
        )
        assert response.status_code == 400
        assert "invalid characters" in response.json()["detail"]

        # Test overly long key
        long_key = "a" * 201
        response = client.put(
            f"/v1/memory/test_ns/{long_key}", json={"object": {"data": "test"}}, headers={"x-tenant-id": "tenant1"}
        )
        assert response.status_code == 400
        assert "too long" in response.json()["detail"]

    def test_input_validation_invalid_tenant_id(self, client):
        """Test input validation for invalid tenant ID."""
        # Test missing tenant ID header
        response = client.put("/v1/memory/test_ns/test_key", json={"object": {"data": "test"}})
        assert response.status_code == 422  # FastAPI validation error

        # Test empty tenant ID
        response = client.put(
            "/v1/memory/test_ns/test_key", json={"object": {"data": "test"}}, headers={"x-tenant-id": ""}
        )
        assert response.status_code == 400
        assert "cannot be empty" in response.json()["detail"]

        # Test tenant ID with invalid characters
        response = client.put(
            "/v1/memory/test_ns/test_key", json={"object": {"data": "test"}}, headers={"x-tenant-id": "invalid@tenant"}
        )
        assert response.status_code == 400
        assert "invalid characters" in response.json()["detail"]

    def test_input_validation_consistency_level(self, client):
        """Test input validation for consistency level."""
        # Test invalid consistency level
        response = client.get(
            "/v1/memory/test_ns/test_key", headers={"x-tenant-id": "tenant1", "x-consistency-level": "INVALID"}
        )
        assert response.status_code == 400
        assert "Invalid consistency level" in response.json()["detail"]

        # Test valid consistency levels
        response = client.get(
            "/v1/memory/test_ns/test_key", headers={"x-tenant-id": "tenant1", "x-consistency-level": "EVENTUAL"}
        )
        assert response.status_code == 200

        response = client.get(
            "/v1/memory/test_ns/test_key", headers={"x-tenant-id": "tenant1", "x-consistency-level": "STRONG"}
        )
        assert response.status_code == 200
