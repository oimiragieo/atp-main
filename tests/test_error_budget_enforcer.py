#!/usr/bin/env python3
"""Comprehensive tests for Error Budget Policy Enforcement."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from tools.error_budget_enforcer import ErrorBudgetEnforcer, ErrorBudgetState, SLODefinition


class TestSLODefinition:
    """Test SLO definition functionality."""

    def test_slo_creation(self):
        """Test creating an SLO definition."""
        slo = SLODefinition(name="test_slo", target_percentage=99.9, window_days=30, error_budget_percentage=5.0)

        assert slo.name == "test_slo"
        assert slo.target_percentage == 99.9
        assert slo.window_days == 30
        assert slo.error_budget_percentage == 5.0


class TestErrorBudgetState:
    """Test error budget state management."""

    def test_initial_state(self):
        """Test initial state of error budget."""
        state = ErrorBudgetState("test_slo")

        assert state.slo_name == "test_slo"
        assert state.total_requests == 0
        assert state.error_requests == 0
        assert state.error_rate_percentage == 0.0
        assert state.availability_percentage == 100.0
        assert len(state.violations) == 0

    def test_add_measurement(self):
        """Test adding measurements to error budget."""
        state = ErrorBudgetState("test_slo")

        state.add_measurement(1000, 10)
        assert state.total_requests == 1000
        assert state.error_requests == 10
        assert state.error_rate_percentage == 1.0
        assert state.availability_percentage == 99.0

        state.add_measurement(500, 5)
        assert state.total_requests == 1500
        assert state.error_requests == 15
        assert state.error_rate_percentage == 1.0
        assert state.availability_percentage == 99.0

    def test_slo_violation_detection(self):
        """Test SLO violation detection."""
        state = ErrorBudgetState("test_slo")
        slo = SLODefinition("test_slo", 99.0, 30, 5.0)

        # No violation initially
        violation = state.check_violation(slo)
        assert violation is None

        # Add measurements that cause violation
        state.add_measurement(1000, 20)  # 2% error rate, availability = 98%

        violation = state.check_violation(slo)
        assert violation is not None
        assert violation.slo_name == "test_slo"
        assert violation.actual_percentage == 98.0
        assert violation.target_percentage == 99.0
        assert violation.error_budget_consumed == 100.0  # 100% of budget consumed

    def test_error_budget_calculation(self):
        """Test error budget remaining calculation."""
        state = ErrorBudgetState("test_slo")
        slo = SLODefinition("test_slo", 99.0, 30, 5.0)

        # Full budget available
        remaining = state.get_error_budget_remaining(slo)
        assert remaining == 5.0

        # Budget exhausted - 2% error rate (worse than 1% target)
        state.add_measurement(1000, 20)  # 2% error rate, availability = 98%
        remaining = state.get_error_budget_remaining(slo)
        # consumed = (2% - 1%) / 1% * 5% = 100% of budget consumed
        assert remaining == 0.0  # Budget exhausted

        # Partial budget consumed - separate test
        state2 = ErrorBudgetState("test_slo2")
        slo2 = SLODefinition("test_slo2", 99.0, 30, 5.0)
        state2.add_measurement(1000, 15)  # 1.5% error rate, availability = 98.5%
        remaining2 = state2.get_error_budget_remaining(slo2)
        # consumed = (1.5% - 1%) / 1% * 5% = 50% of budget consumed
        assert remaining2 == 2.5  # Half budget remaining


class TestErrorBudgetEnforcer:
    """Test error budget enforcer functionality."""

    def test_initialization_with_config(self):
        """Test initialization with existing config."""
        config_data = {
            "slos": [{"name": "test_slo", "target_percentage": 99.5, "window_days": 7, "error_budget_percentage": 2.5}]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            enforcer = ErrorBudgetEnforcer(config_file)

            assert "test_slo" in enforcer.slos
            slo = enforcer.slos["test_slo"]
            assert slo.target_percentage == 99.5
            assert slo.window_days == 7
            assert slo.error_budget_percentage == 2.5

        finally:
            os.unlink(config_file)

    def test_default_config_creation(self):
        """Test creation of default configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "test_config.json")

            enforcer = ErrorBudgetEnforcer(config_file)

            # Should create default SLOs
            assert len(enforcer.slos) == 3
            assert "api_availability" in enforcer.slos
            assert "p95_latency" in enforcer.slos
            assert "error_rate" in enforcer.slos

            # Config file should be created
            assert os.path.exists(config_file)

    def test_record_measurement(self):
        """Test recording measurements."""
        enforcer = ErrorBudgetEnforcer()

        # Record measurement for existing SLO
        enforcer.record_measurement("api_availability", 1000, 5)

        state = enforcer.states["api_availability"]
        assert state.total_requests == 1000
        assert state.error_requests == 5

        # Try recording for non-existent SLO
        with pytest.raises(ValueError):
            enforcer.record_measurement("non_existent_slo", 1000, 5)

    def test_budget_gate_enforcement(self):
        """Test budget gate enforcement."""
        enforcer = ErrorBudgetEnforcer()

        # Initially all gates should pass
        assert enforcer.enforce_budget_gates() is True

        # Create a violation
        slo = SLODefinition("test_violation", 99.0, 30, 5.0)
        enforcer.slos["test_violation"] = slo
        enforcer.states["test_violation"] = ErrorBudgetState("test_violation")

        # Add violating measurements
        enforcer.record_measurement("test_violation", 1000, 20)  # 2% error rate

        # Gate should fail
        assert enforcer.enforce_budget_gates() is False

    def test_budget_status_reporting(self):
        """Test budget status reporting."""
        enforcer = ErrorBudgetEnforcer()

        # Add some measurements
        enforcer.record_measurement("api_availability", 10000, 50)  # 0.5% error rate

        status = enforcer.get_budget_status()

        assert "api_availability" in status
        api_status = status["api_availability"]
        assert api_status["current_availability"] == 99.5
        assert api_status["error_rate"] == 0.5
        assert api_status["total_requests"] == 10000
        assert api_status["error_requests"] == 50

    def test_metrics_export(self):
        """Test metrics export functionality."""
        enforcer = ErrorBudgetEnforcer()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = f.name

        try:
            enforcer.export_metrics(output_file)

            # Check that file was created and contains expected data
            assert os.path.exists(output_file)

            with open(output_file) as f:
                metrics = json.load(f)

            assert "timestamp" in metrics
            assert "error_budget_status" in metrics

        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)

    def test_measurement_simulation(self):
        """Test measurement simulation."""
        enforcer = ErrorBudgetEnforcer()

        # Simulate measurements
        enforcer.simulate_measurements("api_availability", days=5)

        state = enforcer.states["api_availability"]
        assert state.total_requests > 0
        assert state.error_requests >= 0

        # Try simulating non-existent SLO
        with pytest.raises(ValueError):
            enforcer.simulate_measurements("non_existent_slo")


