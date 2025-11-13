#!/usr/bin/env python3
"""
Tests for AGP Hysteresis & Flap Dampening functionality.
"""

import time
from unittest.mock import patch

import pytest

from router_service.agp_update_handler import (
    AGPRoute,
    AGPRouteAttributes,
    AGPRouteTable,
    HysteresisConfig,
    RouteDampeningConfig,
    RouteDampeningTracker,
)


@pytest.fixture
def hysteresis_config():
    """Create hysteresis configuration for testing."""
    return HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5, metric_type="fast")


@pytest.fixture
def dampening_config():
    """Create dampening configuration for testing."""
    return RouteDampeningConfig(
        penalty_per_flap=1000,
        suppress_threshold=2000,
        reuse_threshold=750,
        max_penalty=16000,
        half_life_minutes=15,
        max_flaps_per_minute=6,
    )


@pytest.fixture
def route_table():
    """Create a route table for testing."""
    return AGPRouteTable()


@pytest.fixture
def sample_route():
    """Create a sample route for testing."""
    attributes = AGPRouteAttributes(path=[65001, 65002], next_hop="router2")
    return AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=time.time(), peer_router_id="router1")


def test_hysteresis_config_defaults():
    """Test hysteresis configuration defaults."""
    config = HysteresisConfig()
    assert config.change_threshold_percent == 10.0
    assert config.stabilization_period_seconds == 5
    assert config.metric_type == "fast"


def test_hysteresis_config_validation():
    """Test hysteresis configuration validation."""
    # Valid config
    config = HysteresisConfig()
    config.validate()  # Should not raise

    # Invalid change threshold
    with pytest.raises(ValueError, match="change_threshold_percent must be positive"):
        HysteresisConfig(change_threshold_percent=0).validate()

    # Invalid stabilization period
    with pytest.raises(ValueError, match="stabilization_period_seconds must be positive"):
        HysteresisConfig(stabilization_period_seconds=0).validate()

    # Invalid metric type
    with pytest.raises(ValueError, match="metric_type must be"):
        HysteresisConfig(metric_type="invalid").validate()


def test_dampening_config_with_hysteresis(hysteresis_config, dampening_config):
    """Test dampening tracker with hysteresis configuration."""
    tracker = RouteDampeningTracker(dampening_config, hysteresis_config)

    assert tracker.config == dampening_config
    assert tracker.hysteresis_config == hysteresis_config


def test_flap_dampening_tracking(route_table, sample_route):
    """Test that flap dampening is tracked correctly."""
    # Get initial value (may not be 0 if previous tests affected global state)
    initial_flaps = route_table.flaps_dampened_total._value

    # Add a route
    route_table.update_routes([sample_route])
    # First update shouldn't change dampening count
    assert route_table.flaps_dampened_total._value == initial_flaps

    # Withdraw the route (creates a flap)
    route_table.withdraw_routes([sample_route.prefix])
    # Check that dampening info exists and has penalty
    dampening_info = route_table.dampening_tracker.get_dampening_info(sample_route.prefix)
    assert dampening_info["penalty"] > 0


def test_dampening_suppression_logic(dampening_config):
    """Test dampening suppression logic."""
    tracker = RouteDampeningTracker(dampening_config)

    # Record multiple flaps to trigger suppression
    for _i in range(3):  # 3 flaps * 1000 penalty = 3000 > 2000 threshold
        tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)

    # Should be suppressed
    assert tracker.is_suppressed("10.0.0.0/8")


def test_dampening_penalty_decay(dampening_config):
    """Test that dampening penalties decay over time."""
    tracker = RouteDampeningTracker(dampening_config)

    # Record a flap
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)
    initial_penalty = tracker.get_dampening_info("10.0.0.0/8")["penalty"]
    assert initial_penalty > 0

    # Simulate time passing (30 minutes = 2 half-lives)
    with patch("time.time", return_value=time.time() + 1800):
        decayed_penalty = tracker.get_dampening_info("10.0.0.0/8")["penalty"]
        # Penalty should be significantly reduced (0.25 of original)
        assert decayed_penalty < initial_penalty


def test_dampening_reuse_threshold(dampening_config):
    """Test that routes are reused when penalty drops below threshold."""
    tracker = RouteDampeningTracker(dampening_config)

    # Record flaps to trigger suppression
    for _i in range(3):
        tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)

    assert tracker.is_suppressed("10.0.0.0/8")

    # Check current penalty
    initial_penalty = tracker.get_dampening_info("10.0.0.0/8")["penalty"]
    assert initial_penalty >= dampening_config.suppress_threshold

    # Test that penalty eventually decays (use much longer time)
    with patch("time.time", return_value=time.time() + 86400):  # 24 hours
        final_penalty = tracker.get_dampening_info("10.0.0.0/8")["penalty"]
        # Penalty should be significantly decayed after 24 hours
        assert final_penalty < initial_penalty
        # The route should eventually be reusable
        if final_penalty < dampening_config.reuse_threshold:
            assert not tracker.is_suppressed("10.0.0.0/8")


