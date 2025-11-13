"""Permission system for tool use security.

Implements fine-grained access control:
- Tool allowlists/denylists
- Permission modes (accept/bypass/deny)
- User-based restrictions
- Audit logging
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PermissionMode(str, Enum):
    """Permission enforcement modes."""

    ACCEPT_EDITS = "acceptEdits"  # Auto-approve all tool uses
    BYPASS_PERMISSIONS = "bypassPermissions"  # Skip permission checks
    REQUIRE_APPROVAL = "requireApproval"  # Require explicit approval
    DENY_ALL = "denyAll"  # Deny all tool uses


@dataclass
class PermissionPolicy:
    """Permission policy for tool access."""

    mode: PermissionMode = PermissionMode.REQUIRE_APPROVAL
    allowed_tools: list[str] | None = None  # None = all allowed
    disallowed_tools: list[str] | None = None  # Explicit deny list
    allowed_users: list[str] | None = None  # None = all users
    max_concurrent_tools: int = 10
    require_audit: bool = True


class PermissionManager:
    """Manages tool use permissions."""

    def __init__(self, default_policy: PermissionPolicy | None = None):
        """Initialize permission manager.

        Args:
            default_policy: Default policy for all requests
        """
        self.default_policy = default_policy or PermissionPolicy()
        self._user_policies: dict[str, PermissionPolicy] = {}
        self._audit_log: list[dict[str, Any]] = []

    def set_user_policy(self, user_id: str, policy: PermissionPolicy) -> None:
        """Set permission policy for a user.

        Args:
            user_id: User identifier
            policy: Permission policy
        """
        self._user_policies[user_id] = policy
        logger.info(f"Set policy for user {user_id}: {policy.mode}")

    def get_policy(self, user_id: str | None = None) -> PermissionPolicy:
        """Get permission policy for a user.

        Args:
            user_id: User identifier

        Returns:
            Permission policy
        """
        if user_id and user_id in self._user_policies:
            return self._user_policies[user_id]
        return self.default_policy

    def can_use_tool(
        self, tool_name: str, user_id: str | None = None, context: dict[str, Any] | None = None
    ) -> tuple[bool, str | None]:
        """Check if tool use is permitted.

        Args:
            tool_name: Tool to check
            user_id: User requesting tool use
            context: Additional context

        Returns:
            (allowed, reason)
        """
        policy = self.get_policy(user_id)

        # Check mode
        if policy.mode == PermissionMode.DENY_ALL:
            reason = "All tool use denied by policy"
            self._audit(tool_name, user_id, False, reason, context)
            return False, reason

        if policy.mode == PermissionMode.BYPASS_PERMISSIONS:
            self._audit(tool_name, user_id, True, "Bypass mode", context)
            return True, None

        # Check user allowlist
        if policy.allowed_users and user_id not in policy.allowed_users:
            reason = f"User {user_id} not in allowed users list"
            self._audit(tool_name, user_id, False, reason, context)
            return False, reason

        # Check tool denylist
        if policy.disallowed_tools and tool_name in policy.disallowed_tools:
            reason = f"Tool {tool_name} is explicitly disallowed"
            self._audit(tool_name, user_id, False, reason, context)
            return False, reason

        # Check tool allowlist
        if policy.allowed_tools and tool_name not in policy.allowed_tools:
            reason = f"Tool {tool_name} not in allowed tools list"
            self._audit(tool_name, user_id, False, reason, context)
            return False, reason

        # Permitted
        if policy.mode == PermissionMode.ACCEPT_EDITS:
            self._audit(tool_name, user_id, True, "Auto-approved", context)
            return True, None

        # Require approval (return True but log for audit)
        self._audit(tool_name, user_id, True, "Approval required", context)
        return True, "Approval required"

    def _audit(
        self,
        tool_name: str,
        user_id: str | None,
        allowed: bool,
        reason: str,
        context: dict[str, Any] | None,
    ) -> None:
        """Audit tool use attempt.

        Args:
            tool_name: Tool name
            user_id: User ID
            allowed: Whether access was allowed
            reason: Reason for decision
            context: Additional context
        """
        import time

        entry = {
            "timestamp": time.time(),
            "tool_name": tool_name,
            "user_id": user_id,
            "allowed": allowed,
            "reason": reason,
            "context": context or {},
        }

        self._audit_log.append(entry)

        if not allowed:
            logger.warning(f"Tool access denied: {tool_name} for user {user_id} - {reason}")
        else:
            logger.info(f"Tool access granted: {tool_name} for user {user_id} - {reason}")

    def get_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent audit log entries.

        Args:
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        return self._audit_log[-limit:]


# Global permission manager
_global_manager = PermissionManager()


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager."""
    return _global_manager