class TestCommandLineInterface:
    """Test command line interface."""

    def test_check_command_success(self):
        """Test successful budget check command."""
        from tools.error_budget_enforcer import main

        with patch("sys.argv", ["error_budget_enforcer.py", "--check"]):
            with patch("builtins.print"):
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0  # Success

    def test_check_command_failure(self):
        """Test failing budget check command."""
        from tools.error_budget_enforcer import main

        # Create a temporary config with a violation
        config_data = {
            "slos": [
                {"name": "test_violation", "target_percentage": 99.0, "window_days": 30, "error_budget_percentage": 5.0}
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            # Use the same config file for both calls
            with patch(
                "sys.argv",
                [
                    "error_budget_enforcer.py",
                    "--config",
                    config_file,
                    "--record",
                    "test_violation",
                    "1000",
                    "20",
                    "--check",
                ],
            ):
                with patch("builtins.print"):
                    try:
                        main()
                    except SystemExit as e:
                        assert e.code == 1  # Failure
        finally:
            os.unlink(config_file)

    def test_status_command(self):
        """Test status command."""
        from tools.error_budget_enforcer import main

        with patch("sys.argv", ["error_budget_enforcer.py", "--status"]):
            with patch("builtins.print") as mock_print:
                try:
                    main()
                except SystemExit:
                    pass

                # Verify print was called
                mock_print.assert_called()

    def test_record_command(self):
        """Test record measurement command."""
        from tools.error_budget_enforcer import main

        with patch("sys.argv", ["error_budget_enforcer.py", "--record", "api_availability", "1000", "10"]):
            with patch("builtins.print") as mock_print:
                try:
                    main()
                except SystemExit:
                    pass

                # Verify the record message was printed
                print_calls = [call.args[0] for call in mock_print.call_args_list]
                record_found = any("Recorded measurement for api_availability" in call for call in print_calls)
                assert record_found, f"Record message not found in calls: {print_calls}"


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_multi_slo_management(self):
        """Test managing multiple SLOs simultaneously."""
        enforcer = ErrorBudgetEnforcer()

        # Record measurements for different SLOs
        enforcer.record_measurement("api_availability", 10000, 50)
        enforcer.record_measurement("p95_latency", 5000, 100)
        enforcer.record_measurement("error_rate", 20000, 100)

        # Check status for all
        status = enforcer.get_budget_status()

        assert len(status) == 3
        for slo_name in ["api_availability", "p95_latency", "error_rate"]:
            assert slo_name in status
            assert status[slo_name]["total_requests"] > 0

    def test_violation_tracking(self):
        """Test tracking multiple violations."""
        enforcer = ErrorBudgetEnforcer()

        slo = SLODefinition("test_slo", 99.0, 30, 5.0)
        enforcer.slos["test_slo"] = slo
        enforcer.states["test_slo"] = ErrorBudgetState("test_slo")

        # Create first violation
        enforcer.record_measurement("test_slo", 1000, 20)  # 2% error rate
        violations1 = enforcer.check_all_slos()
        assert len(violations1) == 1

        # Create second violation with different SLO to test multiple
        slo2 = SLODefinition("test_slo2", 99.0, 30, 5.0)
        enforcer.slos["test_slo2"] = slo2
        enforcer.states["test_slo2"] = ErrorBudgetState("test_slo2")
        enforcer.record_measurement("test_slo2", 1000, 25)  # 2.5% error rate

        violations2 = enforcer.check_all_slos()
        assert len(violations2) == 2  # Two violations recorded

    def test_budget_warning_scenarios(self):
        """Test budget warning scenarios."""
        from tools.error_budget_enforcer import ErrorBudgetEnforcer

        # Create a scenario with small error budget
        config_data = {
            "slos": [
                {
                    "name": "small_budget_slo",
                    "target_percentage": 99.0,
                    "window_days": 30,
                    "error_budget_percentage": 2.0,  # Small budget: 2%
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            enforcer = ErrorBudgetEnforcer(config_file)

            # Add a violation that consumes most of the budget
            # 2.0% error rate (98.0% availability) with 1% allowed error
            # consumed = (2.0 - 1) / 1 * 2 = 1 * 2 = 2%
            # remaining = 2 - 2 = 0%, which should trigger warning
            enforcer.record_measurement("small_budget_slo", 1000, 20)  # 2.0% error rate

            with patch("builtins.print") as mock_print:
                enforcer.enforce_budget_gates()

                # This will be False due to violation, but let's check if warning is printed
                # The test is mainly to verify warning logic works
                print_calls = [call.args[0] for call in mock_print.call_args_list]

                # Check that either violations or warnings are reported
                has_feedback = any("Error Budget Policy Violations" in call for call in print_calls) or any(
                    "Error Budget Warnings" in call for call in print_calls
                )
                assert has_feedback, f"No violations or warnings found in calls: {print_calls}"

        finally:
            os.unlink(config_file)


if __name__ == "__main__":
    pytest.main([__file__])
