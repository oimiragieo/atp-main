#!/usr/bin/env python3
"""
Policy Change Approval Workflow

This module implements a comprehensive approval workflow for policy changes
in the ATP system. It supports multi-stage approvals, audit trails, and
compliance with change management requirements (SOC2 CC7.1).

Key Features:
- Multi-stage approval process with configurable approvers
- Policy change requests with detailed justification
- Approval states: PENDING, APPROVED, REJECTED, EXPIRED
- Audit trail for all approval actions
- Automatic expiration of stale requests
- Integration with existing policy systems
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Import metrics
from metrics import (
    POLICY_APPROVAL_LATENCY,
    POLICY_CHANGE_REQUESTS_APPROVED_TOTAL,
    POLICY_CHANGE_REQUESTS_EXPIRED_TOTAL,
    POLICY_CHANGE_REQUESTS_PENDING,
    POLICY_CHANGE_REQUESTS_REJECTED_TOTAL,
    POLICY_CHANGE_REQUESTS_TOTAL,
)


class ApprovalState(Enum):
    """Approval states for policy change requests."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalStage(Enum):
    """Approval stages in the workflow."""

    SECURITY_REVIEW = "security_review"
    COMPLIANCE_REVIEW = "compliance_review"
    BUSINESS_APPROVAL = "business_approval"
    FINAL_APPROVAL = "final_approval"


@dataclass
class PolicyChangeRequest:
    """Represents a policy change request."""

    request_id: str
    policy_type: str  # e.g., "ingestion_policy", "access_policy"
    policy_id: str  # e.g., schema_id or resource_id
    change_type: str  # e.g., "create", "update", "delete"
    current_policy: dict[str, Any] | None
    proposed_policy: dict[str, Any]
    justification: str
    requester: str
    created_at: datetime
    expires_at: datetime
    required_approvers: list[str]
    current_approvals: list[str] = None
    rejection_reason: str | None = None
    state: ApprovalState = ApprovalState.PENDING
    audit_trail: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.current_approvals is None:
            self.current_approvals = []
        if self.audit_trail is None:
            self.audit_trail = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        data["state"] = self.state.value
        # Convert datetimes to ISO strings
        data["created_at"] = self.created_at.isoformat()
        data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyChangeRequest":
        """Create from dictionary."""
        # Convert strings back to enums
        data["state"] = ApprovalState(data["state"])
        # Convert ISO strings back to datetimes
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)

    def is_expired(self) -> bool:
        """Check if the request has expired."""
        return datetime.now() > self.expires_at

    def is_approved(self) -> bool:
        """Check if the request has all required approvals."""
        return set(self.current_approvals) == set(self.required_approvers)

    def add_approval(self, approver: str, comments: str = "") -> None:
        """Add an approval from a user."""
        if approver not in self.current_approvals:
            self.current_approvals.append(approver)
            self._add_audit_entry("approval", approver, comments)

    def reject(self, rejector: str, reason: str) -> None:
        """Reject the request."""
        self.state = ApprovalState.REJECTED
        self.rejection_reason = reason
        self._add_audit_entry("rejection", rejector, reason)

    def cancel(self, canceller: str, reason: str = "") -> None:
        """Cancel the request."""
        self.state = ApprovalState.CANCELLED
        self._add_audit_entry("cancellation", canceller, reason)

    def _add_audit_entry(self, action: str, user: str, details: str = "") -> None:
        """Add an entry to the audit trail."""
        entry = {"timestamp": datetime.now().isoformat(), "action": action, "user": user, "details": details}
        self.audit_trail.append(entry)


