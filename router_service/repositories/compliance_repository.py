"""Compliance repository with specialized query methods."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select

from ..models.database import ComplianceViolation
from .base import BaseRepository

logger = logging.getLogger(__name__)


class ComplianceRepository(BaseRepository[ComplianceViolation]):
    """Repository for ComplianceViolation entities with specialized query methods."""

    def __init__(self):
        super().__init__(ComplianceViolation)

    async def get_by_violation_id(self, violation_id: str) -> ComplianceViolation | None:
        """Get violation by violation_id (not UUID id)."""
        return await self.find_one_by(violation_id=violation_id)

    async def get_by_framework(
        self,
        framework: str,
        tenant_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ComplianceViolation]:
        """Get violations by compliance framework."""
        filters = {"framework": framework}
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status:
            filters["status"] = status

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-detected_at")

    async def get_by_severity(
        self,
        severity: str,
        tenant_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ComplianceViolation]:
        """Get violations by severity level."""
        filters = {"severity": severity}
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status:
            filters["status"] = status

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-detected_at")

    async def get_open_violations(
        self, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[ComplianceViolation]:
        """Get open (unresolved) violations."""
        return await self.get_by_status("open", tenant_id, page, page_size)

    async def get_by_status(
        self, status: str, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[ComplianceViolation]:
        """Get violations by status."""
        filters = {"status": status}
        if tenant_id:
            filters["tenant_id"] = tenant_id

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-detected_at")

    async def get_critical_violations(
        self, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[ComplianceViolation]:
        """Get critical severity violations."""
        return await self.get_by_severity("critical", tenant_id, "open", page, page_size)

    async def get_recent_violations(
        self, hours: int = 24, tenant_id: str | None = None, page: int = 1, page_size: int = 100
    ) -> list[ComplianceViolation]:
        """Get recently detected violations."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(ComplianceViolation).where(ComplianceViolation.detected_at >= cutoff_time)

            if tenant_id:
                stmt = stmt.where(ComplianceViolation.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(ComplianceViolation.detected_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def remediate_violation(
        self, violation_id: str, remediation_notes: str, remediated_by: str | None = None
    ) -> bool:
        """Mark a violation as remediated."""
        violation = await self.get_by_violation_id(violation_id)
        if not violation:
            return False

        updates = {"status": "remediated", "remediated_at": datetime.utcnow(), "remediation_notes": remediation_notes}

        # Add remediated_by to metadata
        if remediated_by:
            metadata = violation.violation_metadata or {}
            metadata["remediated_by"] = remediated_by
            updates["violation_metadata"] = metadata

        updated_violation = await self.update(violation.id, **updates)
        return updated_violation is not None

    async def mark_false_positive(self, violation_id: str, notes: str, marked_by: str | None = None) -> bool:
        """Mark a violation as false positive."""
        violation = await self.get_by_violation_id(violation_id)
        if not violation:
            return False

        updates = {"status": "false_positive", "remediation_notes": notes}

        # Add marked_by to metadata
        if marked_by:
            metadata = violation.violation_metadata or {}
            metadata["marked_false_positive_by"] = marked_by
            metadata["marked_false_positive_at"] = datetime.utcnow().isoformat()
            updates["violation_metadata"] = metadata

        updated_violation = await self.update(violation.id, **updates)
        return updated_violation is not None

    async def get_violation_statistics(
        self,
        tenant_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get compliance violation statistics."""
        async with self.db_manager.get_session() as session:
            # Base query
            base_stmt = select(func.count(ComplianceViolation.id))

            if tenant_id:
                base_stmt = base_stmt.where(ComplianceViolation.tenant_id == tenant_id)

            if start_date:
                base_stmt = base_stmt.where(ComplianceViolation.detected_at >= start_date)

            if end_date:
                base_stmt = base_stmt.where(ComplianceViolation.detected_at <= end_date)

            # Total violations
            total_result = await session.execute(base_stmt)
            total_violations = total_result.scalar() or 0

            # Violations by framework
            framework_stmt = select(ComplianceViolation.framework, func.count(ComplianceViolation.id)).group_by(
                ComplianceViolation.framework
            )

            if tenant_id:
                framework_stmt = framework_stmt.where(ComplianceViolation.tenant_id == tenant_id)

            if start_date:
                framework_stmt = framework_stmt.where(ComplianceViolation.detected_at >= start_date)

            if end_date:
                framework_stmt = framework_stmt.where(ComplianceViolation.detected_at <= end_date)

            framework_result = await session.execute(framework_stmt)
            violations_by_framework = {row[0]: row[1] for row in framework_result.all()}

            # Violations by severity
            severity_stmt = select(ComplianceViolation.severity, func.count(ComplianceViolation.id)).group_by(
                ComplianceViolation.severity
            )

            if tenant_id:
                severity_stmt = severity_stmt.where(ComplianceViolation.tenant_id == tenant_id)

            if start_date:
                severity_stmt = severity_stmt.where(ComplianceViolation.detected_at >= start_date)

            if end_date:
                severity_stmt = severity_stmt.where(ComplianceViolation.detected_at <= end_date)

            severity_result = await session.execute(severity_stmt)
            violations_by_severity = {row[0]: row[1] for row in severity_result.all()}

            # Violations by status
            status_stmt = select(ComplianceViolation.status, func.count(ComplianceViolation.id)).group_by(
                ComplianceViolation.status
            )

            if tenant_id:
                status_stmt = status_stmt.where(ComplianceViolation.tenant_id == tenant_id)

            if start_date:
                status_stmt = status_stmt.where(ComplianceViolation.detected_at >= start_date)

            if end_date:
                status_stmt = status_stmt.where(ComplianceViolation.detected_at <= end_date)

            status_result = await session.execute(status_stmt)
            violations_by_status = {row[0]: row[1] for row in status_result.all()}

            # Calculate remediation rate
            remediated_count = violations_by_status.get("remediated", 0)
            remediation_rate = (remediated_count / total_violations * 100) if total_violations > 0 else 0

            return {
                "total_violations": total_violations,
                "violations_by_framework": violations_by_framework,
                "violations_by_severity": violations_by_severity,
                "violations_by_status": violations_by_status,
                "remediation_rate_percent": round(remediation_rate, 2),
                "open_violations": violations_by_status.get("open", 0),
                "critical_violations": violations_by_severity.get("critical", 0),
            }

    async def get_sla_violations(self, tenant_id: str | None = None, hours: int = 24) -> list[ComplianceViolation]:
        """Get violations that might affect SLA compliance."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            stmt = (
                select(ComplianceViolation)
                .where(ComplianceViolation.detected_at >= cutoff_time)
                .where(ComplianceViolation.severity.in_(["critical", "high"]))
                .where(ComplianceViolation.status == "open")
            )

            if tenant_id:
                stmt = stmt.where(ComplianceViolation.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(ComplianceViolation.detected_at))

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def bulk_remediate_violations(
        self, violation_ids: list[str], remediation_notes: str, remediated_by: str | None = None
    ) -> int:
        """Bulk remediate multiple violations."""
        remediated_count = 0

        for violation_id in violation_ids:
            success = await self.remediate_violation(violation_id, remediation_notes, remediated_by)
            if success:
                remediated_count += 1

        return remediated_count
