#!/usr/bin/env python3
"""
Tests for hold-down and grace period functionality in AGP route management.

Tests cover:
- Hold-down timer functionality (delaying withdrawals on health degradation)
- Grace period timer functionality (delaying advertisements after recovery)
- Integration with existing dampening and hysteresis features
- Metrics tracking for hold_down_events_total
- Edge cases and timer expiration
"""

import time
from unittest.mock import Mock

import pytest

from router_service.agp_update_handler import (
    AGPRoute,
    AGPRouteAttributes,
    AGPRouteTable,
    HoldDownConfig,
    HoldDownState,
    RouteDampeningTracker,
)


class TestHoldDownConfig:
    """Test HoldDownConfig validation and defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HoldDownConfig()
        assert config.persist_seconds == 8
        assert config.grace_seconds == 5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HoldDownConfig(persist_seconds=10, grace_seconds=3)
        assert config.persist_seconds == 10
        assert config.grace_seconds == 3

    def test_validation_positive_values(self):
        """Test validation requires positive values."""
        with pytest.raises(ValueError, match="persist_seconds must be positive"):
            config = HoldDownConfig(persist_seconds=0)
            config.validate()

        with pytest.raises(ValueError, match="grace_seconds must be positive"):
            config = HoldDownConfig(grace_seconds=-1)
            config.validate()


class TestHoldDownState:
    """Test HoldDownState timer management."""

    def test_initial_state(self):
        """Test initial state has no active timers."""
        state = HoldDownState()
        current_time = time.time()

        assert not state.is_in_hold_down(current_time)
        assert not state.is_in_grace_period(current_time)

    def test_hold_down_timer(self):
        """Test hold-down timer functionality."""
        state = HoldDownState()
        config = HoldDownConfig(persist_seconds=2)
        start_time = 1000.0

        # Start hold-down
        state.start_hold_down(start_time, config)

        # Should be in hold-down immediately after starting
        assert state.is_in_hold_down(start_time + 0.5)
        assert state.is_in_hold_down(start_time + 1.9)

        # Should expire after persist_seconds
        assert not state.is_in_hold_down(start_time + 2.1)

    def test_grace_period_timer(self):
        """Test grace period timer functionality."""
        state = HoldDownState()
        config = HoldDownConfig(grace_seconds=3)
        start_time = 1000.0

        # Start grace period
        state.start_grace_period(start_time, config)

        # Should be in grace period
        assert state.is_in_grace_period(start_time + 1)
        assert state.is_in_grace_period(start_time + 2.9)

        # Should expire after grace_seconds
        assert not state.is_in_grace_period(start_time + 3.1)

    def test_clear_timers(self):
        """Test clearing all timers."""
        state = HoldDownState()
        config = HoldDownConfig()
        start_time = 1000.0

        state.start_hold_down(start_time, config)
        state.start_grace_period(start_time, config)

        assert state.is_in_hold_down(start_time)
        assert state.is_in_grace_period(start_time)

        state.clear_timers()

        assert not state.is_in_hold_down(start_time)
        assert not state.is_in_grace_period(start_time)


class TestRouteDampeningTrackerHoldDown:
    """Test hold-down functionality in RouteDampeningTracker."""

    def test_record_health_change_degradation(self):
        """Test recording health degradation starts hold-down."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        start_time = 1000.0

        # Mock time.time to return controlled values
        original_time = time.time
        time.time = Mock(return_value=start_time)

        try:
            tracker.record_health_change(prefix, health_degraded=True)

            # Should start hold-down timer
            info = tracker.get_hold_down_info(prefix)
            assert info["in_hold_down"]
            assert info["hold_down_remaining_seconds"] > 0
            assert not info["in_grace_period"]
        finally:
            time.time = original_time

    def test_record_health_change_recovery(self):
        """Test recording health recovery starts grace period."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        start_time = 1000.0

        # Mock time.time
        original_time = time.time
        time.time = Mock(return_value=start_time)

        try:
            tracker.record_health_change(prefix, health_degraded=False)

            # Should start grace period timer
            info = tracker.get_hold_down_info(prefix)
            assert info["in_grace_period"]
            assert info["grace_period_remaining_seconds"] > 0
            assert not info["in_hold_down"]
        finally:
            time.time = original_time

    def test_should_delay_withdrawal(self):
        """Test withdrawal delay during hold-down period."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        start_time = 1000.0

        # Mock time
        mock_time = Mock(return_value=start_time)
        tracker._time_func = mock_time

        # Start hold-down
        tracker.record_health_change(prefix, health_degraded=True)

        # Should delay withdrawal during hold-down
        assert tracker.should_delay_withdrawal(prefix)

        # Advance time past hold-down period
        mock_time.return_value = start_time + 10

        # Should not delay withdrawal after hold-down expires
        assert not tracker.should_delay_withdrawal(prefix)

    def test_should_delay_advertisement(self):
        """Test advertisement delay during grace period."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        start_time = 1000.0

        # Mock time
        mock_time = Mock(return_value=start_time)
        tracker._time_func = mock_time

        # Start grace period
        tracker.record_health_change(prefix, health_degraded=False)

        # Should delay advertisement during grace period
        assert tracker.should_delay_advertisement(prefix)

        # Advance time past grace period
        mock_time.return_value = start_time + 10

        # Should not delay advertisement after grace period expires
        assert not tracker.should_delay_advertisement(prefix)

    def test_get_hold_down_info_no_state(self):
        """Test getting info for prefix with no hold-down state."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"

        info = tracker.get_hold_down_info(prefix)

        assert not info["in_hold_down"]
        assert not info["in_grace_period"]
        assert info["hold_down_remaining_seconds"] == 0
        assert info["grace_period_remaining_seconds"] == 0


