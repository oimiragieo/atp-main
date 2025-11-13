"""Tests for GAP-109E: Revocation (CRL/OCSP-like) support"""

import time
import unittest
from unittest.mock import patch

from router_service.arpki_validator import (
    CertificateRevocationList,
    RevocationChecker,
    RevocationStatus,
)


class TestCertificateRevocationList(unittest.TestCase):
    """Test Certificate Revocation List functionality."""

    def test_crl_expiration(self):
        """Test CRL expiration checking."""
        now = time.time()
        future = now + 3600

        # Valid CRL
        valid_crl = CertificateRevocationList(
            issuer="CN=ARPKI CA",
            serial_numbers=set(),
            this_update=now - 60,
            next_update=future,
            url="http://example.com/crl.pem",
        )
        self.assertFalse(valid_crl.is_expired())

        # Expired CRL
        expired_crl = CertificateRevocationList(
            issuer="CN=ARPKI CA",
            serial_numbers=set(),
            this_update=now - 7200,
            next_update=now - 60,
            url="http://example.com/crl.pem",
        )
        self.assertTrue(expired_crl.is_expired())

    def test_crl_revocation_check(self):
        """Test CRL revocation status checking."""
        crl = CertificateRevocationList(
            issuer="CN=ARPKI CA",
            serial_numbers={"123456789", "987654321"},
            this_update=time.time() - 60,
            next_update=time.time() + 3600,
            url="http://example.com/crl.pem",
        )

        # Revoked certificate
        self.assertTrue(crl.is_revoked("123456789"))
        self.assertTrue(crl.is_revoked("987654321"))

        # Valid certificate
        self.assertFalse(crl.is_revoked("111111111"))
        self.assertFalse(crl.is_revoked("222222222"))


class TestRevocationChecker(unittest.TestCase):
    """Test Revocation Checker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.checker = RevocationChecker(refresh_interval=3600.0)

    def test_certificate_revocation_check_valid(self):
        """Test revocation check for valid certificate."""
        cert_pem = (
            "-----BEGIN CERTIFICATE-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n-----END CERTIFICATE-----"
        )

        status = self.checker.check_revocation(cert_pem)

        self.assertIsInstance(status, RevocationStatus)
        self.assertFalse(status.is_revoked)
        self.assertIsNone(status.revocation_time)
        self.assertIsNone(status.revocation_reason)
        self.assertIsNotNone(status.checked_at)

    def test_certificate_revocation_check_revoked(self):
        """Test revocation check for revoked certificate."""
        # Add a CRL with revoked certificates
        crl = CertificateRevocationList(
            issuer="CN=ARPKI CA",
            serial_numbers={"abcdef1234567890"},  # This will match our hash
            this_update=time.time() - 60,
            next_update=time.time() + 3600,
            url="http://example.com/crl.pem",
        )
        self.checker._crl_cache["http://example.com/crl.pem"] = crl

        # Create a certificate that will hash to our revoked serial
        # Use the actual hash that will be generated
        import hashlib

        cert_pem = "test_cert_data"
        expected_serial = hashlib.sha256(cert_pem.encode()).hexdigest()[:16]

        # Update the CRL to have the correct serial
        crl.serial_numbers = {expected_serial}

        status = self.checker.check_revocation(cert_pem)

        self.assertIsInstance(status, RevocationStatus)
        self.assertTrue(status.is_revoked)
        self.assertIsNotNone(status.revocation_time)
        self.assertEqual(status.revocation_reason, "CRL")

    def test_crl_refresh(self):
        """Test CRL refresh functionality."""
        # Add a distribution point
        url = "http://example.com/crl.pem"
        self.checker.add_crl_distribution_point(url)

        # Verify CRL was added
        self.assertIn(url, self.checker._crl_cache)

        # Refresh CRLs
        self.checker.refresh_crls()

        # Verify CRL was refreshed
        self.assertIn(url, self.checker._crl_cache)

    def test_should_refresh_crl(self):
        """Test CRL refresh timing logic."""
        url = "http://example.com/crl.pem"

        # Initially should refresh (never refreshed)
        self.assertTrue(self.checker.should_refresh_crl(url))

        # Set last refresh to now
        self.checker._last_refresh[url] = time.time()

        # Should not refresh immediately
        self.assertFalse(self.checker.should_refresh_crl(url))

        # Set last refresh to past refresh interval
        self.checker._last_refresh[url] = time.time() - 3700  # > 3600

        # Should refresh now
        self.assertTrue(self.checker.should_refresh_crl(url))

    def test_add_crl_distribution_point(self):
        """Test adding CRL distribution points."""
        url = "http://example.com/crl.pem"

        # Initially empty
        self.assertNotIn(url, self.checker._crl_cache)

        # Add distribution point
        self.checker.add_crl_distribution_point(url)

        # Should be added
        self.assertIn(url, self.checker._crl_cache)
        self.assertIn(url, self.checker._last_refresh)

    def test_revocation_check_error_handling(self):
        """Test error handling in revocation checking."""
        # Test with None input to cause an exception
        status = self.checker.check_revocation(None)  # type: ignore

        # Should handle error gracefully (fail-open)
        self.assertIsInstance(status, RevocationStatus)
        self.assertFalse(status.is_revoked)
        self.assertEqual(status.revocation_reason, "check_failed")

    @patch("router_service.arpki_validator._HIST_CRL_REFRESH_SECONDS")
    def test_crl_refresh_metrics(self, mock_histogram):
        """Test that CRL refresh metrics are recorded."""
        # Add a distribution point
        self.checker.add_crl_distribution_point("http://example.com/crl.pem")

        # Refresh CRLs
        self.checker.refresh_crls()

        # Verify metrics were recorded
        mock_histogram.observe.assert_called_once()


class TestRevocationStatus(unittest.TestCase):
    """Test RevocationStatus dataclass."""

    def test_revocation_status_creation(self):
        """Test RevocationStatus object creation."""
        now = time.time()

        status = RevocationStatus(
            serial_number="123456789",
            is_revoked=True,
            revocation_time=now - 3600,
            revocation_reason="CRL",
            checked_at=now,
        )

        self.assertEqual(status.serial_number, "123456789")
        self.assertTrue(status.is_revoked)
        self.assertEqual(status.revocation_time, now - 3600)
        self.assertEqual(status.revocation_reason, "CRL")
        self.assertEqual(status.checked_at, now)


if __name__ == "__main__":
    unittest.main()
