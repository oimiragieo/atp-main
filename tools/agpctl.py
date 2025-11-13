#!/usr/bin/env python3
"""
AGP Control CLI Tool (agpctl)

Provides policy linting and what-if simulation capabilities for AGP federation.
"""

import argparse
import fnmatch
import sys
from typing import Any

import yaml

try:
    from metrics.registry import REGISTRY
except ImportError:
    REGISTRY = None


class PolicyLinter:
    """Lint AGP policy files for common errors and best practices."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def lint_policy_file(self, policy_path: str) -> bool:
        """Lint a policy file and return True if valid."""
        try:
            with open(policy_path, encoding="utf-8") as f:
                policy = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to parse YAML: {e}")
            return False

        return self._validate_policy_structure(policy)

    def _validate_policy_structure(self, policy: dict[str, Any]) -> bool:
        """Validate the basic structure of a policy."""
        if not isinstance(policy, dict):
            self.errors.append("Policy must be a dictionary")
            return False

        if "rules" not in policy:
            self.errors.append("Policy must contain 'rules' key")
            return False

        rules = policy.get("rules", [])
        if not isinstance(rules, list):
            self.errors.append("'rules' must be a list")
            return False

        for i, rule in enumerate(rules):
            if not self._validate_rule(rule, i):
                return False

        return len(self.errors) == 0

    def _validate_rule(self, rule: dict[str, Any], index: int) -> bool:
        """Validate a single policy rule."""
        if not isinstance(rule, dict):
            self.errors.append(f"Rule {index} must be a dictionary")
            return False

        # Check required fields
        if "effect" not in rule:
            self.errors.append(f"Rule {index} missing 'effect' field")
            return False

        effect = rule.get("effect")
        if effect not in ["allow", "deny"]:
            self.errors.append(f"Rule {index} effect must be 'allow' or 'deny', got '{effect}'")
            return False

        # Check match structure
        match = rule.get("match", {})
        if not isinstance(match, dict):
            self.errors.append(f"Rule {index} 'match' must be a dictionary")
            return False

        # Validate match patterns
        for key, value in match.items():
            if key == "data_scope_forbidden":
                if not isinstance(value, list):
                    self.errors.append(f"Rule {index} data_scope_forbidden must be a list")
                    return False
            else:
                if not isinstance(value, (str, int)):
                    self.warnings.append(f"Rule {index} {key} should be a string pattern")

        return True

    def get_report(self) -> str:
        """Get a formatted report of linting results."""
        lines = []
        if self.errors:
            lines.append("❌ ERRORS:")
            for error in self.errors:
                lines.append(f"  - {error}")
        else:
            lines.append("✅ No errors found")

        if self.warnings:
            lines.append("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)


class PolicySimulator:
    """Simulate policy decisions with detailed explanations."""

    def __init__(self, policy_path: str):
        self.policy_path = policy_path
        self.policy = self._load_policy()

    def _load_policy(self) -> dict[str, Any]:
        """Load policy from YAML file."""
        with open(self.policy_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def simulate_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        """Simulate a policy decision for given context."""
        trace = []
        decision = "deny"

        for rule_idx, rule in enumerate(self.policy.get("rules", [])):
            rule_trace = self._evaluate_rule(rule, rule_idx, context)
            trace.append(rule_trace)

            if rule_trace["matched"]:
                decision = rule.get("effect", "deny")
                break

        return {"decision": decision, "trace": trace, "context": context}

    def _evaluate_rule(self, rule: dict[str, Any], rule_idx: int, context: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single rule against context."""
        match_criteria = rule.get("match", {})
        reasons = []
        matched = True

        for key, pattern in match_criteria.items():
            if key == "data_scope_forbidden":
                # Special handling for forbidden data scopes
                context_scopes = set(context.get("data_scope", []))
                forbidden_scopes = set(pattern)
                overlap = context_scopes & forbidden_scopes

                if overlap:
                    reasons.append(f"❌ Forbidden data scopes: {list(overlap)}")
                    matched = False
                else:
                    reasons.append("✅ No forbidden data scopes")
            else:
                # Pattern matching for other fields
                context_value = str(context.get(key, ""))
                pattern_str = str(pattern)

                if fnmatch.fnmatch(context_value, pattern_str):
                    reasons.append(f"✅ {key} '{context_value}' matches '{pattern_str}'")
                else:
                    reasons.append(f"❌ {key} '{context_value}' does not match '{pattern_str}'")
                    matched = False

        return {"rule_index": rule_idx, "effect": rule.get("effect", "deny"), "matched": matched, "reasons": reasons}


def main():
    parser = argparse.ArgumentParser(description="AGP Control CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Lint policy files")
    lint_parser.add_argument("policy_file", help="Path to policy YAML file")

    # What-if command
    whatif_parser = subparsers.add_parser("whatif", help="Simulate policy decisions")
    whatif_parser.add_argument("policy_file", help="Path to policy YAML file")
    whatif_parser.add_argument("--tenant", help="Tenant name")
    whatif_parser.add_argument("--task-type", help="Task type")
    whatif_parser.add_argument("--data-scope", nargs="*", help="Data scopes")

    args = parser.parse_args()

    if args.command == "lint":
        linter = PolicyLinter()
        if linter.lint_policy_file(args.policy_file):
            print("✅ Policy file is valid")
            if linter.warnings:
                print("\n" + linter.get_report())
        else:
            print("❌ Policy file has errors")
            print(linter.get_report())
            sys.exit(1)

        # Track lint invocations
        if REGISTRY:
            REGISTRY.counter("policy_lint_invocations_total").inc()

    elif args.command == "whatif":
        # Build context from arguments
        context = {}
        if args.tenant:
            context["tenant"] = args.tenant
        if args.task_type:
            context["task_type"] = args.task_type
        if args.data_scope:
            context["data_scope"] = args.data_scope

        if not context:
            print("❌ Must provide at least one context parameter (--tenant, --task-type, or --data-scope)")
            sys.exit(1)

        try:
            simulator = PolicySimulator(args.policy_file)
            result = simulator.simulate_decision(context)

            print(f"🎯 Decision: {result['decision'].upper()}")
            print(f"📋 Context: {result['context']}")
            print("\n📝 Rule Evaluation Trace:")

            for trace_item in result["trace"]:
                print(f"\nRule {trace_item['rule_index']}: {trace_item['effect'].upper()}")
                for reason in trace_item["reasons"]:
                    print(f"  {reason}")

                if trace_item["matched"]:
                    print("  🎯 This rule matched - decision made!")
                    break

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
