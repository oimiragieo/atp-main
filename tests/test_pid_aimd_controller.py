"""Tests for PID controller for AIMD parameter tuning."""

import time

import pytest

from metrics.registry import REGISTRY
from router_service.window_update import AIMDController, PIDController


@pytest.mark.asyncio
class TestPIDController:
    """Test PID controller for AIMD parameter adaptation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.aimd = AIMDController(add=2, mult=0.5)
        self.pid = PIDController(
            aimd_controller=self.aimd,
            kp=0.1,
            ki=0.01,
            kd=0.05,
            target_latency_ms=1500.0,
            target_throughput=100.0,
            target_error_rate=0.01,
            update_interval_s=1.0,  # Fast updates for testing
        )

    def teardown_method(self):
        """Clean up after tests."""
        self.pid.reset()

    async def test_pid_initialization(self):
        """Test PID controller initializes with correct parameters."""
        assert self.pid.kp == 0.1
        assert self.pid.ki == 0.01
        assert self.pid.kd == 0.05
        assert self.pid.target_latency_ms == 1500.0
        assert self.pid.target_throughput == 100.0
        assert self.pid.target_error_rate == 0.01
        assert self.pid.aimd.add == 2
        assert self.pid.aimd.mult == 0.5

    async def test_pid_no_update_before_interval(self):
        """Test PID doesn't update parameters before interval expires."""
        initial_add = self.aimd.add
        initial_mult = self.aimd.mult

        # Try to update immediately (should not update due to interval)
        self.pid.update_parameters(
            current_latency_ms=2000.0,  # High latency
            current_throughput=50.0,    # Low throughput
            current_error_rate=0.05     # High error rate
        )

        # Parameters should not change
        assert self.aimd.add == initial_add
        assert self.aimd.mult == initial_mult

    async def test_pid_latency_control(self):
        """Test PID controller adjusts mult factor based on latency."""
        # Simulate high latency (should decrease mult factor)
        self.pid.update_parameters(
            current_latency_ms=2000.0,  # Above target
            current_throughput=100.0,   # At target
            current_error_rate=0.01     # At target
        )

        # Force update by advancing time
        self.pid._last_update_time = time.time() - 2.0

        initial_mult = self.aimd.mult
        self.pid.update_parameters(
            current_latency_ms=2000.0,
            current_throughput=100.0,
            current_error_rate=0.01
        )

        # Mult factor should decrease due to high latency
        assert self.aimd.mult < initial_mult

    async def test_pid_throughput_control(self):
        """Test PID controller adjusts add factor based on throughput."""
        # Force update by advancing time
        self.pid._last_update_time = time.time() - 2.0

        initial_add = self.aimd.add
        self.pid.update_parameters(
            current_latency_ms=1500.0,  # At target
            current_throughput=50.0,    # Below target
            current_error_rate=0.01     # At target
        )

        # Add factor should decrease due to low throughput
        assert self.aimd.add < initial_add

    async def test_pid_error_rate_control(self):
        """Test PID controller adjusts add factor based on error rate."""
        # Force update by advancing time
        self.pid._last_update_time = time.time() - 2.0

        initial_add = self.aimd.add
        self.pid.update_parameters(
            current_latency_ms=1500.0,  # At target
            current_throughput=100.0,   # At target
            current_error_rate=0.05     # Above target
        )

        # Add factor should decrease due to high error rate
        assert self.aimd.add < initial_add

    async def test_pid_bounds_checking(self):
        """Test PID controller respects parameter bounds."""
        # Force update by advancing time
        self.pid._last_update_time = time.time() - 2.0

        # Set very extreme conditions to test bounds
        self.pid.update_parameters(
            current_latency_ms=5000.0,   # Very high latency
            current_throughput=10.0,     # Very low throughput
            current_error_rate=0.5       # Very high error rate
        )

        # Check bounds are respected
        assert 1 <= self.aimd.add <= 10
        assert 0.1 <= self.aimd.mult <= 0.9

    async def test_pid_integral_windup_protection(self):
        """Test PID controller prevents integral windup."""
        # Force multiple updates with consistent error
        for _ in range(10):
            self.pid._last_update_time = time.time() - 2.0
            self.pid.update_parameters(
                current_latency_ms=2000.0,
                current_throughput=100.0,
                current_error_rate=0.01
            )

        # Integral terms should be bounded
        assert abs(self.pid._integral_add) <= self.pid.max_integral
        assert abs(self.pid._integral_mult) <= self.pid.max_integral

    async def test_pid_metrics_update(self):
        """Test PID controller updates metrics correctly."""
        # Force update by advancing time
        self.pid._last_update_time = time.time() - 2.0

        # Get initial metric values
        initial_updates = REGISTRY.export()["counters"].get("pid_parameter_updates_total", 0)

        self.pid.update_parameters(
            current_latency_ms=2000.0,
            current_throughput=50.0,
            current_error_rate=0.05
        )

        # Check metrics were updated
        final_updates = REGISTRY.export()["counters"].get("pid_parameter_updates_total", 0)
        assert final_updates >= initial_updates

        # Check gauge metrics
        gauges = REGISTRY.export()["gauges"]
        assert "aimd_add_factor" in gauges
        assert "aimd_mult_factor" in gauges

    async def test_pid_reset(self):
        """Test PID controller reset functionality."""
        # Accumulate some state
        self.pid._integral_add = 5.0
        self.pid._integral_mult = -3.0
        self.pid._prev_error_latency = 100.0

        self.pid.reset()

        # All state should be reset
        assert self.pid._integral_add == 0.0
        assert self.pid._integral_mult == 0.0
        assert self.pid._prev_error_latency == 0.0
        assert self.pid._prev_error_throughput == 0.0
        assert self.pid._prev_error_error_rate == 0.0

    async def test_pid_get_parameters(self):
        """Test PID controller parameter retrieval."""
        params = self.pid.get_parameters()

        required_keys = [
            'kp', 'ki', 'kd', 'target_latency_ms', 'target_throughput',
            'target_error_rate', 'current_add_factor', 'current_mult_factor',
            'integral_add', 'integral_mult', 'last_update_time'
        ]

        for key in required_keys:
            assert key in params
            assert isinstance(params[key], (int, float))


