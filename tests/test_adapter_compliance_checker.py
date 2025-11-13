"""Tests for GAP-139: Adapter interface compliance checker."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.adapter_compliance_checker import AdapterComplianceChecker


def test_compliance_checker_compliant_adapter():
    """Test compliance checker with a compliant adapter."""
    checker = AdapterComplianceChecker()

    # Create a temporary compliant adapter module
    adapter_code = """
import asyncio
from collections.abc import AsyncIterator
from typing import Any

class Adapter:
    async def Estimate(self, req, ctx):
        pass
    
    async def Stream(self, req, ctx):
        pass
    
    async def Health(self, req, ctx):
        pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(adapter_code)
        temp_path = f.name

    try:
        result = checker.check_adapter_module(temp_path)
        assert result["compliant"] is True
        assert len(result["missing_methods"]) == 0
        assert len(result["errors"]) == 0
    finally:
        os.unlink(temp_path)

    print("OK: Compliant adapter test passed")


def test_compliance_checker_missing_methods():
    """Test compliance checker with missing methods."""
    checker = AdapterComplianceChecker()

    # Create a temporary non-compliant adapter module
    adapter_code = """
class Adapter:
    async def Estimate(self, req, ctx):
        pass
    # Missing Stream and Health methods
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(adapter_code)
        temp_path = f.name

    try:
        result = checker.check_adapter_module(temp_path)
        assert result["compliant"] is False
        assert "Stream" in result["missing_methods"]
        assert "Health" in result["missing_methods"]
    finally:
        os.unlink(temp_path)

    print("OK: Missing methods test passed")


def test_compliance_checker_no_adapter_class():
    """Test compliance checker with no Adapter class."""
    checker = AdapterComplianceChecker()

    # Create a temporary module without Adapter class
    adapter_code = """
def some_function():
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(adapter_code)
        temp_path = f.name

    try:
        result = checker.check_adapter_module(temp_path)
        assert result["compliant"] is False
        assert "No Adapter class found" in result["errors"]
    finally:
        os.unlink(temp_path)

    print("OK: No adapter class test passed")


def test_compliance_checker_invalid_module():
    """Test compliance checker with invalid module."""
    checker = AdapterComplianceChecker()

    result = checker.check_adapter_module("/nonexistent/path.py")
    assert result["compliant"] is False
    assert len(result["errors"]) > 0

    print("OK: Invalid module test passed")


def test_compliance_report_generation():
    """Test compliance report generation."""
    checker = AdapterComplianceChecker()

    # Mock results
    results = {
        "total_adapters": 2,
        "compliant_adapters": 1,
        "non_compliant_adapters": 1,
        "results": {
            "compliant_adapter": {
                "module": "compliant_adapter",
                "compliant": True,
                "missing_methods": [],
                "errors": [],
            },
            "non_compliant_adapter": {
                "module": "non_compliant_adapter",
                "compliant": False,
                "missing_methods": ["Stream", "Health"],
                "errors": [],
            },
        },
    }

    report = checker.generate_compliance_report(results)
    assert "Adapter Interface Compliance Report" in report
    assert "Total adapters: 2" in report
    assert "Compliant: 1" in report
    assert "Non-compliant: 1" in report
    assert "✅ COMPLIANT" in report
    assert "❌ NON-COMPLIANT" in report

    print("OK: Compliance report generation test passed")


def test_directory_check():
    """Test checking adapters directory."""
    checker = AdapterComplianceChecker()

    # Create temporary directory with adapter files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a compliant adapter
        compliant_dir = os.path.join(temp_dir, "compliant_adapter")
        os.makedirs(compliant_dir)

        with open(os.path.join(compliant_dir, "server.py"), "w") as f:
            f.write("""
class Adapter:
    async def Estimate(self, req, ctx): pass
    async def Stream(self, req, ctx): pass  
    async def Health(self, req, ctx): pass
""")

        # Create a non-compliant adapter
        non_compliant_dir = os.path.join(temp_dir, "non_compliant_adapter")
        os.makedirs(non_compliant_dir)

        with open(os.path.join(non_compliant_dir, "server.py"), "w") as f:
            f.write("""
class Adapter:
    async def Estimate(self, req, ctx): pass
    # Missing Stream and Health
""")

        results = checker.check_adapters_directory(temp_dir)
        assert results["total_adapters"] == 2
        assert results["compliant_adapters"] == 1
        assert results["non_compliant_adapters"] == 1

    print("OK: Directory check test passed")


if __name__ == "__main__":
    test_compliance_checker_compliant_adapter()
    test_compliance_checker_missing_methods()
    test_compliance_checker_no_adapter_class()
    test_compliance_checker_invalid_module()
    test_compliance_report_generation()
    test_directory_check()
    print("All GAP-139 adapter compliance tests passed!")
