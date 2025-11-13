"""Tests for GAP-109D: ARPKI Route Attestation Validation"""

import time
import unittest
from unittest.mock import patch

from router_service.arpki_validator import (
    ARPKIValidator,
    AttestationObject,
    RouteOriginAuthorization,
    validate_agp_route_attestation,
)


class TestRouteOriginAuthorization(unittest.TestCase):
    """Test Route Origin Authorization functionality."""

    def test_roa_validity(self):
        """Test ROA validity checking."""
        now = time.time()
        future = now + 3600

        # Valid ROA
        valid_roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=24, not_before=now - 60, not_after=future
        )
        self.assertTrue(valid_roa.is_valid())

        # Expired ROA
        expired_roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=24, not_before=now - 7200, not_after=now - 60
        )
        self.assertFalse(expired_roa.is_valid())

        # Future ROA
        future_roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=24, not_before=future, not_after=future + 3600
        )
        self.assertFalse(future_roa.is_valid())

    def test_roa_prefix_coverage(self):
        """Test ROA prefix coverage validation."""
        roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=26, not_before=time.time() - 60, not_after=time.time() + 3600
        )

        # Exact match
        self.assertTrue(roa.covers_prefix("192.0.2.0/24"))

        # More specific (allowed by max_length)
        self.assertTrue(roa.covers_prefix("192.0.2.0/25"))
        self.assertTrue(roa.covers_prefix("192.0.2.0/26"))

        # Too specific (exceeds max_length)
        self.assertFalse(roa.covers_prefix("192.0.2.0/27"))

        # Different prefix
        self.assertFalse(roa.covers_prefix("192.0.2.1/24"))
        self.assertFalse(roa.covers_prefix("192.0.3.0/24"))


class TestAttestationObject(unittest.TestCase):
    """Test Attestation Object functionality."""

    def test_attestation_validation(self):
        """Test attestation validation."""
        now = time.time()
        future = now + 3600

        # Valid attestation
        valid_roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=24, not_before=now - 60, not_after=future
        )

        valid_attestation = AttestationObject(
            roa=valid_roa, certificate_chain=["cert1", "cert2"], signature="valid_signature", signed_data="route_data"
        )

        self.assertTrue(valid_attestation.is_valid())

        # Invalid ROA
        invalid_roa = RouteOriginAuthorization(
            asn=65001, prefix="192.0.2.0/24", max_length=24, not_before=now - 7200, not_after=now - 60
        )

        invalid_attestation = AttestationObject(
            roa=invalid_roa, certificate_chain=["cert1", "cert2"], signature="valid_signature", signed_data="route_data"
        )

        self.assertFalse(invalid_attestation.is_valid())

        # Empty certificate chain
        no_cert_attestation = AttestationObject(
            roa=valid_roa, certificate_chain=[], signature="valid_signature", signed_data="route_data"
        )

        self.assertFalse(no_cert_attestation.is_valid())

        # Missing signature
        no_sig_attestation = AttestationObject(
            roa=valid_roa, certificate_chain=["cert1", "cert2"], signature="", signed_data="route_data"
        )

        self.assertFalse(no_sig_attestation.is_valid())


class TestARPKIValidator(unittest.TestCase):
    """Test ARPKI Validator functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = ARPKIValidator()

    def test_valid_route_attestation(self):
        """Test validation of a valid route attestation."""
        now = time.time()
        future = now + 3600

        attestation_data = {
            "roa": {"asn": 65001, "prefix": "192.0.2.0/24", "maxLength": 24, "notBefore": now - 60, "notAfter": future},
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertTrue(result)

    def test_invalid_asn_mismatch(self):
        """Test validation fails with ASN mismatch."""
        now = time.time()
        future = now + 3600

        attestation_data = {
            "roa": {
                "asn": 65001,  # Different ASN
                "prefix": "192.0.2.0/24",
                "maxLength": 24,
                "notBefore": now - 60,
                "notAfter": future,
            },
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation(
            "192.0.2.0/24",
            65002,
            attestation_data,  # Different ASN
        )
        self.assertFalse(result)

    def test_invalid_prefix_mismatch(self):
        """Test validation fails with prefix mismatch."""
        now = time.time()
        future = now + 3600

        attestation_data = {
            "roa": {
                "asn": 65001,
                "prefix": "192.0.2.0/24",  # Different prefix
                "maxLength": 24,
                "notBefore": now - 60,
                "notAfter": future,
            },
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation(
            "192.0.3.0/24",
            65001,
            attestation_data,  # Different prefix
        )
        self.assertFalse(result)

    def test_expired_attestation(self):
        """Test validation fails with expired attestation."""
        now = time.time()

        attestation_data = {
            "roa": {
                "asn": 65001,
                "prefix": "192.0.2.0/24",
                "maxLength": 24,
                "notBefore": now - 7200,
                "notAfter": now - 60,  # Expired
            },
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertFalse(result)

    def test_invalid_certificate_chain(self):
        """Test validation fails with invalid certificate chain."""
        now = time.time()
        future = now + 3600

        attestation_data = {
            "roa": {"asn": 65001, "prefix": "192.0.2.0/24", "maxLength": 24, "notBefore": now - 60, "notAfter": future},
            "certificateChain": [],  # Empty chain
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertFalse(result)

    def test_missing_signature(self):
        """Test validation fails with missing signature."""
        now = time.time()
        future = now + 3600

        attestation_data = {
            "roa": {"asn": 65001, "prefix": "192.0.2.0/24", "maxLength": 24, "notBefore": now - 60, "notAfter": future},
            "certificateChain": ["cert1", "cert2"],
            "signature": "",  # Missing signature
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertFalse(result)

    def test_malformed_attestation_data(self):
        """Test validation handles malformed attestation data gracefully."""
        # Missing ROA data
        attestation_data = {
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertFalse(result)

        # Invalid ROA data types
        attestation_data = {
            "roa": {
                "asn": "invalid_asn",  # Should be int
                "prefix": "192.0.2.0/24",
                "maxLength": 24,
                "notBefore": time.time() - 60,
                "notAfter": time.time() + 3600,
            },
            "certificateChain": ["cert1", "cert2"],
            "signature": "valid_signature",
            "signedData": "route_data",
        }

        result = self.validator.validate_route_attestation("192.0.2.0/24", 65001, attestation_data)
        self.assertFalse(result)


class TestGlobalValidationFunction(unittest.TestCase):
    """Test the global validation function."""

    @patch("router_service.arpki_validator._ARPKI_VALIDATOR")
    def test_global_validation_function(self, mock_validator):
        """Test the global validation function calls the validator."""
        mock_validator.validate_route_attestation.return_value = True

        result = validate_agp_route_attestation("192.0.2.0/24", 65001, {"test": "data"})

        self.assertTrue(result)
        mock_validator.validate_route_attestation.assert_called_once_with("192.0.2.0/24", 65001, {"test": "data"})


if __name__ == "__main__":
    unittest.main()
