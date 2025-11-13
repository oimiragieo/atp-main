"""GAP-139: Adapter interface compliance checker."""

import importlib.util
import inspect
import os
from typing import Any

from metrics.registry import REGISTRY


class AdapterComplianceChecker:
    """Checks adapter implementations for interface compliance."""

    REQUIRED_METHODS = {"Estimate", "Stream", "Health"}

    def __init__(self) -> None:
        # Initialize metrics for GAP-139
        self._non_compliant_adapters = REGISTRY.gauge("non_compliant_adapters")

    def check_adapter_module(self, module_path: str) -> dict[str, Any]:
        """Check a single adapter module for compliance."""
        result: dict[str, Any] = {
            "module": os.path.basename(module_path),
            "compliant": True,
            "missing_methods": [],
            "errors": [],
        }

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location("adapter_module", module_path)
            if not spec or not spec.loader:
                result["errors"].append("Could not load module")
                result["compliant"] = False
                return result

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find the Adapter class
            adapter_class = self._find_adapter_class(module)
            if not adapter_class:
                result["errors"].append("No Adapter class found")
                result["compliant"] = False
                return result

            # Check for required methods
            missing_methods = self._check_required_methods(adapter_class)
            if missing_methods:
                result["missing_methods"] = missing_methods
                result["compliant"] = False

        except Exception as e:
            result["errors"].append(str(e))
            result["compliant"] = False

        return result

    def check_adapters_directory(self, adapters_dir: str) -> dict[str, Any]:
        """Check all adapters in a directory."""
        results = {}
        total_adapters = 0
        compliant_count = 0

        for root, _dirs, files in os.walk(adapters_dir):
            for file in files:
                if file == "server.py":
                    module_path = os.path.join(root, file)
                    result = self.check_adapter_module(module_path)
                    results[result["module"]] = result
                    total_adapters += 1
                    if result["compliant"]:
                        compliant_count += 1

        # Update metrics
        non_compliant = total_adapters - compliant_count
        self._non_compliant_adapters.set(non_compliant)

        summary = {
            "total_adapters": total_adapters,
            "compliant_adapters": compliant_count,
            "non_compliant_adapters": non_compliant,
            "results": results,
        }

        return summary

    def _find_adapter_class(self, module: Any) -> Any:
        """Find the Adapter class in a module."""
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and name == "Adapter"
                and hasattr(obj, "__module__")
                and obj.__module__ == module.__name__
            ):
                return obj
        return None

    def _check_required_methods(self, adapter_class: Any) -> list[str]:
        """Check if adapter class has all required methods."""
        missing = []
        for method_name in self.REQUIRED_METHODS:
            if not hasattr(adapter_class, method_name):
                missing.append(method_name)
            else:
                method = getattr(adapter_class, method_name)
                if not callable(method):
                    missing.append(f"{method_name} (not callable)")
        return missing

    def generate_compliance_report(self, results: dict[str, Any]) -> str:
        """Generate a human-readable compliance report."""
        report_lines = []
        report_lines.append("Adapter Interface Compliance Report")
        report_lines.append("=" * 40)
        report_lines.append("")

        summary = results
        results_dict = summary.pop("results", {})

        report_lines.append(f"Total adapters: {summary['total_adapters']}")
        report_lines.append(f"Compliant: {summary['compliant_adapters']}")
        report_lines.append(f"Non-compliant: {summary['non_compliant_adapters']}")
        report_lines.append("")

        if results_dict:
            report_lines.append("Details:")
            for adapter_name, result in results_dict.items():
                status = "✅ COMPLIANT" if result["compliant"] else "❌ NON-COMPLIANT"
                report_lines.append(f"  {adapter_name}: {status}")

                if result["missing_methods"]:
                    report_lines.append(f"    Missing methods: {', '.join(result['missing_methods'])}")

                if result["errors"]:
                    report_lines.append(f"    Errors: {', '.join(result['errors'])}")
                report_lines.append("")

        return "\n".join(report_lines)
