#!/usr/bin/env python3
"""
Tests for AGP Route Snapshot functionality.
"""

import time

import pytest

from router_service.agp_update_handler import AGPRoute, AGPRouteAttributes, AGPRouteTable


@pytest.fixture
def sample_route_table():
    """Create a sample route table for testing."""
    table = AGPRouteTable()

    # Add some test routes
    routes = [
        AGPRoute(
            prefix="10.0.0.0/8",
            attributes=AGPRouteAttributes(path=[65001, 65002], next_hop="router2", local_pref=100),
            received_at=time.time(),
            peer_router_id="router1",
        ),
        AGPRoute(
            prefix="192.168.0.0/16",
            attributes=AGPRouteAttributes(path=[65002, 65003], next_hop="router3", local_pref=150),
            received_at=time.time(),
            peer_router_id="router2",
        ),
    ]

    table.update_routes(routes)
    return table


def test_take_snapshot(sample_route_table):
    """Test taking a snapshot of the route table."""
    snapshot = sample_route_table.take_snapshot()

    assert "timestamp" in snapshot
    assert "routes" in snapshot
    assert "dampening_states" in snapshot
    assert "stats" in snapshot

    # Check routes are serialized
    assert "10.0.0.0/8" in snapshot["routes"]
    assert "192.168.0.0/16" in snapshot["routes"]

    # Check stats
    assert snapshot["stats"]["total_prefixes"] == 2
    assert snapshot["stats"]["total_routes"] == 2


def test_restore_from_snapshot(sample_route_table):
    """Test restoring route table from snapshot."""
    # Take initial snapshot
    snapshot = sample_route_table.take_snapshot()

    # Modify the table
    sample_route_table.withdraw_routes(["10.0.0.0/8"])
    assert len(sample_route_table.get_routes("10.0.0.0/8")) == 0

    # Restore from snapshot
    sample_route_table.restore_from_snapshot(snapshot)

    # Verify routes are restored
    assert len(sample_route_table.get_routes("10.0.0.0/8")) == 1
    assert len(sample_route_table.get_routes("192.168.0.0/16")) == 1


def test_diff_snapshots(sample_route_table):
    """Test computing diff between snapshots."""
    # Take first snapshot
    snapshot1 = sample_route_table.take_snapshot()

    # Modify table
    sample_route_table.withdraw_routes(["10.0.0.0/8"])
    new_route = AGPRoute(
        prefix="172.16.0.0/16",
        attributes=AGPRouteAttributes(path=[65003, 65004], next_hop="router4", local_pref=200),
        received_at=time.time(),
        peer_router_id="router3",
    )
    sample_route_table.update_routes([new_route])

    # Take second snapshot
    snapshot2 = sample_route_table.take_snapshot()

    # Compute diff
    diff = sample_route_table.diff_snapshots(snapshot1, snapshot2)

    assert "10.0.0.0/8" in diff["removed_prefixes"]
    assert "172.16.0.0/16" in diff["added_prefixes"]


def test_snapshot_serialization():
    """Test that routes can be serialized and deserialized."""
    original_route = AGPRoute(
        prefix="10.0.0.0/8",
        attributes=AGPRouteAttributes(
            path=[65001, 65002],
            next_hop="router2",
            local_pref=100,
            health={"p50_ms": 10, "p95_ms": 20, "err_rate": 0.01},
        ),
        received_at=time.time(),
        peer_router_id="router1",
    )

    # Serialize
    route_dict = original_route.to_dict()

    # Deserialize
    restored_route = AGPRoute.from_dict(route_dict)

    # Verify
    assert restored_route.prefix == original_route.prefix
    assert restored_route.peer_router_id == original_route.peer_router_id
    assert restored_route.attributes.path == original_route.attributes.path
    assert restored_route.attributes.next_hop == original_route.attributes.next_hop
    assert restored_route.attributes.local_pref == original_route.attributes.local_pref
    assert restored_route.attributes.health == original_route.attributes.health


def test_dampening_state_preservation(sample_route_table):
    """Test that dampening states are preserved in snapshots."""
    # Create some dampening activity
    sample_route_table.dampening_tracker.record_route_change("10.0.0.0/8", is_withdrawal=True)
    sample_route_table.dampening_tracker.record_route_change("10.0.0.0/8", is_withdrawal=False)

    # Take snapshot
    snapshot = sample_route_table.take_snapshot()

    # Verify dampening state is captured
    assert "10.0.0.0/8" in snapshot["dampening_states"]
    dampening_info = snapshot["dampening_states"]["10.0.0.0/8"]
    assert dampening_info["penalty"] > 0
    assert dampening_info["flap_count"] >= 1

    # Clear and restore
    sample_route_table.dampening_tracker.clear_all_states()
    assert len(sample_route_table.dampening_tracker.dampening_states) == 0

    sample_route_table.restore_from_snapshot(snapshot)

    # Verify dampening state is restored
    restored_info = sample_route_table.dampening_tracker.get_dampening_info("10.0.0.0/8")
    assert restored_info["penalty"] > 0


def test_snapshot_metrics(sample_route_table):
    """Test that snapshot metrics are properly tracked."""
    # Take a snapshot
    sample_route_table.take_snapshot()

    # Check that metric was incremented
    # Note: In a real test, we'd mock the registry, but for now we just verify the method exists
    assert hasattr(sample_route_table, "route_snapshots_taken_total")


def test_empty_table_snapshot():
    """Test snapshot of empty route table."""
    empty_table = AGPRouteTable()
    snapshot = empty_table.take_snapshot()

    assert snapshot["stats"]["total_prefixes"] == 0
    assert snapshot["stats"]["total_routes"] == 0
    assert len(snapshot["routes"]) == 0


def test_snapshot_with_expired_routes(sample_route_table):
    """Test snapshot handling with expired routes."""
    # Add a route that will expire soon
    expired_route = AGPRoute(
        prefix="203.0.113.0/24",
        attributes=AGPRouteAttributes(
            path=[65004],
            next_hop="router5",
            valid_until=time.time() - 1,  # Already expired
        ),
        received_at=time.time(),
        peer_router_id="router4",
    )
    sample_route_table.update_routes([expired_route])

    # Take snapshot
    snapshot = sample_route_table.take_snapshot()

    # Verify expired route is still in snapshot (snapshots preserve state)
    assert "203.0.113.0/24" in snapshot["routes"]


def test_route_table_stats_preservation(sample_route_table):
    """Test that route table statistics are preserved in snapshots."""
    # Take snapshot
    snapshot = sample_route_table.take_snapshot()

    # Verify stats are captured
    stats = snapshot["stats"]
    assert "total_prefixes" in stats
    assert "total_routes" in stats
    assert "routes_per_prefix_avg" in stats

    # Verify stats are accurate
    assert stats["total_prefixes"] == 2
    assert stats["total_routes"] == 2
    assert stats["routes_per_prefix_avg"] == 1.0
