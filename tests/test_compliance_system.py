"""Tests for compliance validation system."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from router_service.compliance_validator import (
    ComplianceFramework,
    ComplianceRule,
    ComplianceValidator,
    ComplianceViolation,
    ViolationSeverity,
    get_compliance_validator,
)


class TestComplianceRule:
    """Test compliance rule functionality."""

    def test_rule_creation(self):
        rule = ComplianceRule(
            rule_id="test_rule",
            framework=ComplianceFramework.GDPR,
            title="Test Rule",
            description="Test compliance rule",
            severity=ViolationSeverity.HIGH,
            check_function="test_check",
            remediation_steps=["Step 1", "Step 2"],
        )

        assert rule.rule_id == "test_rule"
        assert rule.framework == ComplianceFramework.GDPR
        assert rule.severity == ViolationSeverity.HIGH
        assert rule.enabled is True
        assert len(rule.remediation_steps) == 2


class TestComplianceViolation:
    """Test compliance violation functionality."""

    def test_violation_creation(self):
        violation = ComplianceViolation(
            violation_id="test_violation",
            rule_id="test_rule",
            framework=ComplianceFramework.SOC2,
            severity=ViolationSeverity.CRITICAL,
            title="Test Violation",
            description="Test violation description",
            detected_at=datetime.utcnow(),
            resource_id="resource123",
            tenant_id="tenant456",
        )

        assert violation.violation_id == "test_violation"
        assert violation.framework == ComplianceFramework.SOC2
        assert violation.severity == ViolationSeverity.CRITICAL
        assert violation.status == "open"
        assert violation.remediated_at is None


@pytest.mark.asyncio
class TestComplianceValidator:
    """Test compliance validator functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.validator = ComplianceValidator()

    async def test_validator_initialization(self):
        """Test validator initializes with default rules."""
        assert len(self.validator.rules) > 0

        # Check for GDPR rules
        gdpr_rules = [rule for rule in self.validator.rules.values() if rule.framework == ComplianceFramework.GDPR]
        assert len(gdpr_rules) > 0

        # Check for SOC2 rules
        soc2_rules = [rule for rule in self.validator.rules.values() if rule.framework == ComplianceFramework.SOC2]
        assert len(soc2_rules) > 0

    @patch("httpx.AsyncClient.get")
    async def test_data_retention_check_violation(self, mock_get):
        """Test data retention check that finds violations."""
        # Mock response with old data
        old_timestamp = (datetime.utcnow() - timedelta(days=800)).isoformat()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "events": [
                {"timestamp": old_timestamp, "event_type": "data_collection"},
                {"timestamp": datetime.utcnow().isoformat(), "event_type": "data_collection"},
            ]
        }
        mock_get.return_value = mock_response

        rule = self.validator.rules["gdpr_data_retention"]
        violation_data = await self.validator.check_data_retention(rule)

        assert violation_data is not None
        assert "old_events_count" in violation_data["metadata"]
        assert violation_data["metadata"]["old_events_count"] == 1

    @patch("httpx.AsyncClient.get")
    async def test_data_retention_check_no_violation(self, mock_get):
        """Test data retention check with no violations."""
        # Mock response with only recent data
        recent_timestamp = datetime.utcnow().isoformat()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"events": [{"timestamp": recent_timestamp, "event_type": "data_collection"}]}
        mock_get.return_value = mock_response

        rule = self.validator.rules["gdpr_data_retention"]
        violation_data = await self.validator.check_data_retention(rule)

        assert violation_data is None

    async def test_consent_tracking_check(self):
        """Test consent tracking check (placeholder implementation)."""
        rule = self.validator.rules["gdpr_consent_tracking"]
        violation_data = await self.validator.check_consent_tracking(rule)

        # Current implementation returns a violation (not implemented)
        assert violation_data is not None
        assert "consent tracking" in violation_data["description"].lower()

    @patch("httpx.AsyncClient.get")
    async def test_data_subject_rights_check_available(self, mock_get):
        """Test data subject rights check when endpoints are available."""
        mock_response = Mock()
        mock_response.status_code = 404  # Endpoint exists but resource not found
        mock_get.return_value = mock_response

        rule = self.validator.rules["gdpr_data_subject_rights"]
        violation_data = await self.validator.check_data_subject_rights(rule)

        assert violation_data is None  # 404 is acceptable

    @patch("httpx.AsyncClient.get")
    async def test_data_subject_rights_check_unavailable(self, mock_get):
        """Test data subject rights check when endpoints are unavailable."""
        mock_response = Mock()
        mock_response.status_code = 500  # Server error
        mock_get.return_value = mock_response

        rule = self.validator.rules["gdpr_data_subject_rights"]
        violation_data = await self.validator.check_data_subject_rights(rule)

        assert violation_data is not None
        assert "not accessible" in violation_data["description"]

    async def test_access_control_check_no_policies(self):
        """Test access control check with no policies configured."""
        # Clear policies from engine
        from router_service.policy_engine import get_policy_engine

        engine = get_policy_engine()
        original_policies = engine.abac_policies.copy()
        engine.abac_policies.clear()

        try:
            rule = self.validator.rules["soc2_access_control"]
            violation_data = await self.validator.check_access_control(rule)

            assert violation_data is not None
            assert "No access control policies" in violation_data["description"]
        finally:
            # Restore original policies
            engine.abac_policies = original_policies

    async def test_access_control_check_with_policies(self):
        """Test access control check with policies configured."""
        from router_service.policy_engine import ABACPolicy, get_policy_engine

        engine = get_policy_engine()

        # Add a test admin policy
        admin_policy = ABACPolicy(
            policy_id="test_admin_policy", name="Test Admin Policy", description="Test admin access control", rules=[]
        )
        engine.add_abac_policy(admin_policy)

        try:
            rule = self.validator.rules["soc2_access_control"]
            violation_data = await self.validator.check_access_control(rule)

            assert violation_data is None  # Should pass with admin policy
        finally:
            # Clean up
            engine.remove_abac_policy("test_admin_policy")

    @patch("httpx.AsyncClient.get")
    async def test_audit_logging_check_valid(self, mock_get):
        """Test audit logging check with valid integrity."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"integrity_valid": True}
        mock_get.return_value = mock_response

        rule = self.validator.rules["soc2_audit_logging"]
        violation_data = await self.validator.check_audit_logging(rule)

        assert violation_data is None

    @patch("httpx.AsyncClient.get")
    async def test_audit_logging_check_invalid(self, mock_get):
        """Test audit logging check with invalid integrity."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"integrity_valid": False}
        mock_get.return_value = mock_response

        rule = self.validator.rules["soc2_audit_logging"]
        violation_data = await self.validator.check_audit_logging(rule)

        assert violation_data is not None
        assert "integrity validation failed" in violation_data["description"]

    @patch.dict("os.environ", {"FORCE_HTTPS": "false", "DB_ENCRYPTION_ENABLED": "false"})
    async def test_data_encryption_check_violations(self):
        """Test data encryption check with violations."""
        rule = self.validator.rules["soc2_data_encryption"]
        violation_data = await self.validator.check_data_encryption(rule)

        assert violation_data is not None
        assert "HTTPS not enforced" in violation_data["metadata"]["issues"]
        assert "Database encryption not configured" in violation_data["metadata"]["issues"]

    @patch.dict("os.environ", {"FORCE_HTTPS": "true", "DB_ENCRYPTION_ENABLED": "true"})
    async def test_data_encryption_check_no_violations(self):
        """Test data encryption check with no violations."""
        rule = self.validator.rules["soc2_data_encryption"]
        violation_data = await self.validator.check_data_encryption(rule)

        assert violation_data is None

    @patch("router_service.compliance_validator.ComplianceValidator.check_data_retention")
    @patch("router_service.compliance_validator.ComplianceValidator.check_consent_tracking")
    async def test_run_compliance_check_gdpr(self, mock_consent, mock_retention):
        """Test running compliance check for GDPR framework."""
        # Mock check methods
        mock_retention.return_value = None  # No violation
        mock_consent.return_value = {"description": "Consent not implemented"}  # Violation

        report = await self.validator.run_compliance_check(ComplianceFramework.GDPR)

        assert report.framework == ComplianceFramework.GDPR
        assert report.total_rules_checked > 0
        assert len(report.violations) >= 1  # At least the consent violation
        assert report.compliance_score < 1.0  # Should be less than perfect due to violations
        assert "total_violations" in report.summary

    async def test_get_violations_filtering(self):
        """Test violation filtering functionality."""
        # Add test violations
        violation1 = ComplianceViolation(
            violation_id="v1",
            rule_id="rule1",
            framework=ComplianceFramework.GDPR,
            severity=ViolationSeverity.HIGH,
            title="Test Violation 1",
            description="Test",
            detected_at=datetime.utcnow(),
        )

        violation2 = ComplianceViolation(
            violation_id="v2",
            rule_id="rule2",
            framework=ComplianceFramework.SOC2,
            severity=ViolationSeverity.CRITICAL,
            title="Test Violation 2",
            description="Test",
            detected_at=datetime.utcnow(),
        )

        self.validator.violations["v1"] = violation1
        self.validator.violations["v2"] = violation2

        # Test framework filtering
        gdpr_violations = self.validator.get_violations(ComplianceFramework.GDPR)
        assert len(gdpr_violations) == 1
        assert gdpr_violations[0].framework == ComplianceFramework.GDPR

        soc2_violations = self.validator.get_violations(ComplianceFramework.SOC2)
        assert len(soc2_violations) == 1
        assert soc2_violations[0].framework == ComplianceFramework.SOC2

        # Test no filtering
        all_violations = self.validator.get_violations()
        assert len(all_violations) == 2

    def test_remediate_violation(self):
        """Test violation remediation."""
        # Add test violation
        violation = ComplianceViolation(
            violation_id="test_violation",
            rule_id="test_rule",
            framework=ComplianceFramework.GDPR,
            severity=ViolationSeverity.HIGH,
            title="Test Violation",
            description="Test",
            detected_at=datetime.utcnow(),
        )

        self.validator.violations["test_violation"] = violation

        # Test successful remediation
        success = self.validator.remediate_violation("test_violation", "Fixed by admin")
        assert success is True

        remediated_violation = self.validator.violations["test_violation"]
        assert remediated_violation.status == "remediated"
        assert remediated_violation.remediated_at is not None
        assert remediated_violation.metadata["remediation_notes"] == "Fixed by admin"

        # Test remediation of non-existent violation
        success = self.validator.remediate_violation("non_existent", "Notes")
        assert success is False


