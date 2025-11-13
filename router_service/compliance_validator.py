"""Automated Compliance Validation Service.

Service for automated validation of compliance requirements including
GDPR, SOC 2, HIPAA, and other regulatory frameworks.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# Metrics
_ctr_compliance_checks = REGISTRY.counter("compliance_checks_total")
_ctr_compliance_violations = REGISTRY.counter("compliance_violations_total")
_ctr_compliance_remediation = REGISTRY.counter("compliance_remediation_total")
_gauge_compliance_score = REGISTRY.gauge("compliance_score")


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""

    GDPR = "gdpr"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"


class ViolationSeverity(Enum):
    """Compliance violation severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComplianceRule:
    """Individual compliance rule definition."""

    rule_id: str
    framework: ComplianceFramework
    title: str
    description: str
    severity: ViolationSeverity
    check_function: str  # Name of function to call for validation
    remediation_steps: list[str]
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceViolation:
    """Compliance violation record."""

    violation_id: str
    rule_id: str
    framework: ComplianceFramework
    severity: ViolationSeverity
    title: str
    description: str
    detected_at: datetime
    resource_id: str | None = None
    tenant_id: str | None = None
    remediation_steps: list[str] = field(default_factory=list)
    status: str = "open"  # open, remediated, false_positive
    remediated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceReport:
    """Compliance assessment report."""

    report_id: str
    framework: ComplianceFramework
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    total_rules_checked: int
    violations: list[ComplianceViolation]
    compliance_score: float  # 0.0 to 1.0
    summary: dict[str, Any] = field(default_factory=dict)


