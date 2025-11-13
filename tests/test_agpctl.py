"""Tests for agpctl CLI tool (GAP-109F)."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from tools.agpctl import PolicyLinter, PolicySimulator


def test_policy_linter_valid_policy():
    """Test linting a valid policy file."""
    policy = {
        "rules": [
            {"match": {"tenant": "acme", "task_type": "qa", "data_scope_forbidden": ["secrets"]}, "effect": "allow"}
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        linter = PolicyLinter()
        result = linter.lint_policy_file(policy_path)
        assert result is True
        assert len(linter.errors) == 0
    finally:
        Path(policy_path).unlink()


def test_policy_linter_invalid_policy():
    """Test linting an invalid policy file."""
    policy = {
        "rules": [
            {
                "match": "invalid",  # Should be dict
                "effect": "allow",
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        linter = PolicyLinter()
        result = linter.lint_policy_file(policy_path)
        assert result is False
        assert len(linter.errors) > 0
    finally:
        Path(policy_path).unlink()


def test_policy_linter_missing_effect():
    """Test linting policy with missing effect."""
    policy = {
        "rules": [
            {
                "match": {"tenant": "*"}
                # Missing effect
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        linter = PolicyLinter()
        result = linter.lint_policy_file(policy_path)
        assert result is False
        assert any("missing 'effect'" in error for error in linter.errors)
    finally:
        Path(policy_path).unlink()


def test_policy_simulator_allow_decision():
    """Test policy simulator with allow decision."""
    policy = {"rules": [{"match": {"tenant": "acme", "task_type": "qa"}, "effect": "allow"}]}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        simulator = PolicySimulator(policy_path)
        context = {"tenant": "acme", "task_type": "qa"}
        result = simulator.simulate_decision(context)

        assert result["decision"] == "allow"
        assert len(result["trace"]) == 1
        assert result["trace"][0]["matched"] is True
    finally:
        Path(policy_path).unlink()


def test_policy_simulator_deny_decision():
    """Test policy simulator with deny decision."""
    policy = {
        "rules": [
            {"match": {"tenant": "acme", "task_type": "qa"}, "effect": "allow"},
            {"match": {"tenant": "*"}, "effect": "deny"},
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        simulator = PolicySimulator(policy_path)
        context = {"tenant": "other", "task_type": "qa"}
        result = simulator.simulate_decision(context)

        assert result["decision"] == "deny"
        assert len(result["trace"]) == 2
        assert result["trace"][0]["matched"] is False
        assert result["trace"][1]["matched"] is True
    finally:
        Path(policy_path).unlink()


def test_policy_simulator_forbidden_data_scope():
    """Test policy simulator with forbidden data scope."""
    policy = {"rules": [{"match": {"tenant": "*", "data_scope_forbidden": ["secrets", "pci"]}, "effect": "deny"}]}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(policy, f)
        policy_path = f.name

    try:
        simulator = PolicySimulator(policy_path)
        context = {"tenant": "acme", "data_scope": ["public", "secrets"]}
        result = simulator.simulate_decision(context)

        # When forbidden data scopes are present, the rule should NOT match
        assert result["decision"] == "deny"  # Default deny when no rules match
        assert result["trace"][0]["matched"] is False
        assert any("Forbidden data scopes" in reason for reason in result["trace"][0]["reasons"])
    finally:
        Path(policy_path).unlink()


@patch("sys.argv", ["agpctl", "lint", "tools/policy_poc.yaml"])
def test_cli_lint_command(capsys):
    """Test CLI lint command."""
    from tools.agpctl import main

    main()

    captured = capsys.readouterr()
    assert "✅ Policy file is valid" in captured.out


@patch("sys.argv", ["agpctl", "whatif", "tools/policy_poc.yaml", "--tenant", "acme", "--task-type", "qa"])
def test_cli_whatif_command(capsys):
    """Test CLI whatif command."""
    from tools.agpctl import main

    main()

    captured = capsys.readouterr()
    assert "Decision: ALLOW" in captured.out or "Decision: DENY" in captured.out


def test_cli_missing_args():
    """Test CLI with missing arguments."""
    with patch("sys.argv", ["agpctl"]):
        with patch("argparse.ArgumentParser.print_help") as mock_help:
            from tools.agpctl import main

            main()
            mock_help.assert_called_once()
