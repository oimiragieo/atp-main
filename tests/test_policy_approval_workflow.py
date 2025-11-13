#!/usr/bin/env python3
"""
Tests for Policy Change Approval Workflow

Comprehensive test suite covering:
- Request creation and lifecycle
- Approval and rejection workflows
- Multi-stage approvals
- Expiration handling
- Audit trail verification
- Integration with policy systems
"""

# Import the approval workflow
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from policy_approval_workflow import ApprovalState, PolicyApprovalWorkflow, PolicyChangeGating


class MockPolicySystem:
    """Mock policy system for testing."""

    def __init__(self):
        self.policies = {}

    def set_policy(self, policy_id: str, policy: dict):
        self.policies[policy_id] = policy

    def get_policy(self, policy_id: str):
        return self.policies.get(policy_id)


def test_request_creation():
    """Test creating policy change requests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        # Test basic request creation
        request_id = workflow.create_request(
            policy_type="ingestion_policy",
            policy_id="user_data_schema",
            change_type="update",
            current_policy={"allow_ingestion": True},
            proposed_policy={"allow_ingestion": False, "max_size_bytes": 1024},
            justification="Security hardening",
            requester="alice",
            required_approvers=["bob", "charlie"],
        )

        assert request_id.startswith("PCR-")
        request = workflow.get_request(request_id)
        assert request is not None
        assert request.policy_type == "ingestion_policy"
        assert request.policy_id == "user_data_schema"
        assert request.change_type == "update"
        assert request.requester == "alice"
        assert request.state == ApprovalState.PENDING
        assert len(request.required_approvers) == 2
        assert len(request.audit_trail) == 1  # Creation entry


def test_approval_workflow():
    """Test the complete approval workflow."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        # Create a request
        request_id = workflow.create_request(
            policy_type="access_policy",
            policy_id="admin_role",
            change_type="create",
            current_policy=None,
            proposed_policy={"permissions": ["read", "write", "admin"]},
            justification="New admin role for compliance team",
            requester="alice",
            required_approvers=["bob", "charlie"],
        )

        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.PENDING

        # First approval
        workflow.approve_request(request_id, "bob", "Looks good for security")
        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.PENDING  # Still needs charlie
        assert "bob" in request.current_approvals
        assert len(request.audit_trail) == 2  # Creation + approval

        # Second approval - should complete
        workflow.approve_request(request_id, "charlie", "Approved for compliance")
        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.APPROVED
        assert "charlie" in request.current_approvals
        assert len(request.audit_trail) == 4  # Creation + 2 approvals + final approval


def test_rejection_workflow():
    """Test request rejection."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        request_id = workflow.create_request(
            policy_type="ingestion_policy",
            policy_id="test_schema",
            change_type="update",
            current_policy={"allow_ingestion": True},
            proposed_policy={"allow_ingestion": False},
            justification="Test rejection",
            requester="alice",
            required_approvers=["bob"],
        )

        # Reject the request
        workflow.reject_request(request_id, "bob", "Policy change too restrictive")
        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.REJECTED
        assert request.rejection_reason == "Policy change too restrictive"
        assert len(request.audit_trail) == 2  # Creation + rejection


def test_cancellation_workflow():
    """Test request cancellation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        request_id = workflow.create_request(
            policy_type="access_policy",
            policy_id="test_role",
            change_type="create",
            current_policy=None,
            proposed_policy={"permissions": ["read"]},
            justification="Test cancellation",
            requester="alice",
            required_approvers=["bob"],
        )

        # Cancel the request
        workflow.cancel_request(request_id, "alice", "No longer needed")
        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.CANCELLED
        assert len(request.audit_trail) == 2  # Creation + cancellation


def test_expiration_handling():
    """Test automatic expiration of requests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        # Create a request that expires in 1 second
        request_id = workflow.create_request(
            policy_type="test_policy",
            policy_id="test_id",
            change_type="update",
            current_policy={},
            proposed_policy={"test": True},
            justification="Test expiration",
            requester="alice",
            required_approvers=["bob"],
            expiry_hours=1 / 3600,  # 1 second
        )

        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.PENDING

        # Wait for expiration
        time.sleep(2)

        # Process expired requests
        expired_ids = workflow.process_expired_requests()
        assert request_id in expired_ids

        request = workflow.get_request(request_id)
        assert request.state == ApprovalState.EXPIRED
        assert len(request.audit_trail) == 2  # Creation + expiration


def test_request_filtering():
    """Test filtering and listing requests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        # Create multiple requests
        workflow.create_request("policy1", "id1", "create", None, {}, "test1", "alice", ["bob"])
        workflow.create_request("policy2", "id2", "update", {}, {}, "test2", "alice", ["charlie"])
        workflow.create_request("policy1", "id3", "delete", {}, None, "test3", "bob", ["alice"])

        # Test filtering by state
        pending = workflow.list_requests(state=ApprovalState.PENDING)
        assert len(pending) == 3

        # Test filtering by requester
        alice_requests = workflow.list_requests(requester="alice")
        assert len(alice_requests) == 2

        # Test filtering by policy type
        policy1_requests = workflow.list_requests(policy_type="policy1")
        assert len(policy1_requests) == 2