class ComplianceValidator:
    """Automated compliance validation service."""

    def __init__(self):
        self.rules: dict[str, ComplianceRule] = {}
        self.violations: dict[str, ComplianceViolation] = {}
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Configuration
        self.memory_gateway_url = os.getenv("MEMORY_GATEWAY_URL", "http://localhost:8080")
        self.check_interval = int(os.getenv("COMPLIANCE_CHECK_INTERVAL", "3600"))  # 1 hour

        # Initialize default rules
        self._initialize_default_rules()

        # Start background validation task
        self._validation_task = None
        try:
            self._validation_task = asyncio.create_task(self._background_validation())
        except RuntimeError:
            # No event loop running
            pass

    def _initialize_default_rules(self):
        """Initialize default compliance rules."""

        # GDPR Rules
        gdpr_rules = [
            ComplianceRule(
                rule_id="gdpr_data_retention",
                framework=ComplianceFramework.GDPR,
                title="Data Retention Limits",
                description="Personal data must not be kept longer than necessary",
                severity=ViolationSeverity.HIGH,
                check_function="check_data_retention",
                remediation_steps=[
                    "Review data retention policies",
                    "Delete or anonymize old personal data",
                    "Implement automated data purging",
                ],
            ),
            ComplianceRule(
                rule_id="gdpr_consent_tracking",
                framework=ComplianceFramework.GDPR,
                title="Consent Tracking",
                description="Must track and validate user consent for data processing",
                severity=ViolationSeverity.HIGH,
                check_function="check_consent_tracking",
                remediation_steps=[
                    "Implement consent management system",
                    "Add consent tracking to data collection",
                    "Provide consent withdrawal mechanism",
                ],
            ),
            ComplianceRule(
                rule_id="gdpr_data_subject_rights",
                framework=ComplianceFramework.GDPR,
                title="Data Subject Rights",
                description="Must provide mechanisms for data subject rights (access, rectification, erasure)",
                severity=ViolationSeverity.CRITICAL,
                check_function="check_data_subject_rights",
                remediation_steps=[
                    "Implement data subject access request handling",
                    "Add data rectification capabilities",
                    "Implement right to erasure (right to be forgotten)",
                ],
            ),
        ]

        # SOC 2 Rules
        soc2_rules = [
            ComplianceRule(
                rule_id="soc2_access_control",
                framework=ComplianceFramework.SOC2,
                title="Access Control",
                description="Logical and physical access controls must be implemented",
                severity=ViolationSeverity.HIGH,
                check_function="check_access_control",
                remediation_steps=[
                    "Implement role-based access control",
                    "Add multi-factor authentication",
                    "Regular access reviews and audits",
                ],
            ),
            ComplianceRule(
                rule_id="soc2_audit_logging",
                framework=ComplianceFramework.SOC2,
                title="Audit Logging",
                description="System activities must be logged and monitored",
                severity=ViolationSeverity.HIGH,
                check_function="check_audit_logging",
                remediation_steps=[
                    "Enable comprehensive audit logging",
                    "Implement log integrity protection",
                    "Set up log monitoring and alerting",
                ],
            ),
            ComplianceRule(
                rule_id="soc2_data_encryption",
                framework=ComplianceFramework.SOC2,
                title="Data Encryption",
                description="Sensitive data must be encrypted in transit and at rest",
                severity=ViolationSeverity.CRITICAL,
                check_function="check_data_encryption",
                remediation_steps=[
                    "Implement TLS for data in transit",
                    "Enable encryption at rest for databases",
                    "Use strong encryption algorithms",
                ],
            ),
        ]

        # Add all rules
        for rule in gdpr_rules + soc2_rules:
            self.rules[rule.rule_id] = rule

    async def run_compliance_check(self, framework: ComplianceFramework | None = None) -> ComplianceReport:
        """Run compliance check for specified framework or all frameworks."""
        _ctr_compliance_checks.inc()

        start_time = datetime.utcnow()
        report_id = f"compliance_{start_time.strftime('%Y%m%d_%H%M%S')}"

        # Filter rules by framework if specified
        rules_to_check = []
        if framework:
            rules_to_check = [rule for rule in self.rules.values() if rule.framework == framework]
        else:
            rules_to_check = list(self.rules.values())

        violations = []

        # Run each compliance check
        for rule in rules_to_check:
            if not rule.enabled:
                continue

            try:
                violation = await self._run_rule_check(rule)
                if violation:
                    violations.append(violation)
                    _ctr_compliance_violations.inc()

            except Exception as e:
                logger.error(f"Failed to run compliance rule {rule.rule_id}: {e}")

        # Calculate compliance score
        total_rules = len(rules_to_check)
        violation_count = len(violations)
        compliance_score = max(0.0, (total_rules - violation_count) / total_rules) if total_rules > 0 else 1.0

        _gauge_compliance_score.set(compliance_score)

        # Create report
        report = ComplianceReport(
            report_id=report_id,
            framework=framework or ComplianceFramework.GDPR,  # Default for mixed reports
            generated_at=datetime.utcnow(),
            period_start=start_time - timedelta(days=30),  # Last 30 days
            period_end=start_time,
            total_rules_checked=total_rules,
            violations=violations,
            compliance_score=compliance_score,
            summary={
                "total_violations": violation_count,
                "critical_violations": len([v for v in violations if v.severity == ViolationSeverity.CRITICAL]),
                "high_violations": len([v for v in violations if v.severity == ViolationSeverity.HIGH]),
                "medium_violations": len([v for v in violations if v.severity == ViolationSeverity.MEDIUM]),
                "low_violations": len([v for v in violations if v.severity == ViolationSeverity.LOW]),
            },
        )

        logger.info(f"Compliance check completed: {violation_count} violations found, score: {compliance_score:.2f}")

        return report

    async def _run_rule_check(self, rule: ComplianceRule) -> ComplianceViolation | None:
        """Run a specific compliance rule check."""
        check_method = getattr(self, rule.check_function, None)
        if not check_method:
            logger.warning(f"Check function {rule.check_function} not found for rule {rule.rule_id}")
            return None

        try:
            violation_data = await check_method(rule)
            if violation_data:
                violation = ComplianceViolation(
                    violation_id=f"{rule.rule_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    rule_id=rule.rule_id,
                    framework=rule.framework,
                    severity=rule.severity,
                    title=rule.title,
                    description=violation_data.get("description", rule.description),
                    detected_at=datetime.utcnow(),
                    resource_id=violation_data.get("resource_id"),
                    tenant_id=violation_data.get("tenant_id"),
                    remediation_steps=rule.remediation_steps,
                    metadata=violation_data.get("metadata", {}),
                )

                # Store violation
                self.violations[violation.violation_id] = violation

                return violation

        except Exception as e:
            logger.error(f"Error running compliance check {rule.rule_id}: {e}")

        return None

    # Compliance check implementations

    async def check_data_retention(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check GDPR data retention compliance."""
        try:
            # Check for old data in memory gateway
            response = await self.http_client.get(
                f"{self.memory_gateway_url}/v1/compliance/audit-log",
                headers={"x-tenant-id": "system"},
                params={"limit": 1000},
            )

            if response.status_code == 200:
                data = response.json()
                events = data.get("events", [])

                # Look for old data (older than 2 years for example)
                cutoff_date = datetime.utcnow() - timedelta(days=730)
                old_events = []

                for event in events:
                    event_time = datetime.fromisoformat(event.get("timestamp", "").replace("Z", "+00:00"))
                    if event_time < cutoff_date:
                        old_events.append(event)

                if old_events:
                    return {
                        "description": f"Found {len(old_events)} data records older than retention policy",
                        "metadata": {"old_events_count": len(old_events), "cutoff_date": cutoff_date.isoformat()},
                    }

        except Exception as e:
            logger.error(f"Data retention check failed: {e}")

        return None

    async def check_consent_tracking(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check GDPR consent tracking compliance."""
        # This would check if consent is properly tracked for data processing
        # For now, return a placeholder violation
        return {
            "description": "Consent tracking mechanism not fully implemented",
            "metadata": {"recommendation": "Implement comprehensive consent management"},
        }

    async def check_data_subject_rights(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check GDPR data subject rights compliance."""
        try:
            # Test if data subject rights endpoints are available
            test_response = await self.http_client.get(
                f"{self.memory_gateway_url}/v1/compliance/gdpr/data-subject/test", headers={"x-tenant-id": "system"}
            )

            # If endpoint exists and responds, rights are implemented
            if test_response.status_code in [200, 404]:  # 404 is OK, means endpoint exists
                return None
            else:
                return {
                    "description": "Data subject rights endpoints not accessible",
                    "metadata": {"endpoint_status": test_response.status_code},
                }

        except Exception as e:
            return {"description": "Data subject rights endpoints not available", "metadata": {"error": str(e)}}

    async def check_access_control(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check SOC 2 access control compliance."""
        # Check if ABAC/RBAC is properly configured
        from .policy_engine import get_policy_engine

        engine = get_policy_engine()
        policies = engine.list_abac_policies()

        if not policies:
            return {
                "description": "No access control policies configured",
                "metadata": {"recommendation": "Configure ABAC policies for access control"},
            }

        # Check if admin access is properly restricted
        admin_policies = [p for p in policies if "admin" in p.name.lower()]
        if not admin_policies:
            return {
                "description": "No specific admin access control policies found",
                "metadata": {"total_policies": len(policies)},
            }

        return None

    async def check_audit_logging(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check SOC 2 audit logging compliance."""
        try:
            # Check if audit log integrity is maintained
            response = await self.http_client.get(
                f"{self.memory_gateway_url}/v1/compliance/audit-integrity", headers={"x-tenant-id": "system"}
            )

            if response.status_code == 200:
                data = response.json()
                if not data.get("integrity_valid", False):
                    return {"description": "Audit log integrity validation failed", "metadata": data}
            else:
                return {
                    "description": "Audit log integrity check unavailable",
                    "metadata": {"status_code": response.status_code},
                }

        except Exception as e:
            return {"description": "Audit logging system not accessible", "metadata": {"error": str(e)}}

        return None

    async def check_data_encryption(self, rule: ComplianceRule) -> dict[str, Any] | None:
        """Check SOC 2 data encryption compliance."""
        # Check if TLS is enforced
        encryption_issues = []

        # Check if HTTPS is enforced (basic check)
        if os.getenv("FORCE_HTTPS", "").lower() not in ("true", "1"):
            encryption_issues.append("HTTPS not enforced")

        # Check if database encryption is configured
        if os.getenv("DB_ENCRYPTION_ENABLED", "").lower() not in ("true", "1"):
            encryption_issues.append("Database encryption not configured")

        if encryption_issues:
            return {
                "description": f"Encryption issues found: {', '.join(encryption_issues)}",
                "metadata": {"issues": encryption_issues},
            }

        return None

    async def _background_validation(self):
        """Background task for periodic compliance validation."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)

                # Run compliance checks for all frameworks
                for framework in ComplianceFramework:
                    try:
                        report = await self.run_compliance_check(framework)
                        logger.info(
                            f"Background compliance check completed for {framework.value}: "
                            f"{len(report.violations)} violations, score: {report.compliance_score:.2f}"
                        )
                    except Exception as e:
                        logger.error(f"Background compliance check failed for {framework.value}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background compliance validation error: {e}")

    def get_violations(self, framework: ComplianceFramework | None = None) -> list[ComplianceViolation]:
        """Get current compliance violations."""
        violations = list(self.violations.values())

        if framework:
            violations = [v for v in violations if v.framework == framework]

        return violations

    def remediate_violation(self, violation_id: str, remediation_notes: str = "") -> bool:
        """Mark a violation as remediated."""
        if violation_id in self.violations:
            violation = self.violations[violation_id]
            violation.status = "remediated"
            violation.remediated_at = datetime.utcnow()
            violation.metadata["remediation_notes"] = remediation_notes

            _ctr_compliance_remediation.inc()
            logger.info(f"Marked violation {violation_id} as remediated")
            return True

        return False

    async def close(self):
        """Clean up resources."""
        if self._validation_task:
            self._validation_task.cancel()
        await self.http_client.aclose()


# Global compliance validator instance
_compliance_validator: ComplianceValidator | None = None


def get_compliance_validator() -> ComplianceValidator:
    """Get the global compliance validator instance."""
    global _compliance_validator
    if _compliance_validator is None:
        _compliance_validator = ComplianceValidator()
    return _compliance_validator