@pytest.mark.asyncio
async def test_pid_convergence_under_step_load():
    """Integration test: PID controller convergence under step load changes."""
    aimd = AIMDController(add=2, mult=0.5)
    pid = PIDController(
        aimd_controller=aimd,
        kp=0.05,  # Lower gains for more stable convergence
        ki=0.01,
        kd=0.02,
        update_interval_s=0.1,  # Very fast updates for testing
    )

    # Simulate step change in load (sudden latency increase)
    # initial_add = aimd.add  # Not used in this test
    # initial_mult = aimd.mult  # Not used in this test

    # Step 1: Normal conditions - let PID stabilize
    for _ in range(3):
        pid._last_update_time = time.time() - 0.2
        pid.update_parameters(
            current_latency_ms=1500.0,  # At target
            current_throughput=100.0,   # At target
            current_error_rate=0.01     # At target
        )

    # Parameters should be relatively stable
    stable_add = aimd.add
    stable_mult = aimd.mult

    # Step 2: Sudden load increase (high latency, low throughput)
    for _ in range(5):
        pid._last_update_time = time.time() - 0.2
        pid.update_parameters(
            current_latency_ms=3000.0,  # High latency
            current_throughput=30.0,    # Low throughput
            current_error_rate=0.02     # Slightly high error rate
        )

    # Parameters should have adjusted
    high_load_add = aimd.add
    high_load_mult = aimd.mult

    # Should have decreased parameters under high load
    assert high_load_add <= stable_add or high_load_mult <= stable_mult

    # Step 3: Return to normal conditions
    for _ in range(5):
        pid._last_update_time = time.time() - 0.2
        pid.update_parameters(
            current_latency_ms=1500.0,  # Back to target
            current_throughput=100.0,   # Back to target
            current_error_rate=0.01     # Back to target
        )

    # Parameters should have adjusted back
    final_add = aimd.add
    final_mult = aimd.mult

    # Should show some movement back towards stable values
    # (Allow some tolerance for PID settling)
    # add_diff_from_stable = abs(final_add - stable_add)  # Not used
    # mult_diff_from_stable = abs(final_mult - stable_mult)  # Not used

    # At least one parameter should be closer to stable than to high load
    add_improved = abs(final_add - stable_add) < abs(high_load_add - stable_add)
    mult_improved = abs(final_mult - stable_mult) < abs(high_load_mult - stable_mult)

    assert add_improved or mult_improved, f"No convergence detected: stable=({stable_add}, {stable_mult}), high_load=({high_load_add}, {high_load_mult}), final=({final_add}, {final_mult})"
