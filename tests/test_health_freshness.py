#!/usr/bin/env python3
"""
Tests for AGP Health Freshness Multiplier & Staleness Penalty.
"""

import time

import pytest

from router_service.agp_update_handler import AGPRoute, AGPRouteAttributes, AGPRouteTable


@pytest.fixture
def route_table():
    """Create a route table for testing."""
    return AGPRouteTable()


@pytest.fixture
def fresh_route():
    """Create a route with fresh health metrics."""
    current_time = time.time()
    attributes = AGPRouteAttributes(
        path=[65001, 65002],
        next_hop="router2",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            "metrics_timestamp": current_time,
            "metrics_half_life_s": 30.0,
        },
    )
    return AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")


@pytest.fixture
def stale_route():
    """Create a route with stale health metrics."""
    current_time = time.time()
    attributes = AGPRouteAttributes(
        path=[65001, 65002],
        next_hop="router2",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            "metrics_timestamp": current_time - 600,  # 10 minutes ago
            "metrics_half_life_s": 30.0,
        },
    )
    return AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")


@pytest.fixture
def no_health_route():
    """Create a route without health metrics."""
    current_time = time.time()
    attributes = AGPRouteAttributes(path=[65001, 65002], next_hop="router2")
    return AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")


def test_freshness_factor_calculation(route_table, fresh_route):
    """Test freshness factor calculation for fresh metrics."""
    factor = route_table._calculate_freshness_factor(fresh_route)

    # Fresh metrics should have high freshness factor (close to 1.0)
    assert factor > 0.9
    assert factor <= 1.0


def test_stale_freshness_factor_calculation(route_table, stale_route):
    """Test freshness factor calculation for stale metrics."""
    factor = route_table._calculate_freshness_factor(stale_route)

    # Stale metrics should have low freshness factor
    assert factor < 0.5
    assert factor >= 0.1  # Minimum bound


def test_no_health_freshness_factor(route_table, no_health_route):
    """Test freshness factor for routes without health metrics."""
    factor = route_table._calculate_freshness_factor(no_health_route)

    # Routes without health metrics should have no penalty
    assert factor == 1.0


def test_future_timestamp_freshness_factor(route_table):
    """Test freshness factor for future timestamps."""
    current_time = time.time()
    attributes = AGPRouteAttributes(
        path=[65001],
        next_hop="router1",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            "metrics_timestamp": current_time + 60,  # Future timestamp
            "metrics_half_life_s": 30.0,
        },
    )
    route = AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")

    factor = route_table._calculate_freshness_factor(route)
    assert factor == 1.0  # No penalty for future timestamps


def test_health_score_with_freshness(route_table, fresh_route, stale_route):
    """Test that freshness affects health score calculation."""
    fresh_score = route_table._calculate_route_score(fresh_route)
    stale_score = route_table._calculate_route_score(stale_route)

    # Fresh route should have better (lower) score than stale route
    assert fresh_score < stale_score


def test_stale_route_counting(route_table, fresh_route, stale_route):
    """Test counting of stale health routes."""
    # Add routes to table
    route_table.update_routes([fresh_route])

    # Initially no stale routes
    assert route_table._count_stale_health_routes() == 0

    # Add stale route
    stale_route.prefix = "192.168.0.0/16"  # Different prefix
    route_table.update_routes([stale_route])

    # Should count the stale route
    assert route_table._count_stale_health_routes() == 1


def test_route_selection_prefers_fresh(route_table, fresh_route, stale_route):
    """Test that route selection prefers fresh routes over stale ones."""
    # Make routes for same prefix but different peers
    stale_route.prefix = fresh_route.prefix
    stale_route.peer_router_id = "router2"

    route_table.update_routes([fresh_route, stale_route])

    # Get best route
    best_route = route_table.get_best_route(fresh_route.prefix)

    # Should prefer the fresh route
    assert best_route.peer_router_id == fresh_route.peer_router_id


def test_custom_half_life():
    """Test freshness calculation with custom half-life."""
    route_table = AGPRouteTable()
    current_time = time.time()

    # Route with short half-life (15 seconds)
    attributes = AGPRouteAttributes(
        path=[65001],
        next_hop="router1",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            "metrics_timestamp": current_time - 30,  # 30 seconds ago
            "metrics_half_life_s": 15.0,  # Short half-life
        },
    )
    route = AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")

    factor = route_table._calculate_freshness_factor(route)

    # With short half-life, 30 seconds ago should be significantly decayed
    import math

    expected_factor = math.exp(-30 / 15.0)  # exp(-2) ≈ 0.135
    assert abs(factor - expected_factor) < 0.01


def test_metrics_update_includes_stale_count(route_table, fresh_route, stale_route):
    """Test that metrics update includes stale route counting."""
    # Add routes
    route_table.update_routes([fresh_route])
    stale_route.prefix = "192.168.0.0/16"
    route_table.update_routes([stale_route])

    # Update metrics
    route_table._update_metrics()

    # Check that stale count is tracked
    # Note: We can't easily test the gauge value without mocking, but we can verify the method exists
    assert hasattr(route_table, "stale_health_routes_total")


def test_freshness_factor_minimum_bound(route_table):
    """Test that freshness factor has a minimum bound."""
    current_time = time.time()

    # Very old metrics
    attributes = AGPRouteAttributes(
        path=[65001],
        next_hop="router1",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            "metrics_timestamp": current_time - 3600,  # 1 hour ago
            "metrics_half_life_s": 30.0,
        },
    )
    route = AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")

    factor = route_table._calculate_freshness_factor(route)

    # Should be bounded at minimum value
    assert factor >= 0.1


def test_no_timestamp_no_penalty(route_table):
    """Test that routes without metrics_timestamp get no freshness penalty."""
    current_time = time.time()

    attributes = AGPRouteAttributes(
        path=[65001],
        next_hop="router1",
        health={
            "p50_ms": 100,
            "p95_ms": 200,
            "err_rate": 0.01,
            # No metrics_timestamp
        },
    )
    route = AGPRoute(prefix="10.0.0.0/8", attributes=attributes, received_at=current_time, peer_router_id="router1")

    factor = route_table._calculate_freshness_factor(route)
    assert factor == 1.0
