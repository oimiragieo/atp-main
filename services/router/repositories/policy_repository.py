"""Policy repository with specialized query methods."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, or_, select

from ..models.database import Policy
from .base import BaseRepository

logger = logging.getLogger(__name__)


class PolicyRepository(BaseRepository[Policy]):
    """Repository for Policy entities with specialized query methods."""

    def __init__(self):
        super().__init__(Policy)

    async def get_by_policy_id(self, policy_id: str) -> Policy | None:
        """Get policy by policy_id (not UUID id)."""
        return await self.find_one_by(policy_id=policy_id)

    async def get_enabled_policies(self, tenant_id: str | None = None) -> list[Policy]:
        """Get all enabled policies, optionally filtered by tenant."""
        filters = {"is_enabled": True}
        if tenant_id:
            filters["tenant_id"] = tenant_id

        return await self.get_all(
            filters=filters,
            order_by="-priority",  # Higher priority first
        )

    async def get_by_priority_range(
        self, min_priority: int, max_priority: int, tenant_id: str | None = None
    ) -> list[Policy]:
        """Get policies within a priority range."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Policy)
                .where(not Policy.is_deleted)
                .where(Policy.priority >= min_priority)
                .where(Policy.priority <= max_priority)
            )

            if tenant_id:
                stmt = stmt.where(Policy.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Policy.priority))

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_policies_by_tenant(
        self, tenant_id: str, enabled_only: bool = True, page: int = 1, page_size: int = 50
    ) -> list[Policy]:
        """Get policies for a specific tenant."""
        filters = {"tenant_id": tenant_id}
        if enabled_only:
            filters["is_enabled"] = True

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-priority")

    async def search_policies(
        self, search_term: str, tenant_id: str | None = None, enabled_only: bool = True
    ) -> list[Policy]:
        """Search policies by name or description."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Policy)
                .where(
                    or_(
                        Policy.name.ilike(f"%{search_term}%"),
                        Policy.description.ilike(f"%{search_term}%"),
                        Policy.policy_id.ilike(f"%{search_term}%"),
                    )
                )
                .where(not Policy.is_deleted)
            )

            if enabled_only:
                stmt = stmt.where(Policy.is_enabled)

            if tenant_id:
                stmt = stmt.where(Policy.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Policy.priority), Policy.name)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_conflicting_policies(
        self, policy_id: str, priority: int, tenant_id: str | None = None
    ) -> list[Policy]:
        """Get policies that might conflict with the given policy."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Policy)
                .where(not Policy.is_deleted)
                .where(Policy.is_enabled)
                .where(Policy.policy_id != policy_id)
                .where(Policy.priority == priority)  # Same priority might cause conflicts
            )

            if tenant_id:
                stmt = stmt.where(Policy.tenant_id == tenant_id)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_priority(self, policy_id: str, new_priority: int) -> bool:
        """Update policy priority."""
        policy = await self.get_by_policy_id(policy_id)
        if not policy:
            return False

        updated_policy = await self.update(policy.id, priority=new_priority)
        return updated_policy is not None

    async def enable_policy(self, policy_id: str) -> bool:
        """Enable a policy."""
        policy = await self.get_by_policy_id(policy_id)
        if not policy:
            return False

        updated_policy = await self.update(policy.id, is_enabled=True)
        return updated_policy is not None

    async def disable_policy(self, policy_id: str) -> bool:
        """Disable a policy."""
        policy = await self.get_by_policy_id(policy_id)
        if not policy:
            return False

        updated_policy = await self.update(policy.id, is_enabled=False)
        return updated_policy is not None

    async def bulk_enable_policies(self, policy_ids: list[str]) -> int:
        """Bulk enable multiple policies."""
        updated_count = 0

        for policy_id in policy_ids:
            success = await self.enable_policy(policy_id)
            if success:
                updated_count += 1

        return updated_count

    async def bulk_disable_policies(self, policy_ids: list[str]) -> int:
        """Bulk disable multiple policies."""
        updated_count = 0

        for policy_id in policy_ids:
            success = await self.disable_policy(policy_id)
            if success:
                updated_count += 1

        return updated_count

    async def get_policy_statistics(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Get policy statistics."""
        async with self.db_manager.get_session() as session:
            # Base query
            base_stmt = select(func.count(Policy.id)).where(not Policy.is_deleted)

            if tenant_id:
                base_stmt = base_stmt.where(Policy.tenant_id == tenant_id)

            # Total policies
            total_result = await session.execute(base_stmt)
            total_policies = total_result.scalar() or 0

            # Enabled policies
            enabled_stmt = base_stmt.where(Policy.is_enabled)
            enabled_result = await session.execute(enabled_stmt)
            enabled_policies = enabled_result.scalar() or 0

            # Priority distribution
            priority_stmt = select(
                func.min(Policy.priority).label("min_priority"),
                func.max(Policy.priority).label("max_priority"),
                func.avg(Policy.priority).label("avg_priority"),
            ).where(not Policy.is_deleted)

            if tenant_id:
                priority_stmt = priority_stmt.where(Policy.tenant_id == tenant_id)

            priority_result = await session.execute(priority_stmt)
            priority_row = priority_result.first()

            return {
                "total_policies": total_policies,
                "enabled_policies": enabled_policies,
                "disabled_policies": total_policies - enabled_policies,
                "min_priority": priority_row.min_priority or 0,
                "max_priority": priority_row.max_priority or 0,
                "avg_priority": float(priority_row.avg_priority or 0),
            }

    async def get_recently_updated_policies(
        self, hours: int = 24, tenant_id: str | None = None, limit: int = 50
    ) -> list[Policy]:
        """Get recently updated policies."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(Policy).where(not Policy.is_deleted).where(Policy.updated_at >= cutoff_time)

            if tenant_id:
                stmt = stmt.where(Policy.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Policy.updated_at)).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def validate_policy_rules(self, policy_id: str) -> dict[str, Any]:
        """Validate policy rules structure (basic validation)."""
        policy = await self.get_by_policy_id(policy_id)
        if not policy:
            return {"valid": False, "error": "Policy not found"}

        try:
            rules = policy.rules

            # Basic structure validation
            if not isinstance(rules, dict):
                return {"valid": False, "error": "Rules must be a dictionary"}

            if "rules" not in rules:
                return {"valid": False, "error": 'Rules dictionary must contain "rules" key'}

            if not isinstance(rules["rules"], list):
                return {"valid": False, "error": "Rules must be a list"}

            # Validate each rule
            for i, rule in enumerate(rules["rules"]):
                if not isinstance(rule, dict):
                    return {"valid": False, "error": f"Rule {i} must be a dictionary"}

                required_fields = ["rule_id", "effect", "conditions"]
                for field in required_fields:
                    if field not in rule:
                        return {"valid": False, "error": f"Rule {i} missing required field: {field}"}

            return {"valid": True, "rule_count": len(rules["rules"])}

        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}

    async def duplicate_policy(
        self, source_policy_id: str, new_policy_id: str, new_name: str, tenant_id: str | None = None
    ) -> Policy | None:
        """Duplicate an existing policy with a new ID and name."""
        source_policy = await self.get_by_policy_id(source_policy_id)
        if not source_policy:
            return None

        # Check if new policy ID already exists
        existing_policy = await self.get_by_policy_id(new_policy_id)
        if existing_policy:
            return None

        # Create new policy with copied data
        new_policy_data = {
            "policy_id": new_policy_id,
            "name": new_name,
            "description": f"Copy of {source_policy.description}",
            "priority": source_policy.priority,
            "is_enabled": False,  # Start disabled for safety
            "rules": source_policy.rules,
            "policy_metadata": source_policy.policy_metadata,
            "tenant_id": tenant_id or source_policy.tenant_id,
        }

        return await self.create(**new_policy_data)