class PolicyApprovalWorkflow:
    """Manages the policy change approval workflow."""

    def __init__(self, storage_path: Path | None = None, secret: bytes = b"default-approval-secret"):
        self.requests: dict[str, PolicyChangeRequest] = {}
        self.storage_path = storage_path or Path("data/policy_approvals")
        self.secret = secret
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._load_requests()

    def create_request(
        self,
        policy_type: str,
        policy_id: str,
        change_type: str,
        current_policy: dict[str, Any] | None,
        proposed_policy: dict[str, Any],
        justification: str,
        requester: str,
        required_approvers: list[str],
        expiry_hours: int = 168,  # 7 days default
    ) -> str:
        """Create a new policy change request."""
        request_id = self._generate_request_id(policy_type, policy_id, requester)
        expires_at = datetime.now() + timedelta(hours=expiry_hours)

        request = PolicyChangeRequest(
            request_id=request_id,
            policy_type=policy_type,
            policy_id=policy_id,
            change_type=change_type,
            current_policy=current_policy,
            proposed_policy=proposed_policy,
            justification=justification,
            requester=requester,
            created_at=datetime.now(),
            expires_at=expires_at,
            required_approvers=required_approvers,
        )

        # Add creation audit entry
        request._add_audit_entry("creation", requester, f"Created {change_type} request for {policy_type}:{policy_id}")

        self.requests[request_id] = request
        self._save_request(request)

        # Update metrics
        POLICY_CHANGE_REQUESTS_TOTAL.inc()
        POLICY_CHANGE_REQUESTS_PENDING.inc()

        return request_id

    def approve_request(self, request_id: str, approver: str, comments: str = "") -> bool:
        """Approve a policy change request."""
        request = self.requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.state != ApprovalState.PENDING:
            raise ValueError(f"Request {request_id} is not in pending state")

        if approver not in request.required_approvers:
            raise ValueError(f"User {approver} is not an authorized approver")

        request.add_approval(approver, comments)

        if request.is_approved():
            request.state = ApprovalState.APPROVED
            request._add_audit_entry("final_approval", approver, "All required approvals received")

            # Update metrics for approval
            POLICY_CHANGE_REQUESTS_APPROVED_TOTAL.inc()
            POLICY_CHANGE_REQUESTS_PENDING.dec()

            # Track approval latency
            latency_seconds = (datetime.now() - request.created_at).total_seconds()
            POLICY_APPROVAL_LATENCY.observe(latency_seconds)

        self._save_request(request)
        return request.state == ApprovalState.APPROVED

    def reject_request(self, request_id: str, rejector: str, reason: str) -> None:
        """Reject a policy change request."""
        request = self.requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.state != ApprovalState.PENDING:
            raise ValueError(f"Request {request_id} is not in pending state")

        request.reject(rejector, reason)
        self._save_request(request)

        # Update metrics
        POLICY_CHANGE_REQUESTS_REJECTED_TOTAL.inc()
        POLICY_CHANGE_REQUESTS_PENDING.dec()

    def cancel_request(self, request_id: str, canceller: str, reason: str = "") -> None:
        """Cancel a policy change request."""
        request = self.requests.get(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.state != ApprovalState.PENDING:
            raise ValueError(f"Request {request_id} is not in pending state")

        if canceller != request.requester:
            raise ValueError("Only the requester can cancel the request")

        request.cancel(canceller, reason)
        self._save_request(request)

        # Update metrics (cancellation doesn't count as rejection or approval)
        POLICY_CHANGE_REQUESTS_PENDING.dec()

    def get_request(self, request_id: str) -> PolicyChangeRequest | None:
        """Get a policy change request."""
        return self.requests.get(request_id)

    def list_requests(
        self, state: ApprovalState | None = None, requester: str | None = None, policy_type: str | None = None
    ) -> list[PolicyChangeRequest]:
        """List policy change requests with optional filtering."""
        requests = list(self.requests.values())

        if state:
            requests = [r for r in requests if r.state == state]
        if requester:
            requests = [r for r in requests if r.requester == requester]
        if policy_type:
            requests = [r for r in requests if r.policy_type == policy_type]

        return sorted(requests, key=lambda r: r.created_at, reverse=True)

    def process_expired_requests(self) -> list[str]:
        """Process expired requests and return their IDs."""
        expired_ids = []
        for request_id, request in self.requests.items():
            if request.state == ApprovalState.PENDING and request.is_expired():
                request.state = ApprovalState.EXPIRED
                request._add_audit_entry("expiration", "system", "Request expired automatically")
                self._save_request(request)
                expired_ids.append(request_id)

                # Update metrics
                POLICY_CHANGE_REQUESTS_EXPIRED_TOTAL.inc()
                POLICY_CHANGE_REQUESTS_PENDING.dec()

        return expired_ids

    def get_pending_count(self) -> int:
        """Get count of pending requests."""
        return len([r for r in self.requests.values() if r.state == ApprovalState.PENDING])

    def _generate_request_id(self, policy_type: str, policy_id: str, requester: str) -> str:
        """Generate a unique request ID."""
        timestamp = str(int(time.time()))
        content = f"{policy_type}:{policy_id}:{requester}:{timestamp}"
        request_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"PCR-{request_hash}"

    def _save_request(self, request: PolicyChangeRequest) -> None:
        """Save a request to disk."""
        if not self.storage_path:
            return

        file_path = self.storage_path / f"{request.request_id}.json"
        with open(file_path, "w") as f:
            json.dump(request.to_dict(), f, indent=2)

    def _load_requests(self) -> None:
        """Load all requests from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return

        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                request = PolicyChangeRequest.from_dict(data)
                self.requests[request.request_id] = request
            except Exception as e:
                print(f"Warning: Failed to load request from {file_path}: {e}")


# Integration with existing policy systems
class PolicyChangeGating:
    """Integrates approval workflow with policy enforcement."""

    def __init__(self, approval_workflow: PolicyApprovalWorkflow):
        self.approval_workflow = approval_workflow
        self.pending_changes: dict[str, dict[str, Any]] = {}

    def request_policy_change(
        self,
        policy_type: str,
        policy_id: str,
        change_type: str,
        current_policy: dict[str, Any] | None,
        proposed_policy: dict[str, Any],
        justification: str,
        requester: str,
        required_approvers: list[str],
    ) -> str:
        """Request a policy change that requires approval."""
        request_id = self.approval_workflow.create_request(
            policy_type=policy_type,
            policy_id=policy_id,
            change_type=change_type,
            current_policy=current_policy,
            proposed_policy=proposed_policy,
            justification=justification,
            requester=requester,
            required_approvers=required_approvers,
        )

        # Store the proposed change for later application
        self.pending_changes[request_id] = {
            "policy_type": policy_type,
            "policy_id": policy_id,
            "change_type": change_type,
            "proposed_policy": proposed_policy,
        }

        return request_id

    def apply_approved_change(self, request_id: str, policy_system: Any) -> bool:
        """Apply an approved policy change to the target system."""
        request = self.approval_workflow.get_request(request_id)
        if not request or request.state != ApprovalState.APPROVED:
            return False

        pending_change = self.pending_changes.get(request_id)
        if not pending_change:
            return False

        try:
            # Apply the change based on policy type
            if pending_change["policy_type"] == "ingestion_policy":
                if pending_change["change_type"] == "update":
                    policy_system.set_policy(pending_change["policy_id"], pending_change["proposed_policy"])
                elif pending_change["change_type"] == "delete":
                    # Remove policy (implementation depends on policy system)
                    pass

            # Remove from pending changes
            del self.pending_changes[request_id]
            return True

        except Exception as e:
            print(f"Error applying policy change {request_id}: {e}")
            return False

    def check_policy_access(self, policy_type: str, policy_id: str, user: str) -> bool:
        """Check if a user can modify a policy (for gating)."""
        # This would integrate with RBAC/ABAC systems
        # For now, return True (allow) - in production this would check permissions
        return True
