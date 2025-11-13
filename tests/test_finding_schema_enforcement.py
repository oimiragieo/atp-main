"""Tests for GAP-136: Finding schema enforcement & agreement logic."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from router_service.finding_validator import FindingAgreementScorer, FindingValidator
from router_service.models import Evidence, Finding


def test_finding_validator_basic():
    """Test basic finding validation."""
    validator = FindingValidator()

    finding_data = {
        "id": "F-101",
        "type": "code.vuln.aud_check_missing",
        "file": "auth/jwt.py",
        "span": "45-80",
        "claim": "Missing audience check on JWT decode",
        "evidence": [{"kind": "code", "file": "auth/jwt.py", "lines": "60-72"}],
        "proposed_fix": "Add audience validation",
        "tests": ["test_jwt_aud"],
        "severity": "high",
        "confidence": 0.83,
    }

    finding = validator.validate_finding(finding_data)
    assert finding.id == "F-101"
    assert finding.type == "code.vuln.aud_check_missing"
    assert finding.severity == "high"
    assert finding.confidence == 0.83
    assert len(finding.evidence) == 1

    print("OK: Basic finding validation test passed")


def test_finding_validator_canonicalization():
    """Test type canonicalization with aliases."""
    validator = FindingValidator()

    # Test with alias
    finding_data = {
        "id": "F-102",
        "type": "missing audience check",  # This should be canonicalized
        "file": "auth/jwt.py",
        "claim": "Missing audience check",
        "severity": "high",
        "confidence": 0.8,
    }

    finding = validator.validate_finding(finding_data)
    assert finding.type == "code.vuln.aud_check_missing"  # Should be canonicalized

    print("OK: Finding canonicalization test passed")


def test_finding_validator_invalid_schema():
    """Test validation of invalid finding schema."""
    validator = FindingValidator()

    # Invalid confidence (should be 0.0-1.0)
    finding_data = {
        "id": "F-103",
        "type": "code.vuln.test",
        "claim": "Test finding",
        "severity": "high",
        "confidence": 1.5,  # Invalid
    }

    try:
        validator.validate_finding(finding_data)
        raise AssertionError("Should have raised ValidationError")
    except ValueError:
        pass  # Expected

    print("OK: Invalid schema validation test passed")


def test_finding_agreement_scorer_single():
    """Test agreement scoring with single finding."""
    scorer = FindingAgreementScorer()

    findings = [
        Finding(
            id="F-101",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.8,
        )
    ]

    agreement = scorer.compute_agreement(findings)
    assert agreement == 1.0

    print("OK: Single finding agreement test passed")


def test_finding_agreement_scorer_identical():
    """Test agreement scoring with identical findings."""
    scorer = FindingAgreementScorer()

    findings = [
        Finding(
            id="F-101",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.8,
            evidence=[Evidence(kind="code", file="auth/jwt.py", lines="60-72")],
        ),
        Finding(
            id="F-102",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.85,
            evidence=[Evidence(kind="code", file="auth/jwt.py", lines="60-72")],
        ),
    ]

    agreement = scorer.compute_agreement(findings)
    assert agreement > 0.5  # Should have good agreement

    print("OK: Identical findings agreement test passed")


def test_finding_agreement_scorer_different():
    """Test agreement scoring with different findings in same group."""
    scorer = FindingAgreementScorer()

    findings = [
        Finding(
            id="F-101",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            span="45-80",
            claim="Missing audience check",
            severity="high",
            confidence=0.8,
            tests=["test_jwt_aud"],
        ),
        Finding(
            id="F-102",
            type="code.vuln.aud_check_missing",  # Same type
            file="auth/jwt.py",  # Same file
            span="45-80",  # Same span
            claim="Missing audience check",
            severity="low",  # Different severity
            confidence=0.7,
            tests=["test_jwt"],  # Different tests
        ),
    ]

    agreement = scorer.compute_agreement(findings)
    assert agreement < 0.8  # Should have lower agreement due to field mismatches

    print("OK: Different findings agreement test passed")


def test_evidence_overlap_calculation():
    """Test evidence overlap calculation."""
    scorer = FindingAgreementScorer()

    findings = [
        Finding(
            id="F-101",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.8,
            evidence=[Evidence(kind="code", file="auth/jwt.py", lines="60-72")],
        ),
        Finding(
            id="F-102",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.85,
            evidence=[Evidence(kind="code", file="auth/jwt.py", lines="60-72")],
        ),
    ]

    overlap = scorer._compute_evidence_overlap(findings)
    assert overlap == 0.5  # Should be 0.5 (1 unique span out of 2 total)

    print("OK: Evidence overlap calculation test passed")


def test_field_match_calculation():
    """Test structured field match calculation."""
    scorer = FindingAgreementScorer()

    findings = [
        Finding(
            id="F-101",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.8,
            tests=["test_jwt_aud"],
        ),
        Finding(
            id="F-102",
            type="code.vuln.aud_check_missing",
            file="auth/jwt.py",
            claim="Missing audience check",
            severity="high",
            confidence=0.85,
            tests=["test_jwt_aud"],
        ),
    ]

    match_score = scorer._compute_field_match(findings)
    assert match_score == 1.0  # Perfect match

    print("OK: Field match calculation test passed")


def test_batch_validation():
    """Test batch validation of findings."""
    validator = FindingValidator()

    findings_data = [
        {
            "id": "F-101",
            "type": "code.vuln.aud_check_missing",
            "file": "auth/jwt.py",
            "claim": "Missing audience check",
            "severity": "high",
            "confidence": 0.8,
        },
        {
            "id": "F-102",
            "type": "code.vuln.xss",
            "file": "web/form.py",
            "claim": "XSS vulnerability",
            "severity": "medium",
            "confidence": 0.7,
        },
    ]

    validated = validator.validate_findings_batch(findings_data)
    assert len(validated) == 2
    assert validated[0].id == "F-101"
    assert validated[1].id == "F-102"

    print("OK: Batch validation test passed")


if __name__ == "__main__":
    test_finding_validator_basic()
    test_finding_validator_canonicalization()
    test_finding_validator_invalid_schema()
    test_finding_agreement_scorer_single()
    test_finding_agreement_scorer_identical()
    test_finding_agreement_scorer_different()
    test_evidence_overlap_calculation()
    test_field_match_calculation()
    test_batch_validation()
    print("All GAP-136 finding schema tests passed!")