def test_authorization_checks():
    """Test authorization and permission checks."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        request_id = workflow.create_request(
            "test_policy", "test_id", "update", {}, {}, "test", "alice", ["bob", "charlie"]
        )

        # Test unauthorized approval
        with pytest.raises(ValueError, match="not an authorized approver"):
            workflow.approve_request(request_id, "dave")

        # Test approval by authorized user
        workflow.approve_request(request_id, "bob")
        request = workflow.get_request(request_id)
        assert "bob" in request.current_approvals

        # Test duplicate approval (should not error but not add duplicate)
        initial_count = len(request.current_approvals)
        workflow.approve_request(request_id, "bob")
        assert len(request.current_approvals) == initial_count


def test_persistence():
    """Test request persistence to disk."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage_path = Path(temp_dir)

        # Create workflow and add request
        workflow1 = PolicyApprovalWorkflow(storage_path)
        request_id = workflow1.create_request(
            "test_policy", "test_id", "create", None, {"test": True}, "test", "alice", ["bob"]
        )

        # Create new workflow instance (simulating restart)
        workflow2 = PolicyApprovalWorkflow(storage_path)

        # Verify request was loaded
        request = workflow2.get_request(request_id)
        assert request is not None
        assert request.policy_type == "test_policy"
        assert request.requester == "alice"
        assert request.state == ApprovalState.PENDING


def test_policy_change_gating():
    """Test integration with policy change gating."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))
        gating = PolicyChangeGating(workflow)
        mock_policy_system = MockPolicySystem()

        # Request a policy change
        request_id = gating.request_policy_change(
            policy_type="ingestion_policy",
            policy_id="test_schema",
            change_type="update",
            current_policy={"allow_ingestion": True},
            proposed_policy={"allow_ingestion": False},
            justification="Security enhancement",
            requester="alice",
            required_approvers=["bob"],
        )

        # Verify request was created
        request = workflow.get_request(request_id)
        assert request is not None
        assert request.state == ApprovalState.PENDING

        # Approve the request
        workflow.approve_request(request_id, "bob")

        # Apply the approved change
        success = gating.apply_approved_change(request_id, mock_policy_system)
        assert success

        # Verify policy was applied
        applied_policy = mock_policy_system.get_policy("test_schema")
        assert applied_policy == {"allow_ingestion": False}


def test_audit_trail_completeness():
    """Test that audit trail captures all actions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        request_id = workflow.create_request(
            "test_policy", "test_id", "update", {}, {}, "test", "alice", ["bob", "charlie"]
        )

        request = workflow.get_request(request_id)

        # Check initial audit trail
        assert len(request.audit_trail) == 1
        assert request.audit_trail[0]["action"] == "creation"
        assert request.audit_trail[0]["user"] == "alice"

        # Add approval
        workflow.approve_request(request_id, "bob", "Approved for security reasons")
        assert len(request.audit_trail) == 2
        assert request.audit_trail[1]["action"] == "approval"
        assert request.audit_trail[1]["user"] == "bob"
        assert "security reasons" in request.audit_trail[1]["details"]

        # Add second approval (completes request)
        workflow.approve_request(request_id, "charlie", "Compliance approved")
        assert len(request.audit_trail) == 4  # creation + approval + approval + final_approval
        assert request.audit_trail[-1]["action"] == "final_approval"


def test_metrics_tracking():
    """Test metrics tracking for pending policy changes."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow = PolicyApprovalWorkflow(Path(temp_dir))

        # Initially no pending requests
        assert workflow.get_pending_count() == 0

        # Create a request
        request_id1 = workflow.create_request("policy1", "id1", "create", None, {}, "test", "alice", ["bob"])
        assert workflow.get_pending_count() == 1

        # Create another request
        request_id2 = workflow.create_request("policy2", "id2", "update", {}, {}, "test", "alice", ["charlie"])
        assert workflow.get_pending_count() == 2

        # Approve first request
        workflow.approve_request(request_id1, "bob")
        assert workflow.get_pending_count() == 1

        # Reject second request
        workflow.reject_request(request_id2, "charlie", "Not approved")
        assert workflow.get_pending_count() == 0


if __name__ == "__main__":
    # Run all tests
    test_request_creation()
    test_approval_workflow()
    test_rejection_workflow()
    test_cancellation_workflow()
    test_expiration_handling()
    test_request_filtering()
    test_authorization_checks()
    test_persistence()
    test_policy_change_gating()
    test_audit_trail_completeness()
    test_metrics_tracking()

    print("✅ All policy approval workflow tests passed!")