@pytest.mark.asyncio
class TestComplianceAPI:
    """Test compliance management API endpoints."""

    async def test_compliance_frameworks_enum(self):
        """Test compliance frameworks enumeration."""
        frameworks = list(ComplianceFramework)

        assert ComplianceFramework.GDPR in frameworks
        assert ComplianceFramework.SOC2 in frameworks
        assert ComplianceFramework.HIPAA in frameworks
        assert ComplianceFramework.PCI_DSS in frameworks
        assert ComplianceFramework.ISO27001 in frameworks

    def test_violation_severity_enum(self):
        """Test violation severity enumeration."""
        severities = list(ViolationSeverity)

        assert ViolationSeverity.LOW in severities
        assert ViolationSeverity.MEDIUM in severities
        assert ViolationSeverity.HIGH in severities
        assert ViolationSeverity.CRITICAL in severities


def test_global_compliance_validator():
    """Test global compliance validator singleton."""
    validator1 = get_compliance_validator()
    validator2 = get_compliance_validator()

    # Should return the same instance
    assert validator1 is validator2


@pytest.mark.asyncio
class TestComplianceIntegration:
    """Integration tests for compliance system."""

    @patch("httpx.AsyncClient.get")
    async def test_end_to_end_compliance_check(self, mock_get):
        """Test end-to-end compliance check workflow."""
        # Mock memory gateway responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"events": [], "integrity_valid": True}
        mock_get.return_value = mock_response

        validator = get_compliance_validator()

        # Run compliance check
        report = await validator.run_compliance_check(ComplianceFramework.GDPR)

        assert report is not None
        assert report.framework == ComplianceFramework.GDPR
        assert isinstance(report.compliance_score, float)
        assert 0.0 <= report.compliance_score <= 1.0
        assert isinstance(report.violations, list)
        assert "total_violations" in report.summary

    def test_compliance_metrics_integration(self):
        """Test compliance metrics are properly tracked."""
        from metrics.registry import REGISTRY

        # Check that compliance metrics exist
        assert "compliance_checks_total" in REGISTRY.counters
        assert "compliance_violations_total" in REGISTRY.counters
        assert "compliance_score" in REGISTRY.gauges
