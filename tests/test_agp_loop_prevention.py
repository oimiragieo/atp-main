"""Tests for AGP loop prevention (GAP-109A)."""

import pytest

from router_service.agp_update_handler import AGPRoute, AGPRouteAttributes, AGPRouteTable, AGPUpdateHandler


@pytest.fixture
def route_table():
    return AGPRouteTable()


@pytest.fixture
def update_handler(route_table):
    return AGPUpdateHandler(route_table, router_id="router1:cluster-a")


def test_loop_prevention_originator_id_equals_self(update_handler):
    """Test that routes with originator_id equal to self are rejected."""
    # Create a route with originator_id equal to our router_id
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        originator_id="router1:cluster-a",  # Same as our router_id
        cluster_list=["cluster-b", "cluster-c"],
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert update_handler._would_create_loop(route) is True


def test_loop_prevention_cluster_id_in_list(update_handler):
    """Test that routes with our cluster_id in cluster_list are rejected."""
    # Create a route with our cluster_id in cluster_list
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        originator_id="router2:cluster-b",
        cluster_list=["cluster-a", "cluster-b"],  # Our cluster_id "cluster-a" is in the list
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert update_handler._would_create_loop(route) is True


def test_loop_prevention_no_loop(update_handler):
    """Test that routes without loop conditions are accepted."""
    # Create a route that should not create a loop
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        originator_id="router2:cluster-b",  # Different from our router_id
        cluster_list=["cluster-b", "cluster-c"],  # Our cluster_id "cluster-a" is not in the list
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert update_handler._would_create_loop(route) is False


def test_loop_prevention_missing_attributes(update_handler):
    """Test that routes with missing loop prevention attributes are accepted."""
    # Create a route without originator_id or cluster_list
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        # No originator_id or cluster_list
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert update_handler._would_create_loop(route) is False


def test_update_handler_filters_loop_routes(update_handler):
    """Test that handle_update filters out routes that would create loops."""
    # Create an UPDATE message with mixed routes
    message = {
        "type": "UPDATE",
        "announce": [
            {
                "prefix": "192.168.1.0/24",
                "attrs": {
                    "path": [1, 2, 3],
                    "next_hop": "peer1",
                    "originator_id": "router2:cluster-b",
                    "cluster_list": ["cluster-b", "cluster-c"],
                },
            },
            {
                "prefix": "192.168.2.0/24",
                "attrs": {
                    "path": [1, 2, 4],
                    "next_hop": "peer1",
                    "originator_id": "router1:cluster-a",  # This should be filtered
                    "cluster_list": ["cluster-b", "cluster-c"],
                },
            },
            {
                "prefix": "192.168.3.0/24",
                "attrs": {
                    "path": [1, 2, 5],
                    "next_hop": "peer1",
                    "originator_id": "router3:cluster-c",
                    "cluster_list": ["cluster-a", "cluster-c"],  # This should be filtered
                },
            },
        ],
    }

    announced_routes, withdrawn_prefixes = update_handler.handle_update(message, "peer1")

    # Should have 1 route (the first one), 2 filtered out
    assert len(announced_routes) == 1
    assert announced_routes[0].prefix == "192.168.1.0/24"
    assert withdrawn_prefixes == []

    # Check that metrics were updated
    # Note: We can't easily check the counter value without mocking, but the method should have been called


def test_cluster_id_derivation_simple_router_id():
    """Test cluster_id derivation with simple router_id."""
    route_table = AGPRouteTable()
    handler = AGPUpdateHandler(route_table, router_id="router1")

    # With simple router_id, cluster_id should be the same
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        originator_id="router2",
        cluster_list=["router1"],  # Our router_id is in the list
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert handler._would_create_loop(route) is True


def test_cluster_id_derivation_complex_router_id():
    """Test cluster_id derivation with complex router_id."""
    route_table = AGPRouteTable()
    handler = AGPUpdateHandler(route_table, router_id="router1:cluster-a:zone-1")

    # With complex router_id, cluster_id should be the first part
    attrs = AGPRouteAttributes(
        path=[1, 2, 3],
        next_hop="peer1",
        originator_id="router2:cluster-b",
        cluster_list=["cluster-a"],  # Our cluster_id "cluster-a" is in the list
    )

    route = AGPRoute(prefix="192.168.1.0/24", attributes=attrs, received_at=1234567890.0, peer_router_id="peer1")

    assert handler._would_create_loop(route) is True
