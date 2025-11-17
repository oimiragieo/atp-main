#!/usr/bin/env python3
"""
ATP Installation Validator

Comprehensive validation script to verify ATP platform installation.
Checks all services, dependencies, and configurations.

Usage:
    python scripts/validate_installation.py
    python scripts/validate_installation.py --quick  # Skip slow checks
    python scripts/validate_installation.py --verbose  # Detailed output
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("❌ Missing dependency: requests")
    print("Install with: pip install -r client/requirements.txt")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


class Validator:
    """ATP platform installation validator."""

    def __init__(self, verbose: bool = False):
        """Initialize validator.

        Args:
            verbose: Enable detailed output
        """
        self.verbose = verbose
        self.checks_passed = 0
        self.checks_failed = 0
        self.checks_warned = 0

    def print_header(self, text: str) -> None:
        """Print section header."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")

    def print_success(self, text: str) -> None:
        """Print success message."""
        print(f"{Colors.GREEN}✅ {text}{Colors.END}")
        self.checks_passed += 1

    def print_failure(self, text: str, details: str = "") -> None:
        """Print failure message."""
        print(f"{Colors.RED}❌ {text}{Colors.END}")
        if details and self.verbose:
            print(f"   {Colors.RED}{details}{Colors.END}")
        self.checks_failed += 1

    def print_warning(self, text: str, details: str = "") -> None:
        """Print warning message."""
        print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")
        if details and self.verbose:
            print(f"   {Colors.YELLOW}{details}{Colors.END}")
        self.checks_warned += 1

    def print_info(self, text: str) -> None:
        """Print info message."""
        if self.verbose:
            print(f"   ℹ️  {text}")

    def check_command(self, command: list[str], name: str) -> bool:
        """Check if a command exists and runs successfully.

        Args:
            command: Command to run
            name: Name for display

        Returns:
            True if command succeeds
        """
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                self.print_success(f"{name} is available")
                self.print_info(result.stdout.strip()[:100])
                return True
            else:
                self.print_failure(f"{name} check failed", result.stderr.strip()[:100])
                return False
        except FileNotFoundError:
            self.print_failure(f"{name} not found")
            return False
        except subprocess.TimeoutExpired:
            self.print_failure(f"{name} timed out")
            return False
        except Exception as e:
            self.print_failure(f"{name} error", str(e))
            return False

    def check_http_endpoint(self, url: str, name: str, expected_status: int = 200, timeout: int = 5) -> bool:
        """Check if HTTP endpoint is accessible.

        Args:
            url: URL to check
            name: Name for display
            expected_status: Expected HTTP status code
            timeout: Request timeout in seconds

        Returns:
            True if endpoint is accessible
        """
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == expected_status:
                self.print_success(f"{name} is healthy ({url})")
                self.print_info(f"Response: {response.text[:100]}")
                return True
            else:
                self.print_warning(
                    f"{name} returned unexpected status",
                    f"Expected {expected_status}, got {response.status_code}",
                )
                return False
        except requests.exceptions.ConnectionError:
            self.print_failure(f"{name} is not accessible", f"Connection refused: {url}")
            return False
        except requests.exceptions.Timeout:
            self.print_failure(f"{name} timed out", f"URL: {url}")
            return False
        except Exception as e:
            self.print_failure(f"{name} error", str(e))
            return False

    def check_file_exists(self, path: str, name: str) -> bool:
        """Check if file exists.

        Args:
            path: File path
            name: Name for display

        Returns:
            True if file exists
        """
        if os.path.exists(path):
            self.print_success(f"{name} exists ({path})")
            return True
        else:
            self.print_failure(f"{name} not found", path)
            return False

    def check_directory_exists(self, path: str, name: str) -> bool:
        """Check if directory exists.

        Args:
            path: Directory path
            name: Name for display

        Returns:
            True if directory exists
        """
        if os.path.isdir(path):
            self.print_success(f"{name} directory exists ({path})")
            return True
        else:
            self.print_failure(f"{name} directory not found", path)
            return False

    def validate_prerequisites(self) -> None:
        """Validate prerequisites are installed."""
        self.print_header("1. Prerequisites")

        self.check_command(["docker", "--version"], "Docker")
        self.check_command(["docker", "compose", "version"], "Docker Compose")
        self.check_command(["python3", "--version"], "Python 3")
        self.check_command(["git", "--version"], "Git")

        # Optional tools
        if self.check_command(["cargo", "--version"], "Rust/Cargo (optional)"):
            pass  # Rust is optional

    def validate_file_structure(self) -> None:
        """Validate file structure."""
        self.print_header("2. File Structure")

        # Core files
        self.check_file_exists("docker-compose.yml", "Docker Compose config")
        self.check_file_exists("requirements.txt", "Python requirements")
        self.check_file_exists("README.md", "README")
        self.check_file_exists("GETTING_STARTED.md", "Getting Started guide")
        self.check_file_exists("ADAPTER_STATUS.md", "Adapter Status doc")

        # Core directories
        self.check_directory_exists("router_service", "Router service")
        self.check_directory_exists("services/memory-gateway", "Memory gateway")
        self.check_directory_exists("client", "Client scripts")
        self.check_directory_exists("adapters/python", "Python adapters")
        self.check_directory_exists("docs", "Documentation")
        self.check_directory_exists("deploy", "Deployment configs")

        # Client requirements
        self.check_file_exists("client/requirements.txt", "Client requirements")

    def validate_docker_services(self, quick: bool = False) -> None:
        """Validate Docker services are running.

        Args:
            quick: Skip slow checks
        """
        self.print_header("3. Docker Services")

        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                self.print_warning(
                    "Docker Compose not running",
                    "Start with: docker compose up -d",
                )
                return

            # Parse output
            try:
                services = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        services.append(json.loads(line))

                if services:
                    self.print_success(f"Found {len(services)} Docker services")
                    for svc in services:
                        name = svc.get("Service", "unknown")
                        status = svc.get("State", "unknown")
                        if status == "running":
                            self.print_info(f"✓ {name}: {status}")
                        else:
                            self.print_warning(f"{name} is not running", f"State: {status}")
                else:
                    self.print_warning(
                        "No Docker services found",
                        "Start with: docker compose up -d",
                    )
            except json.JSONDecodeError:
                self.print_info("Could not parse docker compose output")

        except subprocess.TimeoutExpired:
            self.print_failure("Docker Compose check timed out")
        except Exception as e:
            self.print_failure("Docker Compose check failed", str(e))

    def validate_service_health(self) -> None:
        """Validate service health endpoints."""
        self.print_header("4. Service Health Checks")

        # Core services
        self.check_http_endpoint("http://localhost:7443/healthz", "Router Service")
        self.check_http_endpoint("http://localhost:8080/healthz", "Memory Gateway")

        # Observability
        self.check_http_endpoint("http://localhost:9090/-/healthy", "Prometheus")
        self.check_http_endpoint("http://localhost:3000/api/health", "Grafana")

        # OPA
        self.check_http_endpoint("http://localhost:8181/health", "OPA Policy Engine")

    def validate_python_dependencies(self) -> None:
        """Validate Python dependencies."""
        self.print_header("5. Python Dependencies")

        required_packages = [
            "requests",
            "fastapi",
            "uvicorn",
            "pydantic",
            "typer",
            "rich",
        ]

        for package in required_packages:
            try:
                __import__(package)
                self.print_success(f"Python package '{package}' is installed")
            except ImportError:
                self.print_warning(
                    f"Python package '{package}' not found",
                    f"Install with: pip install {package}",
                )

    def validate_documentation(self) -> None:
        """Validate documentation completeness."""
        self.print_header("6. Documentation")

        docs = [
            ("README.md", "Main README"),
            ("GETTING_STARTED.md", "Getting Started guide"),
            ("ADAPTER_STATUS.md", "Adapter Status"),
            ("CONTRIBUTING.md", "Contributing guide"),
            ("CHANGELOG.md", "Changelog"),
            ("docs/01_ATP.md", "ATP Architecture"),
            ("tools/cli/README.md", "CLI Documentation"),
        ]

        for file_path, name in docs:
            self.check_file_exists(file_path, name)

    def print_summary(self) -> None:
        """Print validation summary."""
        self.print_header("Validation Summary")

        total = self.checks_passed + self.checks_failed + self.checks_warned

        print(f"Total checks: {total}")
        print(f"{Colors.GREEN}✅ Passed: {self.checks_passed}{Colors.END}")
        print(f"{Colors.RED}❌ Failed: {self.checks_failed}{Colors.END}")
        print(f"{Colors.YELLOW}⚠️  Warnings: {self.checks_warned}{Colors.END}")

        if self.checks_failed == 0:
            if self.checks_warned == 0:
                print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 All checks passed! ATP is ready to use.{Colors.END}")
            else:
                print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  Installation is functional but has warnings.{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ Installation has issues. Please review failures above.{Colors.END}")

        print(f"\n{Colors.BLUE}Next steps:{Colors.END}")
        print("  • Read GETTING_STARTED.md for usage guide")
        print("  • Check ADAPTER_STATUS.md for adapter availability")
        print("  • Run: docker compose up -d (if not already running)")
        print("  • Try: python client/health_check.py")

    def run(self, quick: bool = False) -> int:
        """Run all validation checks.

        Args:
            quick: Skip slow checks

        Returns:
            Exit code (0 for success)
        """
        print(f"{Colors.BOLD}ATP Installation Validator{Colors.END}")
        print(f"Checking ATP platform installation...\n")

        self.validate_prerequisites()
        self.validate_file_structure()
        self.validate_docker_services(quick=quick)

        if not quick:
            self.validate_service_health()
            self.validate_python_dependencies()

        self.validate_documentation()

        self.print_summary()

        return 1 if self.checks_failed > 0 else 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate ATP platform installation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip slow checks (service health, dependencies)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output with detailed information",
    )

    args = parser.parse_args()

    validator = Validator(verbose=args.verbose)
    return validator.run(quick=args.quick)


if __name__ == "__main__":
    sys.exit(main())
