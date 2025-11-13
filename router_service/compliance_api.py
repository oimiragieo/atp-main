"""Compliance Management API Endpoints.

REST API endpoints for compliance reporting, violation management,
and automated compliance validation.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .compliance_validator import (
    ComplianceFramework,
    ViolationSeverity,
    get_compliance_validator,
)
from .enterprise_auth import UserInfo, require_admin, require_authentication

logger = logging.getLogger(__name__)

# Create router
compliance_router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


# Pydantic models for API
class ComplianceViolationModel(BaseModel):
    """API model for compliance violation."""

    violation_id: str
    rule_id: str
    framework: ComplianceFramework
    severity: ViolationSeverity
    title: str
    description: str
    detected_at: datetime
    resource_id: str | None = None
    tenant_id: str | None = None
    remediation_steps: list[str]
    status: str
    remediated_at: datetime | None = None


class ComplianceReportModel(BaseModel):
    """API model for compliance report."""

    report_id: str
    framework: ComplianceFramework
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    total_rules_checked: int
    violations: list[ComplianceViolationModel]
    compliance_score: float
    summary: dict


class RemediationRequest(BaseModel):
    """Request model for violation remediation."""

    remediation_notes: str = Field("", description="Notes about the remediation")


@compliance_router.post("/check", response_model=ComplianceReportModel)
async def run_compliance_check(
    framework: ComplianceFramework | None = Query(None, description="Specific framework to check"),
    user: UserInfo = Depends(require_admin()),
) -> ComplianceReportModel:
    """Run compliance check for specified framework or all frameworks."""
    validator = get_compliance_validator()

    try:
        report = await validator.run_compliance_check(framework)

        # Convert to API model
        violations = [
            ComplianceViolationModel(
                violation_id=v.violation_id,
                rule_id=v.rule_id,
                framework=v.framework,
                severity=v.severity,
                title=v.title,
                description=v.description,
                detected_at=v.detected_at,
                resource_id=v.resource_id,
                tenant_id=v.tenant_id,
                remediation_steps=v.remediation_steps,
                status=v.status,
                remediated_at=v.remediated_at,
            )
            for v in report.violations
        ]

        return ComplianceReportModel(
            report_id=report.report_id,
            framework=report.framework,
            generated_at=report.generated_at,
            period_start=report.period_start,
            period_end=report.period_end,
            total_rules_checked=report.total_rules_checked,
            violations=violations,
            compliance_score=report.compliance_score,
            summary=report.summary,
        )

    except Exception as e:
        logger.error(f"Failed to run compliance check: {e}")
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {str(e)}")


@compliance_router.get("/violations", response_model=list[ComplianceViolationModel])
async def get_violations(
    framework: ComplianceFramework | None = Query(None, description="Filter by framework"),
    severity: ViolationSeverity | None = Query(None, description="Filter by severity"),
    status: str | None = Query(None, description="Filter by status (open, remediated, false_positive)"),
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"})),
) -> list[ComplianceViolationModel]:
    """Get current compliance violations with optional filtering."""
    validator = get_compliance_validator()

    violations = validator.get_violations(framework)

    # Apply filters
    if severity:
        violations = [v for v in violations if v.severity == severity]

    if status:
        violations = [v for v in violations if v.status == status]

    # Convert to API models
    return [
        ComplianceViolationModel(
            violation_id=v.violation_id,
            rule_id=v.rule_id,
            framework=v.framework,
            severity=v.severity,
            title=v.title,
            description=v.description,
            detected_at=v.detected_at,
            resource_id=v.resource_id,
            tenant_id=v.tenant_id,
            remediation_steps=v.remediation_steps,
            status=v.status,
            remediated_at=v.remediated_at,
        )
        for v in violations
    ]


@compliance_router.get("/violations/{violation_id}", response_model=ComplianceViolationModel)
async def get_violation(
    violation_id: str, user: UserInfo = Depends(require_authentication({"read", "write", "admin"}))
) -> ComplianceViolationModel:
    """Get a specific compliance violation."""
    validator = get_compliance_validator()

    violations = validator.get_violations()
    violation = next((v for v in violations if v.violation_id == violation_id), None)

    if not violation:
        raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found")

    return ComplianceViolationModel(
        violation_id=violation.violation_id,
        rule_id=violation.rule_id,
        framework=violation.framework,
        severity=violation.severity,
        title=violation.title,
        description=violation.description,
        detected_at=violation.detected_at,
        resource_id=violation.resource_id,
        tenant_id=violation.tenant_id,
        remediation_steps=violation.remediation_steps,
        status=violation.status,
        remediated_at=violation.remediated_at,
    )


@compliance_router.post("/violations/{violation_id}/remediate")
async def remediate_violation(
    violation_id: str, request: RemediationRequest, user: UserInfo = Depends(require_admin())
) -> dict:
    """Mark a compliance violation as remediated."""
    validator = get_compliance_validator()

    success = validator.remediate_violation(violation_id, request.remediation_notes)

    if not success:
        raise HTTPException(status_code=404, detail=f"Violation {violation_id} not found")

    logger.info(f"Violation {violation_id} remediated by user {user.user_id}")

    return {
        "message": f"Violation {violation_id} marked as remediated",
        "remediated_by": user.user_id,
        "remediated_at": datetime.utcnow().isoformat(),
    }


@compliance_router.get("/frameworks", response_model=list[str])
async def get_supported_frameworks(
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"})),
) -> list[str]:
    """Get list of supported compliance frameworks."""
    return [framework.value for framework in ComplianceFramework]


@compliance_router.get("/dashboard")
async def get_compliance_dashboard(
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"})),
) -> dict:
    """Get compliance dashboard data."""
    validator = get_compliance_validator()

    # Get violations by framework
    violations_by_framework = {}
    for framework in ComplianceFramework:
        violations = validator.get_violations(framework)
        violations_by_framework[framework.value] = {
            "total": len(violations),
            "open": len([v for v in violations if v.status == "open"]),
            "critical": len([v for v in violations if v.severity == ViolationSeverity.CRITICAL]),
            "high": len([v for v in violations if v.severity == ViolationSeverity.HIGH]),
        }

    # Calculate overall compliance score
    all_violations = validator.get_violations()
    total_rules = len(validator.rules)
    open_violations = len([v for v in all_violations if v.status == "open"])
    overall_score = max(0.0, (total_rules - open_violations) / total_rules) if total_rules > 0 else 1.0

    return {
        "overall_compliance_score": overall_score,
        "total_rules": total_rules,
        "total_violations": len(all_violations),
        "open_violations": open_violations,
        "violations_by_framework": violations_by_framework,
        "recent_violations": [
            {
                "violation_id": v.violation_id,
                "framework": v.framework.value,
                "severity": v.severity.value,
                "title": v.title,
                "detected_at": v.detected_at.isoformat(),
            }
            for v in sorted(all_violations, key=lambda x: x.detected_at, reverse=True)[:10]
        ],
    }


@compliance_router.get("/export/{framework}")
async def export_compliance_report(
    framework: ComplianceFramework,
    format: str = Query("json", description="Export format (json, csv)"),
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"})),
) -> dict:
    """Export compliance report in specified format."""
    validator = get_compliance_validator()

    try:
        report = await validator.run_compliance_check(framework)

        if format.lower() == "json":
            return {
                "format": "json",
                "report": {
                    "report_id": report.report_id,
                    "framework": report.framework.value,
                    "generated_at": report.generated_at.isoformat(),
                    "compliance_score": report.compliance_score,
                    "violations": [
                        {
                            "violation_id": v.violation_id,
                            "rule_id": v.rule_id,
                            "severity": v.severity.value,
                            "title": v.title,
                            "description": v.description,
                            "detected_at": v.detected_at.isoformat(),
                            "status": v.status,
                        }
                        for v in report.violations
                    ],
                },
            }
        elif format.lower() == "csv":
            # Generate CSV data
            csv_lines = ["violation_id,rule_id,severity,title,status,detected_at"]
            for v in report.violations:
                csv_lines.append(
                    f"{v.violation_id},{v.rule_id},{v.severity.value},"
                    f'"{v.title}",{v.status},{v.detected_at.isoformat()}'
                )

            return {"format": "csv", "data": "\n".join(csv_lines)}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    except Exception as e:
        logger.error(f"Failed to export compliance report: {e}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
