#!/usr/bin/env python3
"""Automated security testing script for ATP Platform.

Runs a subset of tests from SECURITY_TESTING_CHECKLIST.md that can be automated.
For complete security testing, manual review with tools like OWASP ZAP is recommended.

Usage:
    python3 scripts/security_tests.py [--verbose] [--auth-key KEY]

Requirements:
    - ATP services running (docker compose up)
    - requests library (pip install requests)
"""

import argparse
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)


class SecurityTester:
    """Automated security testing for ATP platform."""

    def __init__(self, base_url: str = "http://localhost:7443", api_key: str | None = None, verbose: bool = False):
        self.base_url = base_url
        self.api_key = api_key
        self.verbose = verbose
        self.results: list[dict[str, Any]] = []

    def log(self, message: str) -> None:
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"  {message}")

    def test_result(self, test_name: str, passed: bool, details: str = "") -> None:
        """Record test result."""
        result = {"test": test_name, "passed": passed, "details": details}
        self.results.append(result)

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if details and not passed:
            print(f"      {details}")

    def test_public_endpoint_access(self) -> None:
        """Test A01: Public endpoints accessible without auth."""
        print("\n[A01] Testing Public Endpoint Access...")

        # Test /healthz
        try:
            response = requests.get(f"{self.base_url}/healthz", timeout=5)
            self.test_result(
                "Public /healthz accessible", response.status_code == 200, f"Status: {response.status_code}"
            )
        except Exception as e:
            self.test_result("Public /healthz accessible", False, str(e))

        # Test /metrics
        try:
            response = requests.get(f"{self.base_url}/metrics", timeout=5)
            self.test_result(
                "Public /metrics accessible",
                response.status_code in [200, 404],  # 404 is ok, means not implemented yet
                f"Status: {response.status_code}",
            )
        except Exception as e:
            self.test_result("Public /metrics accessible", False, str(e))

    def test_protected_endpoint_requires_auth(self) -> None:
        """Test A01: Protected endpoints require authentication."""
        print("\n[A01] Testing Protected Endpoint Authentication...")

        # Test without API key
        try:
            response = requests.post(f"{self.base_url}/v1/ask", json={"prompt": "test"}, timeout=5)
            self.test_result(
                "Protected endpoint blocks unauthenticated requests",
                response.status_code == 401,
                f"Expected 401, got {response.status_code}",
            )
        except Exception as e:
            self.test_result("Protected endpoint blocks unauthenticated requests", False, str(e))

        # Test with invalid API key
        try:
            response = requests.post(
                f"{self.base_url}/v1/ask", json={"prompt": "test"}, headers={"X-API-Key": "invalid-key"}, timeout=5
            )
            self.test_result(
                "Protected endpoint rejects invalid API key",
                response.status_code == 401,
                f"Expected 401, got {response.status_code}",
            )
        except Exception as e:
            self.test_result("Protected endpoint rejects invalid API key", False, str(e))

    def test_input_validation(self) -> None:
        """Test A03: Input validation."""
        print("\n[A03] Testing Input Validation...")

        if not self.api_key:
            self.test_result("Input validation tests", False, "API key required for these tests")
            return

        # Test oversized prompt
        try:
            oversized = "a" * 150000  # Exceeds 100,000 char limit
            response = requests.post(
                f"{self.base_url}/v1/ask",
                json={"prompt": oversized, "quality": "fast"},
                headers={"X-API-Key": self.api_key},
                timeout=5,
            )
            self.test_result(
                "Rejects oversized prompt (>100k chars)",
                response.status_code == 422,
                f"Expected 422, got {response.status_code}",
            )
        except Exception as e:
            self.test_result("Rejects oversized prompt (>100k chars)", False, str(e))

        # Test invalid quality parameter
        try:
            response = requests.post(
                f"{self.base_url}/v1/ask",
                json={"prompt": "test", "quality": "super-fast"},
                headers={"X-API-Key": self.api_key},
                timeout=5,
            )
            self.test_result(
                "Rejects invalid quality parameter",
                response.status_code == 422,
                f"Expected 422, got {response.status_code}",
            )
        except Exception as e:
            self.test_result("Rejects invalid quality parameter", False, str(e))

        # Test negative max_cost_usd
        try:
            response = requests.post(
                f"{self.base_url}/v1/ask",
                json={"prompt": "test", "max_cost_usd": -1.0},
                headers={"X-API-Key": self.api_key},
                timeout=5,
            )
            self.test_result(
                "Rejects negative cost limit", response.status_code == 422, f"Expected 422, got {response.status_code}"
            )
        except Exception as e:
            self.test_result("Rejects negative cost limit", False, str(e))

    def test_cors_configuration(self) -> None:
        """Test A05: CORS misconfiguration."""
        print("\n[A05] Testing CORS Configuration...")

        # Test PUT method (should be blocked)
        try:
            response = requests.put(
                f"{self.base_url}/v1/ask",
                json={"prompt": "test"},
                headers={"X-API-Key": self.api_key} if self.api_key else {},
                timeout=5,
            )
            self.test_result(
                "CORS blocks PUT method", response.status_code == 405, f"Expected 405, got {response.status_code}"
            )
        except Exception as e:
            self.test_result("CORS blocks PUT method", False, str(e))

        # Test DELETE method (should be blocked)
        try:
            response = requests.delete(
                f"{self.base_url}/v1/ask", headers={"X-API-Key": self.api_key} if self.api_key else {}, timeout=5
            )
            self.test_result(
                "CORS blocks DELETE method", response.status_code == 405, f"Expected 405, got {response.status_code}"
            )
        except Exception as e:
            self.test_result("CORS blocks DELETE method", False, str(e))

    def test_bash_tool_security(self) -> None:
        """Test ATP-specific: Bash tool security."""
        print("\n[ATP] Testing Bash Tool Security...")

        # Bash tool should be disabled by default
        try:
            response = requests.post(
                f"{self.base_url}/tools/bash",
                json={"command": "echo test"},
                headers={"X-API-Key": self.api_key} if self.api_key else {},
                timeout=5,
            )
            # Could be 401 (no auth), 404 (not implemented), or error message
            is_disabled = response.status_code in [401, 404] or "disabled" in response.text.lower()
            self.test_result(
                "Bash tool disabled by default",
                is_disabled,
                f"Status: {response.status_code}, Response: {response.text[:100]}",
            )
        except Exception as e:
            self.test_result("Bash tool disabled by default", False, str(e))

    def test_api_key_dos_prevention(self) -> None:
        """Test A02: DoS prevention via oversized API key."""
        print("\n[A02] Testing DoS Prevention...")

        # Test oversized API key
        try:
            oversized_key = "a" * 1000  # Exceeds 512 char limit
            response = requests.post(
                f"{self.base_url}/v1/ask", json={"prompt": "test"}, headers={"X-API-Key": oversized_key}, timeout=5
            )
            self.test_result(
                "Rejects oversized API key (>512 chars)",
                response.status_code == 401,
                f"Expected 401, got {response.status_code}",
            )
        except Exception as e:
            self.test_result("Rejects oversized API key (>512 chars)", False, str(e))

    def test_sql_injection_protection(self) -> None:
        """Test A03: SQL injection protection."""
        print("\n[A03] Testing SQL Injection Protection...")

        if not self.api_key:
            self.test_result("SQL injection tests", False, "API key required")
            return

        # Test SQL injection in prompt
        try:
            sql_payload = "test' OR '1'='1"
            response = requests.post(
                f"{self.base_url}/v1/ask", json={"prompt": sql_payload}, headers={"X-API-Key": self.api_key}, timeout=5
            )
            # Should not crash (500), should process or validate (200/422)
            self.test_result(
                "Handles SQL injection in prompt safely",
                response.status_code in [200, 422],
                f"Status: {response.status_code}",
            )
        except Exception as e:
            self.test_result("Handles SQL injection in prompt safely", False, str(e))

    def print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)
        print("SECURITY TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        total = len(self.results)

        print(f"Total tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success rate: {(passed / total * 100):.1f}%")

        if failed > 0:
            print("\nFailed tests:")
            for result in self.results:
                if not result["passed"]:
                    print(f"  - {result['test']}")
                    if result["details"]:
                        print(f"    {result['details']}")

        print("\n" + "=" * 60)
        print("NOTE: This is a subset of SECURITY_TESTING_CHECKLIST.md")
        print("For complete security testing, use:")
        print("  - OWASP ZAP for web application scanning")
        print("  - Manual testing with Burp Suite")
        print("  - Full checklist review")
        print("=" * 60)

    def run_all_tests(self) -> bool:
        """Run all automated security tests."""
        print("ATP Platform - Automated Security Tests")
        print("=" * 60)
        print(f"Target: {self.base_url}")
        print(f"Auth: {'Enabled' if self.api_key else 'Disabled (limited tests)'}")
        print("=" * 60)

        self.test_public_endpoint_access()
        self.test_protected_endpoint_requires_auth()
        self.test_input_validation()
        self.test_cors_configuration()
        self.test_bash_tool_security()
        self.test_api_key_dos_prevention()
        self.test_sql_injection_protection()

        self.print_summary()

        # Return True if all tests passed
        return all(r["passed"] for r in self.results)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Automated security testing for ATP Platform")
    parser.add_argument(
        "--base-url", default="http://localhost:7443", help="Base URL of ATP service (default: http://localhost:7443)"
    )
    parser.add_argument("--auth-key", help="API key for authenticated tests (optional)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    tester = SecurityTester(base_url=args.base_url, api_key=args.auth_key, verbose=args.verbose)

    all_passed = tester.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