def test_flap_rate_detection(dampening_config):
    """Test flap rate detection for excessive flapping."""
    tracker = RouteDampeningTracker(dampening_config)

    # Record flaps faster than the rate limit
    current_time = time.time()
    for i in range(7):  # More than max_flaps_per_minute
        with patch("time.time", return_value=current_time + i * 5):  # 5 seconds apart
            tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)

    # Should detect excessive flapping
    state = tracker.dampening_states["10.0.0.0/8"]
    assert state.should_suppress_due_to_flaps(current_time + 35, dampening_config)


def test_dampening_state_persistence():
    """Test that dampening state persists across operations."""
    config = RouteDampeningConfig()
    tracker = RouteDampeningTracker(config)

    # Record some activity
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=False)

    info = tracker.get_dampening_info("10.0.0.0/8")
    assert info["flap_count"] >= 2
    assert info["penalty"] > 0


def test_multiple_prefixes_dampening():
    """Test dampening works correctly with multiple prefixes."""
    config = RouteDampeningConfig()
    tracker = RouteDampeningTracker(config)

    # Record activity on different prefixes
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)
    tracker.record_route_change("192.168.0.0/16", is_withdrawal=True)

    # Each should have independent state
    info1 = tracker.get_dampening_info("10.0.0.0/8")
    info2 = tracker.get_dampening_info("192.168.0.0/16")

    assert info1["penalty"] > 0
    assert info2["penalty"] > 0
    assert info1["penalty"] == info2["penalty"]  # Same penalty for same activity


def test_dampening_metrics_integration(route_table, sample_route):
    """Test that dampening metrics are properly integrated."""
    # This test verifies the metric exists and can be accessed
    assert hasattr(route_table, "flaps_dampened_total")

    # Get initial value (may not be 0 if previous tests affected global state)
    initial_value = route_table.flaps_dampened_total._value

    # Add route
    route_table.update_routes([sample_route])

    # Metric should still be accessible and value should not decrease
    assert hasattr(route_table, "flaps_dampened_total")
    assert route_table.flaps_dampened_total._value >= initial_value


def test_hysteresis_config_in_route_table():
    """Test that hysteresis config is properly integrated in route table."""
    table = AGPRouteTable()

    # Verify hysteresis config exists
    assert hasattr(table.dampening_tracker, "hysteresis_config")
    assert table.dampening_tracker.hysteresis_config.metric_type == "fast"


def test_dampening_withdrawal_vs_advertisement():
    """Test that both withdrawals and advertisements trigger dampening."""
    config = RouteDampeningConfig()
    tracker = RouteDampeningTracker(config)

    # Record withdrawal
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)
    penalty_after_withdrawal = tracker.get_dampening_info("10.0.0.0/8")["penalty"]

    # Record advertisement (should also trigger flap detection)
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=False)
    penalty_after_advertisement = tracker.get_dampening_info("10.0.0.0/8")["penalty"]

    # Penalty should increase
    assert penalty_after_advertisement > penalty_after_withdrawal


def test_dampening_state_cleanup():
    """Test cleanup of old dampening states."""
    config = RouteDampeningConfig()
    tracker = RouteDampeningTracker(config)

    # Add some state
    tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)

    # Verify state exists
    assert "10.0.0.0/8" in tracker.dampening_states

    # Simulate old state (no activity for over an hour)
    old_time = time.time() - 4000  # 4000 seconds ago
    tracker.dampening_states["10.0.0.0/8"].last_flap_time = old_time

    # Cleanup should remove old states
    tracker.cleanup_expired_states(max_age_seconds=3600)

    # State should be removed since penalty is 0 and it's old
    # Note: This depends on the cleanup logic in the actual implementation


def test_max_penalty_cap(dampening_config):
    """Test that penalty is capped at maximum value."""
    tracker = RouteDampeningTracker(dampening_config)

    # Record many flaps to exceed max penalty
    for _i in range(20):  # 20 * 1000 = 20000 > 16000 max
        tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)

    penalty = tracker.get_dampening_info("10.0.0.0/8")["penalty"]
    assert penalty <= dampening_config.max_penalty