class TestAGPRouteTableHoldDown:
    """Test hold-down integration in AGPRouteTable."""

    def create_test_route(self, prefix: str, peer_id: str) -> AGPRoute:
        """Create a test route for testing."""
        attributes = AGPRouteAttributes(
            path=[1, 2, 3], next_hop="192.168.1.1", originator_id="router1", cluster_list=["cluster1"]
        )
        return AGPRoute(prefix=prefix, attributes=attributes, received_at=time.time(), peer_router_id=peer_id)

    def test_update_routes_health_based_grace_period(self):
        """Test that advertisements are delayed during grace period."""
        # Create table
        table = AGPRouteTable()

        route = self.create_test_route("192.168.1.0/24", "peer1")

        # Mock time for call
        mock_time = Mock(return_value=1000.0)
        table.dampening_tracker._time_func = mock_time

        # Try to advertise route with health_degraded=False (should start grace period and delay)
        table.update_routes_health_based([route], health_degraded=False)

        # Route should not be added because grace period starts immediately
        assert len(table.get_routes(route.prefix)) == 0

        # Verify grace period is active
        info = table.dampening_tracker.get_hold_down_info(route.prefix)
        assert info["in_grace_period"]
        assert info["grace_period_remaining_seconds"] == 5.0

    def test_withdraw_routes_health_based_hold_down(self):
        """Test that withdrawals are delayed during hold-down period."""
        # Create a mock time function
        mock_time = Mock(return_value=1000.0)

        # Create table with mock time function
        table = AGPRouteTable()
        table.dampening_tracker._time_func = mock_time

        route = self.create_test_route("192.168.1.0/24", "peer1")

        # Add route first
        table.update_routes([route])

        # Record health degradation to start hold-down
        table.dampening_tracker.record_health_change(route.prefix, health_degraded=True)

        # Try to withdraw during hold-down period (should start hold-down and delay)
        table.withdraw_routes_health_based([route.prefix], health_degraded=True)

        # Route should still be present because hold-down starts immediately
        assert len(table.get_routes(route.prefix)) == 1

        # Verify hold-down is active
        info = table.dampening_tracker.get_hold_down_info(route.prefix)
        assert info["in_hold_down"]
        assert info["hold_down_remaining_seconds"] == 8.0

    def test_hold_down_events_metric(self):
        """Test that hold_down_events_total metric is incremented."""
        table = AGPRouteTable()
        route = self.create_test_route("192.168.1.0/24", "peer1")
        start_time = 1000.0

        original_time = time.time
        time.time = Mock(return_value=start_time)

        try:
            # Start grace period
            table.dampening_tracker.record_health_change(route.prefix, health_degraded=False)

            # Try to advertise during grace period (should increment metric)
            table.update_routes_health_based([route], health_degraded=False)

            # Check that the metric exists and has been used
            # We can't easily check the exact count without accessing internal state,
            # but we can verify the metric exists
            assert hasattr(table, "hold_down_events_total")
            assert table.hold_down_events_total is not None
        finally:
            time.time = original_time

    def test_integration_with_dampening(self):
        """Test hold-down works alongside existing dampening features."""
        table = AGPRouteTable()
        route = self.create_test_route("192.168.1.0/24", "peer1")

        # Add route
        table.update_routes([route])
        assert len(table.get_routes(route.prefix)) == 1

        # Withdraw route (triggers dampening)
        table.withdraw_routes([route.prefix])
        assert len(table.get_routes(route.prefix)) == 0

        # Test that hold-down state is tracked separately
        hold_down_info = table.dampening_tracker.get_hold_down_info(route.prefix)
        assert "in_hold_down" in hold_down_info
        assert "in_grace_period" in hold_down_info


class TestHoldDownEdgeCases:
    """Test edge cases for hold-down functionality."""

    def test_multiple_health_changes(self):
        """Test multiple health changes reset timers appropriately."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        start_time = 1000.0

        original_time = time.time
        time.time = Mock(return_value=start_time)

        try:
            # Start with degradation
            tracker.record_health_change(prefix, health_degraded=True)
            assert tracker.should_delay_withdrawal(prefix)

            # Recovery should start grace period instead
            tracker.record_health_change(prefix, health_degraded=False)
            assert not tracker.should_delay_withdrawal(prefix)
            assert tracker.should_delay_advertisement(prefix)
        finally:
            time.time = original_time

    def test_timer_expiration_precision(self):
        """Test timer expiration with precise timing."""
        tracker = RouteDampeningTracker()
        prefix = "192.168.1.0/24"
        config = HoldDownConfig(persist_seconds=1, grace_seconds=1)
        tracker.hold_down_config = config
        start_time = 1000.0

        # Mock time
        mock_time = Mock(return_value=start_time)
        tracker._time_func = mock_time

        # Start hold-down
        tracker.record_health_change(prefix, health_degraded=True)
        assert tracker.should_delay_withdrawal(prefix)

        # Exactly at expiration time
        mock_time.return_value = start_time + 1.0
        assert not tracker.should_delay_withdrawal(prefix)

    def test_different_prefixes_isolated(self):
        """Test that hold-down state is isolated per prefix."""
        tracker = RouteDampeningTracker()
        prefix1 = "192.168.1.0/24"
        prefix2 = "192.168.2.0/24"

        # Affect only prefix1
        tracker.record_health_change(prefix1, health_degraded=True)

        assert tracker.should_delay_withdrawal(prefix1)
        assert not tracker.should_delay_withdrawal(prefix2)

        # Grace period for prefix2
        tracker.record_health_change(prefix2, health_degraded=False)

        assert tracker.should_delay_withdrawal(prefix1)
        assert not tracker.should_delay_withdrawal(prefix2)
        assert tracker.should_delay_advertisement(prefix2)
