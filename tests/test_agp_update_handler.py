#!/usr/bin/env python3
"""
Tests for AGP UPDATE Message Handling and Route Management
"""

import time

import pytest

from router_service.agp_update_handler import (
    AGPRoute,
    AGPRouteAttributes,
    AGPRouteTable,
    AGPUpdateHandler,
    AGPUpdateMessage,
    DampeningState,
    EWMASmoother,
    HealthMetricsProcessor,
    HysteresisConfig,
    ParallelSession,
    ParallelSessionConfig,
    ParallelSessionManager,
    ParallelSessionState,
    RouteDampeningConfig,
    RouteDampeningTracker,
    RouteSelectionConfig,
    ValidationError,
)
from router_service.control_status import GLOBAL_AGENT_STATUS, Status
from router_service.frame import DispatchPayload, EndPayload, StreamPayload


class TestAGPRouteAttributes:
    """Test cases for AGP route attributes."""

    def test_valid_attributes(self):
        """Test valid route attributes."""
        attrs = AGPRouteAttributes(
            path=[64512, 65001],
            next_hop="router-2",
            local_pref=200,
            med=50,
            qos_supported=["gold", "silver"],
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
            health={"p50_ms": 800, "p95_ms": 1400, "err_rate": 0.015},
            cost={"usd_per_1k_tokens": 0.004},
            predictability={"estimate_mape_7d": 0.12, "under_rate_7d": 0.07},
            communities=["no-export?false", "region:us-east"],
            security_groups=["sandboxed-fs"],
            regions=["us-east-1"],
            valid_until=time.time() + 3600,
        )
        attrs.validate()  # Should not raise

    def test_invalid_path_empty(self):
        """Test validation fails with empty path."""
        attrs = AGPRouteAttributes(path=[], next_hop="router-2")
        with pytest.raises(ValidationError, match="Path cannot be empty"):
            attrs.validate()

    def test_invalid_path_adn(self):
        """Test validation fails with invalid ADN."""
        attrs = AGPRouteAttributes(path=[64512, -1], next_hop="router-2")
        with pytest.raises(ValidationError, match="Invalid ADN in path"):
            attrs.validate()

    def test_invalid_local_pref(self):
        """Test validation fails with invalid local_pref."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2", local_pref=-1)
        with pytest.raises(ValidationError, match="Invalid local_pref"):
            attrs.validate()

    def test_invalid_med(self):
        """Test validation fails with invalid MED."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2", med=-1)
        with pytest.raises(ValidationError, match="Invalid MED"):
            attrs.validate()

    def test_invalid_qos_tier(self):
        """Test validation fails with invalid QoS tier."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2", qos_supported=["invalid"])
        with pytest.raises(ValidationError, match="Invalid QoS tier"):
            attrs.validate()

    def test_qos_fit_validation_insufficient(self):
        """Test validation fails with insufficient QoS support."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            qos_supported=["bronze"],  # Only bronze, but we require at least silver
        )
        with pytest.raises(ValidationError, match="Route must support at least silver QoS"):
            attrs.validate()

    def test_qos_fit_validation_sufficient(self):
        """Test validation passes with sufficient QoS support."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            qos_supported=["gold", "silver"],  # Has silver and gold
        )
        attrs.validate()  # Should not raise

    def test_no_export_community_handling(self):
        """Test that no-export community routes are rejected per policy."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2", communities=["no-export", "region:us-east"])
        # No-export routes should be rejected per AGP Federation Spec
        with pytest.raises(ValidationError, match="no-export routes not accepted"):
            attrs.validate()

    def test_invalid_capacity_missing_fields(self):
        """Test validation fails with incomplete capacity."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128},  # Missing required fields
        )
        with pytest.raises(ValidationError, match="Capacity missing required fields"):
            attrs.validate()

    def test_invalid_health_missing_fields(self):
        """Test validation fails with incomplete health."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            health={"p50_ms": 800},  # Missing required fields
        )
        with pytest.raises(ValidationError, match="Health missing required fields"):
            attrs.validate()

    def test_invalid_cost_missing_fields(self):
        """Test validation fails with incomplete cost."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            cost={},  # Missing required fields
        )
        with pytest.raises(ValidationError, match="Cost missing usd_per_1k_tokens"):
            attrs.validate()

    def test_invalid_predictability_missing_fields(self):
        """Test validation fails with incomplete predictability."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            predictability={"estimate_mape_7d": 0.12},  # Missing required fields
        )
        with pytest.raises(ValidationError, match="Predictability missing required fields"):
            attrs.validate()

    def test_expired_route(self):
        """Test expired route detection."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            valid_until=time.time() - 1,  # Already expired
        )
        assert attrs.is_expired()

    def test_valid_route_not_expired(self):
        """Test valid route is not expired."""
        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            valid_until=time.time() + 3600,  # Future expiry
        )
        assert not attrs.is_expired()


class TestAGPRoute:
    """Test cases for AGP routes."""

    def test_valid_route_creation(self):
        """Test creating a valid route."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")
        assert route.prefix == "reviewer.*"
        assert route.is_valid()

    def test_invalid_route_creation(self):
        """Test route creation fails with invalid attributes."""
        attrs = AGPRouteAttributes(path=[], next_hop="router-2")  # Invalid: empty path
        with pytest.raises(ValidationError):
            AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")


class TestAGPUpdateMessage:
    """Test cases for AGP UPDATE messages."""

    def test_valid_update_message(self):
        """Test valid UPDATE message."""
        msg = AGPUpdateMessage(
            announce=[{"prefix": "reviewer.*", "attrs": {"path": [64512], "next_hop": "router-2"}}],
            withdraw=["summarizer.eu.*"],
        )
        msg.validate()  # Should not raise

    def test_invalid_message_type(self):
        """Test validation fails with invalid message type."""
        msg = AGPUpdateMessage(type="INVALID")
        with pytest.raises(ValidationError, match="Invalid message type"):
            msg.validate()

    def test_empty_update_message(self):
        """Test validation fails with empty UPDATE message."""
        msg = AGPUpdateMessage()
        with pytest.raises(ValidationError, match="UPDATE message must have announce or withdraw"):
            msg.validate()

    def test_invalid_announce_missing_prefix(self):
        """Test validation fails with announce missing prefix."""
        msg = AGPUpdateMessage(
            announce=[
                {
                    "attrs": {"path": [64512], "next_hop": "router-2"}
                    # Missing "prefix"
                }
            ]
        )
        with pytest.raises(ValidationError, match="Announce missing prefix or attrs"):
            msg.validate()

    def test_invalid_announce_missing_attrs(self):
        """Test validation fails with announce missing attrs."""
        msg = AGPUpdateMessage(
            announce=[
                {
                    "prefix": "reviewer.*"
                    # Missing "attrs"
                }
            ]
        )
        with pytest.raises(ValidationError, match="Announce missing prefix or attrs"):
            msg.validate()

    def test_invalid_announce_missing_path(self):
        """Test validation fails with announce missing path."""
        msg = AGPUpdateMessage(
            announce=[
                {
                    "prefix": "reviewer.*",
                    "attrs": {
                        "next_hop": "router-2"
                        # Missing "path"
                    },
                }
            ]
        )
        with pytest.raises(ValidationError, match="Route attrs missing path or next_hop"):
            msg.validate()

    def test_parse_routes_success(self):
        """Test successful route parsing."""
        msg = AGPUpdateMessage(
            announce=[
                {"prefix": "reviewer.*", "attrs": {"path": [64512, 65001], "next_hop": "router-2", "local_pref": 200}}
            ],
            withdraw=["summarizer.eu.*"],
        )

        routes, withdrawn = msg.parse_routes("router-1")

        assert len(routes) == 1
        assert routes[0].prefix == "reviewer.*"
        assert routes[0].attributes.path == [64512, 65001]
        assert routes[0].attributes.next_hop == "router-2"
        assert routes[0].attributes.local_pref == 200
        assert withdrawn == ["summarizer.eu.*"]

    def test_parse_routes_with_invalid_route(self):
        """Test route parsing handles invalid routes gracefully."""
        msg = AGPUpdateMessage(
            announce=[
                {"prefix": "reviewer.*", "attrs": {"path": [64512], "next_hop": "router-2"}},
                {
                    "prefix": "invalid.*",
                    "attrs": {
                        "path": [],  # Invalid: empty path
                        "next_hop": "router-3",
                    },
                },
            ]
        )

        routes, withdrawn = msg.parse_routes("router-1")

        # Should still parse the valid route
        assert len(routes) == 1
        assert routes[0].prefix == "reviewer.*"


class TestAGPRouteTable:
    """Test cases for AGP route table."""

    def setup_method(self):
        """Set up test fixtures."""
        self.table = AGPRouteTable()

    def test_update_routes(self):
        """Test updating routes in the table."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        routes = self.table.get_routes("reviewer.*")
        assert len(routes) == 1
        assert routes[0].prefix == "reviewer.*"

    def test_withdraw_routes_specific_peer(self):
        """Test withdrawing routes for specific peer."""
        # Add routes from two peers
        attrs1 = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route1 = AGPRoute(prefix="reviewer.*", attributes=attrs1, received_at=time.time(), peer_router_id="router-1")

        attrs2 = AGPRouteAttributes(path=[65001], next_hop="router-3")
        route2 = AGPRoute(prefix="reviewer.*", attributes=attrs2, received_at=time.time(), peer_router_id="router-2")

        self.table.update_routes([route1, route2])

        # Withdraw from specific peer
        self.table.withdraw_routes(["reviewer.*"], "router-1")

        routes = self.table.get_routes("reviewer.*")
        assert len(routes) == 1
        assert routes[0].peer_router_id == "router-2"

    def test_withdraw_routes_all_peers(self):
        """Test withdrawing routes from all peers."""
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        # Withdraw from all peers
        self.table.withdraw_routes(["reviewer.*"])

        routes = self.table.get_routes("reviewer.*")
        assert len(routes) == 0

    def test_get_best_route(self):
        """Test getting best route using selection algorithm."""
        # Create routes with different preferences
        attrs1 = AGPRouteAttributes(path=[64512], next_hop="router-2", med=100, local_pref=100)
        route1 = AGPRoute(prefix="reviewer.*", attributes=attrs1, received_at=time.time(), peer_router_id="router-1")

        attrs2 = AGPRouteAttributes(path=[65001], next_hop="router-3", med=50, local_pref=200)
        route2 = AGPRoute(prefix="reviewer.*", attributes=attrs2, received_at=time.time(), peer_router_id="router-2")

        self.table.update_routes([route1, route2])

        best = self.table.get_best_route("reviewer.*")
        assert best is not None
        assert best.peer_router_id == "router-2"  # Should prefer lower MED

    def test_cleanup_expired_routes(self):
        """Test cleanup of expired routes."""
        # Create expired route
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2", valid_until=time.time() - 1)
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        removed = self.table.cleanup_expired()
        assert removed == 1

        routes = self.table.get_routes("reviewer.*")
        assert len(routes) == 0

    def test_get_stats(self):
        """Test route table statistics."""
        # Add some routes
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route1 = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")
        route2 = AGPRoute(prefix="summarizer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route1, route2])

        stats = self.table.get_stats()
        assert stats["total_prefixes"] == 2
        assert stats["total_routes"] == 2

    def test_backpressure_capacity_reduction_no_backpressure(self):
        """Test that capacity is not reduced when no backpressure is active."""
        # Clear any existing sessions and ensure no backpressure (all agents READY)
        GLOBAL_AGENT_STATUS._by_session.clear()
        GLOBAL_AGENT_STATUS.set_status("session1", Status.READY)
        GLOBAL_AGENT_STATUS.set_status("session2", Status.READY)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        stored_route = self.table.get_routes("reviewer.*")[0]
        assert stored_route.attributes.capacity["max_parallel"] == 128
        assert stored_route.attributes.capacity["tokens_per_s"] == 2000000
        assert stored_route.attributes.capacity["usd_per_s"] == 10.0

    def test_backpressure_capacity_reduction_partial_backpressure(self):
        """Test capacity reduction with partial backpressure (50% BUSY)."""
        # Set up partial backpressure (1 READY, 1 BUSY)
        GLOBAL_AGENT_STATUS.set_status("session1", Status.READY)
        GLOBAL_AGENT_STATUS.set_status("session2", Status.BUSY)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        stored_route = self.table.get_routes("reviewer.*")[0]
        # 50% reduction factor should result in 50% capacity
        assert stored_route.attributes.capacity["max_parallel"] == 64
        assert stored_route.attributes.capacity["tokens_per_s"] == 1000000
        assert stored_route.attributes.capacity["usd_per_s"] == 5.0

    def test_backpressure_capacity_reduction_full_backpressure(self):
        """Test capacity reduction with full backpressure (all BUSY/PAUSE)."""
        # Set up full backpressure (all BUSY)
        GLOBAL_AGENT_STATUS.set_status("session1", Status.BUSY)
        GLOBAL_AGENT_STATUS.set_status("session2", Status.PAUSE)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        stored_route = self.table.get_routes("reviewer.*")[0]
        # 0% reduction factor should result in 0 capacity
        assert stored_route.attributes.capacity["max_parallel"] == 0
        assert stored_route.attributes.capacity["tokens_per_s"] == 0
        assert stored_route.attributes.capacity["usd_per_s"] == 0.0

    def test_backpressure_capacity_reduction_health_based_update(self):
        """Test capacity reduction in health-based route updates."""
        # Set up backpressure
        GLOBAL_AGENT_STATUS.set_status("session1", Status.BUSY)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes_health_based([route], health_degraded=True)

        stored_route = self.table.get_routes("reviewer.*")[0]
        # Should be reduced due to backpressure
        assert stored_route.attributes.capacity["max_parallel"] == 0
        assert stored_route.attributes.capacity["tokens_per_s"] == 0
        assert stored_route.attributes.capacity["usd_per_s"] == 0.0

    def test_backpressure_metrics_tracking(self):
        """Test that backpressure capacity reductions are tracked in metrics."""
        # Set up backpressure
        GLOBAL_AGENT_STATUS.set_status("session1", Status.BUSY)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            capacity={"max_parallel": 128, "tokens_per_s": 2000000, "usd_per_s": 10.0},
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        initial_count = self.table.backpressure_capacity_reductions_total._value
        self.table.update_routes([route])

        # Metric should be incremented
        assert self.table.backpressure_capacity_reductions_total._value == initial_count + 1

    def test_backpressure_no_capacity_field(self):
        """Test that routes without capacity are not affected by backpressure."""
        # Set up backpressure
        GLOBAL_AGENT_STATUS.set_status("session1", Status.BUSY)

        attrs = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            # No capacity field
        )
        route = AGPRoute(prefix="reviewer.*", attributes=attrs, received_at=time.time(), peer_router_id="router-1")

        self.table.update_routes([route])

        stored_route = self.table.get_routes("reviewer.*")[0]
        assert stored_route.attributes.capacity is None


class TestAGPUpdateHandler:
    """Test cases for AGP UPDATE handler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.route_table = AGPRouteTable()
        self.handler = AGPUpdateHandler(self.route_table, "test-router")

    def test_handle_valid_update(self):
        """Test handling valid UPDATE message."""
        message = {
            "type": "UPDATE",
            "announce": [{"prefix": "reviewer.*", "attrs": {"path": [64512], "next_hop": "router-2"}}],
            "withdraw": ["summarizer.eu.*"],
        }

        routes, withdrawn = self.handler.handle_update(message, "router-1")

        assert len(routes) == 1
        assert routes[0].prefix == "reviewer.*"
        assert withdrawn == ["summarizer.eu.*"]

    def test_handle_invalid_update(self):
        """Test handling invalid UPDATE message."""
        message = {
            "type": "UPDATE"
            # Missing both announce and withdraw
        }

        with pytest.raises(ValidationError, match="UPDATE message must have announce or withdraw"):
            self.handler.handle_update(message, "router-1")

    def test_policy_enforcement_qos_fit_rejection(self):
        """Test that routes with insufficient QoS are rejected."""
        message = {
            "type": "UPDATE",
            "announce": [
                {
                    "prefix": "reviewer.*",
                    "attrs": {
                        "path": [64512],
                        "next_hop": "router-2",
                        "qos_supported": ["bronze"],  # Insufficient QoS
                    },
                }
            ],
        }

        routes, withdrawn = self.handler.handle_update(message, "router-1")

        # Route should be rejected due to insufficient QoS
        assert len(routes) == 0
        assert self.route_table.qos_fit_rejections_total._value == 1

    def test_policy_enforcement_no_export_filtering(self):
        """Test that no-export community routes are filtered."""
        message = {
            "type": "UPDATE",
            "announce": [
                {
                    "prefix": "reviewer.*",
                    "attrs": {"path": [64512], "next_hop": "router-2", "communities": ["no-export"]},
                }
            ],
        }

        routes, withdrawn = self.handler.handle_update(message, "router-1")

        # Route should be filtered due to no-export community
        assert len(routes) == 0
        assert self.route_table.no_export_filtered_total._value == 1

    def test_policy_enforcement_valid_route_accepted(self):
        """Test that valid routes with sufficient QoS are accepted."""
        message = {
            "type": "UPDATE",
            "announce": [
                {
                    "prefix": "reviewer.*",
                    "attrs": {"path": [64512], "next_hop": "router-2", "qos_supported": ["gold", "silver"]},
                }
            ],
        }

        routes, withdrawn = self.handler.handle_update(message, "router-1")

        # Route should be accepted
        assert len(routes) == 1
        assert routes[0].prefix == "reviewer.*"


class TestRouteSelectionConfig:
    """Test cases for route selection configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RouteSelectionConfig()
        assert config.local_pref_weight == 0.25
        assert config.path_len_weight == 0.15
        assert config.health_weight == 0.15
        assert config.cost_weight == 0.15
        assert config.predict_weight == 0.10
        assert config.qos_fit_weight == 0.05
        assert config.enable_ecmp is True
        assert config.max_ecmp_paths == 8

    def test_config_validation_valid(self):
        """Test validation of valid configuration."""
        config = RouteSelectionConfig()
        config.validate()  # Should not raise

    def test_config_validation_invalid_weights(self):
        """Test validation fails with invalid weights."""
        config = RouteSelectionConfig(local_pref_weight=-0.1)
        with pytest.raises(ValueError, match="All weights must be between 0 and 1"):
            config.validate()

    def test_config_validation_weights_sum(self):
        """Test validation fails when weights don't sum to 1."""
        config = RouteSelectionConfig(local_pref_weight=0.5, path_len_weight=0.6)
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            config.validate()

    def test_config_validation_max_ecmp_paths(self):
        """Test validation fails with invalid max_ecmp_paths."""
        config = RouteSelectionConfig(max_ecmp_paths=0)
        with pytest.raises(ValueError, match="max_ecmp_paths must be at least 1"):
            config.validate()


class TestRouteSelectionAlgorithm:
    """Test cases for enhanced route selection algorithm."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = RouteSelectionConfig()
        self.table = AGPRouteTable(self.config)

    def test_weighted_route_selection(self):
        """Test route selection with weighted algorithm."""
        # Create routes with different attributes
        attrs1 = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            local_pref=200,
            med=50,
            health={"p50_ms": 400, "p95_ms": 800, "err_rate": 0.01},
        )
        route1 = AGPRoute("test.*", attrs1, time.time(), "router-1")

        attrs2 = AGPRouteAttributes(
            path=[64512, 65001],
            next_hop="router-3",
            local_pref=100,
            med=100,
            health={"p50_ms": 600, "p95_ms": 1200, "err_rate": 0.05},
        )
        route2 = AGPRoute("test.*", attrs2, time.time(), "router-2")

        self.table.update_routes([route1, route2])

        best = self.table.get_best_route("test.*")
        assert best is not None
        assert best.peer_router_id == "router-1"  # Should prefer higher local_pref

    def test_ecmp_route_selection(self):
        """Test ECMP route selection."""
        # Create routes with equal scores
        attrs1 = AGPRouteAttributes(path=[64512], next_hop="router-2", local_pref=100)
        route1 = AGPRoute("test.*", attrs1, time.time(), "router-1")

        attrs2 = AGPRouteAttributes(path=[64512], next_hop="router-3", local_pref=100)
        route2 = AGPRoute("test.*", attrs2, time.time(), "router-2")

        attrs3 = AGPRouteAttributes(path=[64512], next_hop="router-4", local_pref=100)
        route3 = AGPRoute("test.*", attrs3, time.time(), "router-3")

        self.table.update_routes([route1, route2, route3])

        ecmp_routes = self.table.get_ecmp_routes("test.*")
        assert len(ecmp_routes) == 3  # All have equal scores

    def test_ecmp_with_qqos_filter(self):
        """Test ECMP with QoS filtering."""
        # Create routes with different QoS support
        attrs1 = AGPRouteAttributes(path=[64512], next_hop="router-2", qos_supported=["gold", "silver"])
        route1 = AGPRoute("test.*", attrs1, time.time(), "router-1")

        attrs2 = AGPRouteAttributes(
            path=[64512],
            next_hop="router-3",
            qos_supported=["silver"],  # Updated to silver to meet policy requirements
        )
        route2 = AGPRoute("test.*", attrs2, time.time(), "router-2")

        self.table.update_routes([route1, route2])

        # Request gold QoS
        ecmp_routes = self.table.get_ecmp_routes("test.*", "gold")
        assert len(ecmp_routes) == 1
        assert ecmp_routes[0].peer_router_id == "router-1"

    def test_ecmp_hashing_consistency(self):
        """Test ECMP hashing provides consistent results."""
        # Create multiple equal routes
        routes = []
        for i in range(3):
            attrs = AGPRouteAttributes(path=[64512], next_hop=f"router-{i}", local_pref=100)
            route = AGPRoute("test.*", attrs, time.time(), f"router-{i}")
            routes.append(route)

        self.table.update_routes(routes)

        # Same session should always get same route
        session_id = "session-123"
        route1 = self.table.select_route_with_ecmp("test.*", session_id)
        route2 = self.table.select_route_with_ecmp("test.*", session_id)

        assert route1 is not None
        assert route2 is not None
        assert route1.peer_router_id == route2.peer_router_id

    def test_ecmp_max_paths_limit(self):
        """Test ECMP respects max_ecmp_paths limit."""
        config = RouteSelectionConfig(max_ecmp_paths=2)
        table = AGPRouteTable(config)

        # Create more routes than max_ecmp_paths
        routes = []
        for i in range(5):
            attrs = AGPRouteAttributes(path=[64512], next_hop=f"router-{i}", local_pref=100)
            route = AGPRoute("test.*", attrs, time.time(), f"router-{i}")
            routes.append(route)

        table.update_routes(routes)

        ecmp_routes = table.get_ecmp_routes("test.*")
        assert len(ecmp_routes) == 2  # Limited by max_ecmp_paths

    def test_route_scoring_calculation(self):
        """Test route scoring calculation."""
        # Test scoring with various attributes
        attrs = AGPRouteAttributes(
            path=[64512, 65001, 65100],  # Path length 3
            next_hop="router-2",
            local_pref=200,  # High preference
            health={"p50_ms": 300, "p95_ms": 500, "err_rate": 0.02},  # Good health
            cost={"usd_per_1k_tokens": 0.005},  # Low cost
            predictability={"estimate_mape_7d": 0.1, "under_rate_7d": 0.05},  # Good predictability
        )

        score = self.table._calculate_route_score(AGPRoute("test.*", attrs, time.time(), "router-1"))

        # Score should be a finite float
        assert isinstance(score, float)
        assert score >= 0

        # Test with minimal attributes
        min_attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        min_score = self.table._calculate_route_score(AGPRoute("test.*", min_attrs, time.time(), "router-1"))

        assert isinstance(min_score, float)
        assert min_score >= 0

    def test_overhead_penalty_integration(self):
        """Test that overhead calibration penalty influences route selection (GAP-109C)."""
        # Create route with good overhead telemetry
        attrs1 = AGPRouteAttributes(
            path=[64512],
            next_hop="router-2",
            local_pref=100,
            overhead={"overhead_mape_7d": 0.05, "overhead_p95_factor": 1.02},  # Good prediction
        )
        route1 = AGPRoute("test.*", attrs1, time.time(), "router-1")

        # Create route with poor overhead telemetry
        attrs2 = AGPRouteAttributes(
            path=[64512],
            next_hop="router-3",
            local_pref=100,
            overhead={"overhead_mape_7d": 0.30, "overhead_p95_factor": 1.50},  # Poor prediction
        )
        route2 = AGPRoute("test.*", attrs2, time.time(), "router-2")

        self.table.update_routes([route1, route2])

        best = self.table.get_best_route("test.*")
        assert best is not None
        assert best.peer_router_id == "router-1"  # Should prefer route with better overhead prediction

    def test_disabled_ecmp(self):
        """Test behavior when ECMP is disabled."""
        config = RouteSelectionConfig(enable_ecmp=False)
        table = AGPRouteTable(config)

        # Create multiple equal routes
        routes = []
        for i in range(3):
            attrs = AGPRouteAttributes(path=[64512], next_hop=f"router-{i}", local_pref=100)
            route = AGPRoute("test.*", attrs, time.time(), f"router-{i}")
            routes.append(route)

        table.update_routes(routes)

        # Should still return all routes for ECMP consideration
        ecmp_routes = table.get_ecmp_routes("test.*")
        assert len(ecmp_routes) == 3

        # But select_route_with_ecmp should still work
        selected = table.select_route_with_ecmp("test.*", "session-123")
        assert selected is not None

        # But select_route_with_ecmp should still work
        selected = table.select_route_with_ecmp("test.*", "session-123")
        assert selected is not None


class TestRouteDampeningConfig:
    """Test cases for route dampening configuration."""

    def test_default_config(self):
        """Test default dampening configuration values."""
        config = RouteDampeningConfig()
        assert config.penalty_per_flap == 1000
        assert config.suppress_threshold == 2000
        assert config.reuse_threshold == 750
        assert config.max_penalty == 16000
        assert config.half_life_minutes == 15
        assert config.max_flaps_per_minute == 6

    def test_config_validation_valid(self):
        """Test validation of valid dampening configuration."""
        config = RouteDampeningConfig()
        config.validate()  # Should not raise

    def test_config_validation_invalid_penalty(self):
        """Test validation fails with invalid penalty_per_flap."""
        config = RouteDampeningConfig(penalty_per_flap=0)
        with pytest.raises(ValueError, match="penalty_per_flap must be positive"):
            config.validate()

    def test_config_validation_invalid_thresholds(self):
        """Test validation fails with invalid thresholds."""
        config = RouteDampeningConfig(suppress_threshold=-1)
        with pytest.raises(ValueError, match="suppress_threshold must be positive"):
            config.validate()


class TestDampeningState:
    """Test cases for dampening state tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = RouteDampeningConfig()

    def test_initial_state(self):
        """Test initial dampening state."""
        state = DampeningState()
        assert state.penalty == 0
        assert state.last_flap_time == 0.0
        assert state.flap_count == 0
        assert state.suppressed is False

    def test_record_flap(self):
        """Test recording route flaps."""
        state = DampeningState()
        current_time = time.time()

        # First flap
        state.record_flap(current_time, self.config)
        assert state.penalty == 1000
        assert state.flap_count == 1
        assert not state.suppressed

        # Second flap
        state.record_flap(current_time + 1, self.config)
        assert state.penalty == 2000
        assert state.flap_count == 2
        assert state.suppressed  # Should be suppressed at threshold

    def test_penalty_decay(self):
        """Test penalty decay over time."""
        state = DampeningState()
        current_time = time.time()

        # Record a flap
        state.record_flap(current_time, self.config)
        assert state.penalty == 1000

        # Decay after half life (15 minutes)
        decay_time = current_time + (15 * 60)
        state.decay_penalty(decay_time, self.config)
        assert state.penalty == 500  # Should be half

    def test_suppression_and_reuse(self):
        """Test suppression and reuse thresholds."""
        state = DampeningState()
        current_time = time.time()

        # Build up penalty to suppression
        for i in range(3):
            state.record_flap(current_time + i, self.config)

        assert state.suppressed
        assert state.penalty >= self.config.suppress_threshold

        # Decay penalty below reuse threshold
        decay_time = current_time + (45 * 60)  # 45 minutes, even further beyond half-life
        state.decay_penalty(decay_time, self.config)

        # Should be unsuppressed when penalty drops below reuse threshold
        assert state.penalty < self.config.reuse_threshold
        assert not state.suppressed

    def test_max_penalty_cap(self):
        """Test maximum penalty cap."""
        state = DampeningState()
        current_time = time.time()

        # Record many flaps to exceed max penalty
        for i in range(20):
            state.record_flap(current_time + i, self.config)

        assert state.penalty == self.config.max_penalty

    def test_flap_rate_detection(self):
        """Test flap rate detection for suppression."""
        state = DampeningState()
        current_time = time.time()

        # Record flaps within one minute to trigger rate-based suppression
        for i in range(7):  # More than max_flaps_per_minute
            state.record_flap(current_time + i, self.config)

        # Check immediately after the flaps (within the same minute)
        assert state.should_suppress_due_to_flaps(current_time + 10, self.config)


class TestRouteDampeningTracker:
    """Test cases for route dampening tracker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = RouteDampeningConfig()
        self.tracker = RouteDampeningTracker(self.config)

    def test_initial_state_no_suppression(self):
        """Test that new prefixes are not suppressed."""
        assert not self.tracker.is_suppressed("test.*")
        assert not self.tracker.should_suppress_due_to_flaps("test.*")

    def test_record_advertisement(self):
        """Test recording route advertisements."""
        self.tracker.record_route_change("test.*", is_withdrawal=False)

        # Should not be suppressed after first advertisement
        assert not self.tracker.is_suppressed("test.*")

    def test_record_withdrawal_creates_flap(self):
        """Test that withdrawal after advertisement creates a flap."""
        # First advertisement
        self.tracker.record_route_change("test.*", is_withdrawal=False)

        # Then withdrawal - this should create a flap
        self.tracker.record_route_change("test.*", is_withdrawal=True)

        # Should have penalty now
        info = self.tracker.get_dampening_info("test.*")
        assert info["penalty"] > 0

    def test_suppression_after_multiple_flaps(self):
        """Test suppression after multiple route flaps."""
        # Create multiple flaps
        for _ in range(3):
            self.tracker.record_route_change("test.*", is_withdrawal=True)

        # Should be suppressed
        assert self.tracker.is_suppressed("test.*")

    def test_get_dampening_info(self):
        """Test getting dampening information."""
        # No activity
        info = self.tracker.get_dampening_info("test.*")
        assert info["penalty"] == 0
        assert not info["suppressed"]
        assert info["flap_count"] == 0

        # After flap
        self.tracker.record_route_change("test.*", is_withdrawal=True)
        info = self.tracker.get_dampening_info("test.*")
        assert info["penalty"] > 0
        assert info["flap_count"] == 1

    def test_cleanup_expired_states(self):
        """Test cleanup of expired dampening states."""
        # Create some state
        self.tracker.record_route_change("test.*", is_withdrawal=True)

        # Should have one state
        assert len(self.tracker.dampening_states) == 1

        # Manually set last_flap_time to old time to simulate expired state
        state = self.tracker.dampening_states["test.*"]
        state.last_flap_time = time.time() - 7200  # 2 hours ago
        state.penalty = 0  # No penalty

        # Cleanup should remove expired states
        self.tracker.cleanup_expired_states()

        # Should have cleaned up the state
        assert len(self.tracker.dampening_states) == 0


class TestRouteTableDampeningIntegration:
    """Test cases for route table dampening integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = RouteSelectionConfig()
        self.table = AGPRouteTable(self.config)

    def test_dampening_blocks_best_route(self):
        """Test that dampening blocks best route selection."""
        # Create and advertise a route
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route = AGPRoute("test.*", attrs, time.time(), "router-1")
        self.table.update_routes([route])

        # Should be able to get the route initially
        best = self.table.get_best_route("test.*")
        assert best is not None

        # Withdraw to create flap
        self.table.withdraw_routes(["test.*"])

        # Re-advertise to create another flap
        self.table.update_routes([route])

        # Withdraw again to trigger suppression
        self.table.withdraw_routes(["test.*"])

        # Should be suppressed now
        best = self.table.get_best_route("test.*")
        assert best is None

    def test_dampening_blocks_ecmp_routes(self):
        """Test that dampening blocks ECMP route selection."""
        # Create routes
        routes = []
        for i in range(2):
            attrs = AGPRouteAttributes(path=[64512], next_hop=f"router-{i}")
            route = AGPRoute("test.*", attrs, time.time(), f"router-{i}")
            routes.append(route)

        self.table.update_routes(routes)

        # Should get ECMP routes initially
        ecmp = self.table.get_ecmp_routes("test.*")
        assert len(ecmp) == 2

        # Create flaps to trigger suppression
        for _ in range(3):
            self.table.withdraw_routes(["test.*"])
            self.table.update_routes(routes)

        # Should be suppressed
        ecmp = self.table.get_ecmp_routes("test.*")
        assert len(ecmp) == 0

    def test_dampening_metrics_updated(self):
        """Test that dampening metrics are updated."""
        # Create a route and trigger suppression
        attrs = AGPRouteAttributes(path=[64512], next_hop="router-2")
        route = AGPRoute("test.*", attrs, time.time(), "router-1")

        # First advertisement (no flap)
        self.table.update_routes([route])

        # Create multiple flaps: withdraw and re-advertise multiple times
        for _ in range(4):  # 4 withdraw/advertise cycles = 4 flaps
            self.table.withdraw_routes(["test.*"])
            self.table.update_routes([route])

        # Check if route is actually suppressed
        dampening_info = self.table.get_dampening_info("test.*")
        assert dampening_info["suppressed"], f"Route should be suppressed but info: {dampening_info}"

        # Force metrics update
        self.table._update_metrics()

        # Should have at least one dampened route
        assert self.table.routes_dampened._value >= 1

    def test_dampening_info_access(self):
        """Test access to dampening information."""
        info = self.table.get_dampening_info("test.*")
        assert isinstance(info, dict)
        assert "penalty" in info
        assert "suppressed" in info


class TestEWMASmoother:
    """Test EWMA smoothing functionality."""

    def test_ewma_initial_value(self):
        """Test that EWMA starts with the first value."""
        smoother = EWMASmoother(alpha=0.1)
        result = smoother.update(100.0)
        assert result == 100.0
        assert smoother.get_smoothed_value() == 100.0

    def test_ewma_smoothing(self):
        """Test EWMA smoothing over multiple updates."""
        smoother = EWMASmoother(alpha=0.5)
        # First value
        result1 = smoother.update(100.0)
        assert result1 == 100.0

        # Second value - should be average with alpha=0.5
        result2 = smoother.update(200.0)
        expected = 0.5 * 200.0 + 0.5 * 100.0  # 150.0
        assert result2 == expected

        # Third value
        result3 = smoother.update(300.0)
        expected = 0.5 * 300.0 + 0.5 * 150.0  # 225.0
        assert result3 == expected

    def test_ewma_reset(self):
        """Test EWMA reset functionality."""
        smoother = EWMASmoother(alpha=0.1)
        smoother.update(100.0)
        assert smoother.get_smoothed_value() == 100.0

        smoother.reset()
        assert smoother.get_smoothed_value() is None
        assert smoother.last_update_time is None

    def test_ewma_different_alpha(self):
        """Test EWMA with different alpha values."""
        # High alpha (more responsive)
        smoother_high = EWMASmoother(alpha=0.9)
        smoother_high.update(100.0)
        result = smoother_high.update(200.0)
        expected_high = 0.9 * 200.0 + 0.1 * 100.0  # 190.0
        assert result == expected_high

        # Low alpha (more smooth)
        smoother_low = EWMASmoother(alpha=0.1)
        smoother_low.update(100.0)
        result = smoother_low.update(200.0)
        expected_low = 0.1 * 200.0 + 0.9 * 100.0  # 110.0
        assert result == expected_low


class TestHealthMetricsProcessor:
    """Test health metrics processing with EWMA and hysteresis."""

    def test_hysteresis_config_validation(self):
        """Test hysteresis configuration validation."""
        config = HysteresisConfig()
        config.validate()  # Should not raise

        # Test invalid values
        config.change_threshold_percent = 0
        with pytest.raises(ValueError, match="change_threshold_percent must be positive"):
            config.validate()

        config = HysteresisConfig(ewma_alpha=0)
        with pytest.raises(ValueError, match="ewma_alpha must be between 0 and 1"):
            config.validate()

        config = HysteresisConfig(ewma_alpha=1.5)
        with pytest.raises(ValueError, match="ewma_alpha must be between 0 and 1"):
            config.validate()

    def test_first_advertisement_always_allowed(self):
        """Test that the first health update is always advertised."""
        config = HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5)
        processor = HealthMetricsProcessor(hysteresis_config=config)

        result = processor.should_advertise_update(100.0, 1000.0)
        assert result is True
        assert processor.last_advertised_value == 100.0
        assert processor.last_change_time == 1000.0

    def test_hysteresis_below_threshold_suppressed(self):
        """Test that changes below threshold are suppressed."""
        config = HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5)
        processor = HealthMetricsProcessor(hysteresis_config=config)

        # First update
        processor.should_advertise_update(100.0, 1000.0)

        # Small change (5% < 10% threshold)
        result = processor.should_advertise_update(105.0, 1001.0)
        assert result is False
        assert processor.suppressed_updates == 1

    def test_hysteresis_above_threshold_but_too_soon_suppressed(self):
        """Test that changes above threshold but too soon are suppressed."""
        config = HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5)
        processor = HealthMetricsProcessor(hysteresis_config=config)

        # First update
        processor.should_advertise_update(100.0, 1000.0)

        # Large change but immediately after
        result = processor.should_advertise_update(120.0, 1000.5)  # Only 0.5s passed, need 5s
        assert result is False
        assert processor.suppressed_updates == 1

    def test_hysteresis_above_threshold_after_delay_allowed(self):
        """Test that changes above threshold after delay are allowed."""
        config = HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5, ewma_enabled=False)
        processor = HealthMetricsProcessor(hysteresis_config=config)

        # First update
        processor.should_advertise_update(100.0, 1000.0)

        # Large change after sufficient delay
        result = processor.should_advertise_update(120.0, 1006.0)  # 6s passed
        assert result is True
        assert processor.last_advertised_value == 120.0
        assert processor.suppressed_updates == 0

    def test_ewma_smoothing_enabled(self):
        """Test EWMA smoothing when enabled."""
        config = HysteresisConfig(
            change_threshold_percent=10.0, stabilization_period_seconds=5, ewma_alpha=0.5, ewma_enabled=True
        )
        processor = HealthMetricsProcessor(hysteresis_config=config)

        # First update
        processor.should_advertise_update(100.0, 1000.0)
        assert processor.get_smoothed_value() == 100.0

        # Second update - should be smoothed
        processor.should_advertise_update(200.0, 1001.0)
        expected_smoothed = 0.5 * 200.0 + 0.5 * 100.0  # 150.0
        assert processor.get_smoothed_value() == expected_smoothed

    def test_ewma_smoothing_disabled(self):
        """Test no smoothing when EWMA is disabled."""
        config = HysteresisConfig(change_threshold_percent=10.0, stabilization_period_seconds=5, ewma_enabled=False)
        processor = HealthMetricsProcessor(hysteresis_config=config)

        # First update
        processor.should_advertise_update(100.0, 1000.0)
        assert processor.get_smoothed_value() == 100.0

        # Second update - should not be smoothed
        processor.should_advertise_update(200.0, 1001.0)
        assert processor.get_smoothed_value() == 200.0

    def test_processor_reset(self):
        """Test processor reset functionality."""
        config = HysteresisConfig()
        processor = HealthMetricsProcessor(hysteresis_config=config)

        processor.should_advertise_update(100.0, 1000.0)
        processor.should_advertise_update(105.0, 1001.0)  # Suppressed

        assert processor.suppressed_updates == 1
        assert processor.last_advertised_value == 100.0

        processor.reset()
        assert processor.suppressed_updates == 0
        assert processor.last_advertised_value is None
        assert processor.last_change_time is None


class TestParallelSession:
    """Test parallel session state machine."""

    def test_session_initialization(self):
        """Test parallel session initialization."""
        config = ParallelSessionConfig(max_buffer_tokens=512)
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]

        session = ParallelSession(session_id="test-session-123", config=config, personas=personas)

        assert session.session_id == "test-session-123"
        assert session.state == ParallelSessionState.INIT
        assert len(session.personas) == 2
        assert "doctor-1" in session.buffers
        assert "lawyer-1" in session.buffers

    def test_state_transitions(self):
        """Test valid state transitions."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())

        # INIT -> DISPATCHED
        session.transition_to(ParallelSessionState.DISPATCHED)
        assert session.state == ParallelSessionState.DISPATCHED

        # DISPATCHED -> STREAMING
        session.transition_to(ParallelSessionState.STREAMING)
        assert session.state == ParallelSessionState.STREAMING

        # STREAMING -> BUFFERING
        session.transition_to(ParallelSessionState.BUFFERING)
        assert session.state == ParallelSessionState.BUFFERING

        # BUFFERING -> RECONCILING
        session.transition_to(ParallelSessionState.RECONCILING)
        assert session.state == ParallelSessionState.RECONCILING

        # RECONCILING -> COMPLETE
        session.transition_to(ParallelSessionState.COMPLETE)
        assert session.state == ParallelSessionState.COMPLETE

    def test_invalid_state_transitions(self):
        """Test invalid state transitions raise errors."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())

        # Try invalid transition INIT -> STREAMING
        with pytest.raises(ValueError, match="Invalid transition"):
            session.transition_to(ParallelSessionState.STREAMING)

        # Try transition from COMPLETE (terminal state)
        session.state = ParallelSessionState.COMPLETE
        with pytest.raises(ValueError, match="Invalid transition"):
            session.transition_to(ParallelSessionState.INIT)

    def test_add_persona_only_in_init(self):
        """Test personas can only be added in INIT state."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())

        # Should work in INIT
        session.add_persona({"persona_id": "nurse-1", "clone_id": 1})
        assert len(session.personas) == 1

        # Should fail after transitioning
        session.transition_to(ParallelSessionState.DISPATCHED)
        with pytest.raises(ValueError, match="Can only add personas in INIT state"):
            session.add_persona({"persona_id": "nurse-2", "clone_id": 1})

    def test_buffer_stream_data(self):
        """Test buffering streaming data."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data to buffer
        session.buffer_stream_data("doctor-1", 1, "Hello")
        session.buffer_stream_data("doctor-1", 2, " world")

        assert len(session.buffers["doctor-1"]) == 2
        assert session.buffers["doctor-1"][0]["data"] == "Hello"
        assert session.buffers["doctor-1"][1]["data"] == " world"

    def test_buffer_overflow(self):
        """Test buffer overflow protection."""
        config = ParallelSessionConfig(max_buffer_tokens=10)
        session = ParallelSession(session_id="test", config=config)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Fill buffer to limit
        session.buffer_stream_data("doctor-1", 1, "1234567890")  # Exactly 10 chars

        # Should fail on overflow
        with pytest.raises(ValueError, match="Buffer overflow"):
            session.buffer_stream_data("doctor-1", 2, "1")  # Would exceed limit

    def test_mark_persona_complete(self):
        """Test marking personas as complete."""
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        session = ParallelSession(session_id="test", config=ParallelSessionConfig(), personas=personas)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Mark first persona complete
        stats = {"latency_ms": 500, "tokens": 100}
        session.mark_persona_complete("doctor-1", stats)

        assert session.personas[0]["completed"] is True
        assert session.personas[0]["stats"] == stats

        # Should not transition yet (not all complete)
        assert session.state == ParallelSessionState.STREAMING

        # Mark second persona complete
        session.mark_persona_complete("lawyer-1", stats)

        # Should transition to BUFFERING
        assert session.state == ParallelSessionState.BUFFERING

    def test_reconcile_first_win(self):
        """Test first-win reconciliation policy."""
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        session = ParallelSession(
            session_id="test", config=ParallelSessionConfig(), personas=personas, reconciliation_policy="first-win"
        )
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data for both personas
        session.buffer_stream_data("doctor-1", 1, "Medical")
        session.buffer_stream_data("doctor-1", 2, " advice")

        session.buffer_stream_data("lawyer-1", 1, "Legal")
        session.buffer_stream_data("lawyer-1", 2, " advice")

        # Mark doctor complete first
        session.mark_persona_complete("doctor-1", {"latency_ms": 300})
        session.mark_persona_complete("lawyer-1", {"latency_ms": 500})

        # Should have transitioned to BUFFERING automatically
        assert session.state == ParallelSessionState.BUFFERING

        session.transition_to(ParallelSessionState.RECONCILING)

        result = session.reconcile_results()
        assert result["result"] == "Medical advice"
        assert result["winning_persona"] == "doctor-1"
        assert result["policy"] == "first-win"

    def test_reconcile_consensus(self):
        """Test consensus reconciliation policy."""
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        session = ParallelSession(
            session_id="test", config=ParallelSessionConfig(), personas=personas, reconciliation_policy="consensus"
        )
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data and mark both complete
        session.buffer_stream_data("doctor-1", 1, "Consensus")
        session.mark_persona_complete("doctor-1", {"latency_ms": 300})
        session.mark_persona_complete("lawyer-1", {"latency_ms": 500})

        # Should have transitioned to BUFFERING automatically
        assert session.state == ParallelSessionState.BUFFERING

        session.transition_to(ParallelSessionState.RECONCILING)

        result = session.reconcile_results()
        assert result["policy"] == "consensus"  # Consensus strategy now properly identified

    def test_reconcile_weighted_merge(self):
        """Test weighted merge reconciliation policy."""
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        session = ParallelSession(
            session_id="test", config=ParallelSessionConfig(), personas=personas, reconciliation_policy="weighted-merge"
        )
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data for both personas
        session.buffer_stream_data("doctor-1", 1, "Medical")
        session.buffer_stream_data("lawyer-1", 1, "Legal")

        # Mark both complete
        session.mark_persona_complete("doctor-1", {"latency_ms": 300})
        session.mark_persona_complete("lawyer-1", {"latency_ms": 500})

        # Should have transitioned to BUFFERING automatically
        assert session.state == ParallelSessionState.BUFFERING

        session.transition_to(ParallelSessionState.RECONCILING)

        result = session.reconcile_results()
        assert "Medical" in result["result"]
        assert "Legal" in result["result"]
        assert "[doctor-1:1.0]" in result["result"]
        assert "[lawyer-1:1.0]" in result["result"]


class TestReconciliationStrategies:
    """Test reconciliation strategy implementations."""

    def test_first_win_strategy(self):
        """Test FirstWinStrategy implementation."""
        from router_service.agp_update_handler import FirstWinStrategy

        strategy = FirstWinStrategy()
        assert strategy.name == "first-win"

        # Test with mock session
        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True, "completed_at": 100},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True, "completed_at": 200},
            ],
            reconciliation_policy="first-win",
        )
        session.buffers = {"doctor-1": [{"seq": 1, "data": "Medical"}]}

        assert strategy.can_reconcile(session)
        result = strategy.reconcile(session)
        assert result["policy"] == "first-win"
        assert result["winning_persona"] == "doctor-1"

    def test_consensus_strategy(self):
        """Test ConsensusStrategy implementation."""
        from router_service.agp_update_handler import ConsensusStrategy

        strategy = ConsensusStrategy()
        assert strategy.name == "consensus"

        # Test with majority
        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="consensus",
        )
        session.buffers = {"doctor-1": [{"seq": 1, "data": "Consensus"}]}

        assert strategy.can_reconcile(session)
        result = strategy.reconcile(session)
        assert result["policy"] == "consensus"

    def test_consensus_strategy_insufficient_majority(self):
        """Test ConsensusStrategy with insufficient majority."""
        from router_service.agp_update_handler import ConsensusStrategy

        strategy = ConsensusStrategy()

        # Test with insufficient majority (only 1 of 3 completed)
        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": False},
                {"persona_id": "nurse-1", "clone_id": 1, "completed": False},
            ],
            reconciliation_policy="consensus",
        )

        assert not strategy.can_reconcile(session)

    def test_weighted_merge_strategy(self):
        """Test WeightedMergeStrategy implementation."""
        from router_service.agp_update_handler import WeightedMergeStrategy

        strategy = WeightedMergeStrategy()
        assert strategy.name == "weighted-merge"

        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="weighted-merge",
        )
        session.buffers = {"doctor-1-1": [{"seq": 1, "data": "Medical"}], "lawyer-1-1": [{"seq": 1, "data": "Legal"}]}

        assert strategy.can_reconcile(session)
        result = strategy.reconcile(session)
        assert result["policy"] == "weighted-merge"
        assert "Medical" in result["result"]
        assert "Legal" in result["result"]

    def test_weighted_merge_with_weights(self):
        """Test WeightedMergeStrategy with custom weights."""
        from router_service.agp_update_handler import WeightedMergeStrategy

        weights = {"doctor-1": 2.0, "lawyer-1": 1.0}
        strategy = WeightedMergeStrategy(weights=weights)

        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="weighted-merge",
        )
        session.buffers = {"doctor-1": [{"seq": 1, "data": "Medical"}], "lawyer-1": [{"seq": 1, "data": "Legal"}]}

        result = strategy.reconcile(session)
        assert "[doctor-1:2.0]" in result["result"]
        assert "[lawyer-1:1.0]" in result["result"]
        assert result["total_weight"] == 3.0

    def test_arbiter_strategy_converged_results(self):
        """Test ArbiterReconciliationStrategy with converged results."""
        from router_service.agp_update_handler import ArbiterReconciliationStrategy

        strategy = ArbiterReconciliationStrategy(max_usd_budget=0.10)

        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="arbiter",
        )
        session.buffers = {
            "doctor-1-1": [{"seq": 1, "data": "Medical advice"}],
            "lawyer-1-1": [{"seq": 1, "data": "Medical advice"}],  # Same result
        }

        assert strategy.can_reconcile(session)
        result = strategy.reconcile(session)
        assert result["policy"] == "arbiter"
        assert result["arbiter_used"] is False
        assert result["results_converged"] is True
        assert "Medical advice" in result["result"]

    def test_arbiter_strategy_divergent_results(self):
        """Test ArbiterReconciliationStrategy with divergent results."""
        from router_service.agp_update_handler import ArbiterReconciliationStrategy

        strategy = ArbiterReconciliationStrategy(max_usd_budget=0.10)

        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="arbiter",
        )
        session.buffers = {
            "doctor-1-1": [
                {
                    "seq": 1,
                    "data": "Medical diagnosis with very detailed explanation of symptoms and comprehensive treatment plan including multiple options and follow-up care instructions",
                }
            ],
            "lawyer-1-1": [{"seq": 1, "data": "Legal contract"}],  # Different result
        }

        assert strategy.can_reconcile(session)
        result = strategy.reconcile(session)
        assert result["policy"] == "arbiter"
        assert result["arbiter_used"] is True
        assert "budget_used" in result
        assert "arbiter_reasoning" in result

    def test_arbiter_strategy_budget_exceeded(self):
        """Test ArbiterReconciliationStrategy when budget is exceeded."""
        from router_service.agp_update_handler import ArbiterReconciliationStrategy

        strategy = ArbiterReconciliationStrategy(max_usd_budget=0.05)
        strategy._budget_used = 0.06  # Simulate budget already exceeded

        session = ParallelSession(
            session_id="test",
            config=ParallelSessionConfig(),
            personas=[
                {"persona_id": "doctor-1", "clone_id": 1, "completed": True},
                {"persona_id": "lawyer-1", "clone_id": 1, "completed": True},
            ],
            reconciliation_policy="arbiter",
        )
        session.buffers = {
            "doctor-1-1": [
                {
                    "seq": 1,
                    "data": "Medical diagnosis with very detailed explanation of symptoms and comprehensive treatment plan including multiple options and follow-up care instructions",
                }
            ],
            "lawyer-1-1": [{"seq": 1, "data": "Legal contract"}],  # Different result
        }

        # When budget is exceeded, can_reconcile should return False
        assert not strategy.can_reconcile(session)

        # But we can still call reconcile directly to test the fallback behavior
        result = strategy.reconcile(session)
        assert result["policy"] == "arbiter"
        assert result["arbiter_used"] is False
        assert result["budget_exceeded"] is True


class TestParallelSessionManager:
    """Test parallel session manager."""

    def test_create_and_get_session(self):
        """Test creating and retrieving sessions."""
        manager = ParallelSessionManager()

        personas = [{"persona_id": "doctor-1", "clone_id": 1}]
        session = manager.create_session("test-session", personas)

        assert session.session_id == "test-session"
        assert len(manager.sessions) == 1

        retrieved = manager.get_session("test-session")
        assert retrieved is session

    def test_remove_session(self):
        """Test removing completed sessions."""
        manager = ParallelSessionManager()

        personas = [{"persona_id": "doctor-1", "clone_id": 1}]
        manager.create_session("test-session", personas)

        assert len(manager.sessions) == 1

        manager.remove_session("test-session")
        assert len(manager.sessions) == 0
        assert manager.get_session("test-session") is None

    def test_cleanup_expired_sessions(self):
        """Test cleanup of expired sessions."""
        config = ParallelSessionConfig()
        manager = ParallelSessionManager(config)

        # Create a session and manually set old creation time
        personas = [{"persona_id": "doctor-1", "clone_id": 1}]
        session = manager.create_session("old-session", personas)
        session.created_at = time.time() - 7200  # 2 hours ago

        # Create a recent session
        manager.create_session("new-session", personas)

        assert len(manager.sessions) == 2

        # Cleanup sessions older than 1 hour
        removed = manager.cleanup_expired_sessions(3600.0)
        assert removed == 1
        assert len(manager.sessions) == 1
        assert manager.get_session("new-session") is not None
        assert manager.get_session("old-session") is None

    def test_reconciliation_metrics(self):
        """Test reconciliation strategy metrics recording."""
        from metrics.registry import REGISTRY

        # Reset counter
        REGISTRY.counter("reconciliation_strategy_counts").set(0)

        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        session = manager.create_session("test-session", personas, "first-win")

        # Set up session for reconciliation
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)
        session.buffer_stream_data("doctor-1", 1, "Medical")
        session.mark_persona_complete("doctor-1", {"latency_ms": 300})
        session.transition_to(ParallelSessionState.BUFFERING)
        session.transition_to(ParallelSessionState.RECONCILING)

        # Perform reconciliation through manager
        initial_count = REGISTRY.counter("reconciliation_strategy_counts").value
        result = manager.reconcile_session("test-session")
        final_count = REGISTRY.counter("reconciliation_strategy_counts").value

        assert final_count == initial_count + 1
        assert result["policy"] == "first-win"


class TestCloneManagement:
    """Test persona clone management (GAP-114)."""

    def test_allocate_clones_single(self):
        """Test allocating clones for a single persona."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor", "count": 1}]
        personas = manager.allocate_clones(specs)

        assert len(personas) == 1
        assert personas[0]["persona_id"] == "doctor"
        assert personas[0]["clone_id"] == 1

    def test_allocate_clones_multiple(self):
        """Test allocating clones for multiple personas."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor", "count": 2}, {"persona_id": "lawyer", "count": 1}]
        personas = manager.allocate_clones(specs)

        assert len(personas) == 3
        assert personas[0]["persona_id"] == "doctor"
        assert personas[0]["clone_id"] == 1
        assert personas[1]["persona_id"] == "doctor"
        assert personas[1]["clone_id"] == 2
        assert personas[2]["persona_id"] == "lawyer"
        assert personas[2]["clone_id"] == 3

    def test_allocate_clones_default_count(self):
        """Test allocating clones with default count of 1."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor"}]  # No count specified
        personas = manager.allocate_clones(specs)

        assert len(personas) == 1
        assert personas[0]["persona_id"] == "doctor"
        assert personas[0]["clone_id"] == 1

    def test_clone_id_uniqueness(self):
        """Test that clone IDs are unique across allocations."""
        manager = ParallelSessionManager()

        # First allocation
        specs1 = [{"persona_id": "doctor", "count": 1}]
        personas1 = manager.allocate_clones(specs1)

        # Second allocation
        specs2 = [{"persona_id": "lawyer", "count": 1}]
        personas2 = manager.allocate_clones(specs2)

        assert personas1[0]["clone_id"] == 1
        assert personas2[0]["clone_id"] == 2

    def test_create_session_with_clones(self):
        """Test creating session with automatic clone allocation."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor", "count": 2}, {"persona_id": "lawyer", "count": 1}]
        session = manager.create_session_with_clones("test-session", specs)

        assert len(session.personas) == 3
        assert session.personas[0]["persona_id"] == "doctor"
        assert session.personas[0]["clone_id"] == 1
        assert session.personas[1]["persona_id"] == "doctor"
        assert session.personas[1]["clone_id"] == 2
        assert session.personas[2]["persona_id"] == "lawyer"
        assert session.personas[2]["clone_id"] == 3

    def test_multiple_clones_sequencing(self):
        """Test that multiple clones of same persona maintain independent buffers."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor", "count": 2}]
        session = manager.create_session_with_clones("test-session", specs)

        # Transition to streaming
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Send data to each clone
        session.buffer_stream_data("doctor", 1, "Clone 1 data", clone_id=1)
        session.buffer_stream_data("doctor", 1, "Clone 2 data", clone_id=2)

        # Check that buffers are separate
        assert len(session.buffers["doctor-1"]) == 1
        assert len(session.buffers["doctor-2"]) == 1
        assert session.buffers["doctor-1"][0]["data"] == "Clone 1 data"
        assert session.buffers["doctor-2"][0]["data"] == "Clone 2 data"

    def test_clone_completion_independence(self):
        """Test that clones complete independently."""
        manager = ParallelSessionManager()

        specs = [{"persona_id": "doctor", "count": 2}]
        session = manager.create_session_with_clones("test-session", specs)

        # Transition to streaming
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Complete first clone
        session.mark_persona_complete("doctor", {"latency_ms": 100}, clone_id=1)

        # Session should not transition to BUFFERING yet (not all clones complete)
        assert session.state == ParallelSessionState.STREAMING

        # Complete second clone
        session.mark_persona_complete("doctor", {"latency_ms": 200}, clone_id=2)

        # Now session should transition to BUFFERING
        assert session.state == ParallelSessionState.BUFFERING


class TestMessageSchemaExtensions:
    """Test GAP-111 message schema extensions."""

    def test_dispatch_payload_creation(self):
        """Test DISPATCH payload creation with parallel session metadata."""
        targets = [{"persona_id": "doctor-1", "clone_id": 1}, {"persona_id": "lawyer-1", "clone_id": 1}]
        budget = {"tokens": 4096, "dollars": 0.02}

        payload = DispatchPayload(session_id="test-session-123", targets=targets, budget=budget)

        assert payload.type == "agent.dispatch"
        assert payload.session_id == "test-session-123"
        assert len(payload.targets) == 2
        assert payload.targets[0].persona_id == "doctor-1"
        assert payload.targets[0].clone_id == 1

    def test_stream_payload_creation(self):
        """Test STREAM payload creation with parallel session metadata."""
        payload = StreamPayload(
            session_id="test-session-123", persona_id="doctor-1", clone_id=1, seq=5, data="Hello world"
        )

        assert payload.type == "agent.stream"
        assert payload.session_id == "test-session-123"
        assert payload.persona_id == "doctor-1"
        assert payload.clone_id == 1
        assert payload.seq == 5
        assert payload.data == "Hello world"

    def test_end_payload_creation(self):
        """Test END payload creation with parallel session metadata."""
        stats = {"latency_ms": 500, "tokens": 100}

        payload = EndPayload(session_id="test-session-123", persona_id="doctor-1", clone_id=1, stats=stats)

        assert payload.type == "agent.end"
        assert payload.session_id == "test-session-123"
        assert payload.persona_id == "doctor-1"
        assert payload.clone_id == 1
        assert payload.stats == stats


class TestMultiPersonaStreamOrdering:
    """Test multi-persona stream ordering (GAP-111)."""

    def test_stream_sequence_ordering(self):
        """Test that streams maintain sequence ordering per persona."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add out-of-order data for doctor persona
        session.buffer_stream_data("doctor-1", 3, "third")
        session.buffer_stream_data("doctor-1", 1, "first")
        session.buffer_stream_data("doctor-1", 2, "second")

        # Add data for lawyer persona
        session.buffer_stream_data("lawyer-1", 1, "legal")
        session.buffer_stream_data("lawyer-1", 2, "advice")

        # Check that data is stored (ordering handled by consumer)
        assert len(session.buffers["doctor-1"]) == 3
        assert len(session.buffers["lawyer-1"]) == 2

        # Verify sequence numbers are preserved
        doctor_data = sorted(session.buffers["doctor-1"], key=lambda x: x["seq"])
        assert doctor_data[0]["data"] == "first"
        assert doctor_data[1]["data"] == "second"
        assert doctor_data[2]["data"] == "third"

    def test_cross_persona_independence(self):
        """Test that different personas can stream independently."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Doctor streams quickly
        session.buffer_stream_data("doctor-1", 1, "Medical")
        session.buffer_stream_data("doctor-1", 2, " advice")

        # Lawyer streams slower
        session.buffer_stream_data("lawyer-1", 1, "Legal")

        # Doctor completes first
        session.mark_persona_complete("doctor-1", {"latency_ms": 300})

        # Lawyer continues streaming
        session.buffer_stream_data("lawyer-1", 2, " advice")
        session.mark_persona_complete("lawyer-1", {"latency_ms": 600})

        # Session should transition to BUFFERING when all complete
        assert session.state == ParallelSessionState.BUFFERING

    def test_sequence_gap_handling(self):
        """Test handling of sequence gaps (out-of-order delivery)."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Simulate out-of-order delivery
        session.buffer_stream_data("doctor-1", 5, "fifth")
        session.buffer_stream_data("doctor-1", 2, "second")
        session.buffer_stream_data("doctor-1", 1, "first")

        # Buffer should contain all data
        assert len(session.buffers["doctor-1"]) == 3

        # Sequence numbers should be preserved for ordering
        seqs = [item["seq"] for item in session.buffers["doctor-1"]]
        assert 1 in seqs and 2 in seqs and 5 in seqs

    def test_gap_fill_timeout(self):
        """Test gap filling after timeout."""
        config = ParallelSessionConfig(buffer_timeout_s=0.1)  # Short timeout
        session = ParallelSession(session_id="test", config=config)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add sequence 1 and 3, missing 2
        session.buffer_stream_data("doctor-1", 1, "first")
        session.buffer_stream_data("doctor-1", 3, "third")

        # Wait for timeout
        import time

        time.sleep(0.2)

        # Add sequence 4, which should trigger gap fill for 2
        session.buffer_stream_data("doctor-1", 4, "fourth")

        # Check that gap was filled
        ordered = session.get_ordered_buffer_data("doctor-1")
        assert len(ordered) == 4
        assert ordered[0]["data"] == "first"
        assert ordered[1]["data"] == ""  # Gap filled
        assert ordered[1]["gap_filled"] is True
        assert ordered[2]["data"] == "third"
        assert ordered[3]["data"] == "fourth"

    def test_gap_fill_in_order(self):
        """Test gap filling when data arrives in order."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add in order
        session.buffer_stream_data("doctor-1", 1, "first")
        session.buffer_stream_data("doctor-1", 2, "second")
        session.buffer_stream_data("doctor-1", 3, "third")

        # No gaps should be filled
        ordered = session.get_ordered_buffer_data("doctor-1")
        assert len(ordered) == 3
        assert all(not item.get("gap_filled", False) for item in ordered)

    def test_buffer_overflow_qos_gold(self):
        """Test buffer overflow with gold QoS (smaller buffer)."""
        config = ParallelSessionConfig(max_buffer_tokens=20)
        session = ParallelSession(session_id="test", config=config)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Gold QoS has 0.5x multiplier, so buffer limit is 10
        session.buffer_stream_data("doctor-1", 1, "1234567890", "gold")  # 10 chars

        # Should fail on overflow (11th char would exceed 10)
        with pytest.raises(ValueError, match="Buffer overflow"):
            session.buffer_stream_data("doctor-1", 2, "1", "gold")

    def test_buffer_overflow_qos_bronze(self):
        """Test buffer overflow with bronze QoS (larger buffer)."""
        config = ParallelSessionConfig(max_buffer_tokens=20)
        session = ParallelSession(session_id="test", config=config)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Bronze QoS has 2.0x multiplier, so buffer limit is 40
        session.buffer_stream_data("doctor-1", 1, "1234567890" * 4, "bronze")  # 40 chars

        # Should fail on overflow (41st char would exceed 40)
        with pytest.raises(ValueError, match="Buffer overflow"):
            session.buffer_stream_data("doctor-1", 2, "1", "bronze")

    def test_buffer_stats(self):
        """Test buffer statistics tracking."""
        session = ParallelSession(session_id="test", config=ParallelSessionConfig())
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add some data
        session.buffer_stream_data("doctor-1", 1, "hello")
        session.buffer_stream_data("doctor-1", 3, "world")

        stats = session.get_buffer_stats("doctor-1")
        assert stats["total_entries"] == 2
        assert stats["total_tokens"] == 10  # "hello" + "world"
        assert stats["gaps"] == 0  # No gaps filled yet
        assert stats["oldest_age"] > 0

    def test_buffer_stats_with_gaps(self):
        """Test buffer statistics with gap filling."""
        config = ParallelSessionConfig(buffer_timeout_s=0.1)
        session = ParallelSession(session_id="test", config=config)
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data with gap
        session.buffer_stream_data("doctor-1", 1, "hello")
        session.buffer_stream_data("doctor-1", 3, "world")

        # Wait for timeout and trigger gap fill
        import time

        time.sleep(0.2)
        session.get_ordered_buffer_data("doctor-1")  # Triggers gap fill

        stats = session.get_buffer_stats("doctor-1")
        assert stats["total_entries"] == 3  # Original 2 + 1 gap fill
        assert stats["gaps"] == 1
        assert stats["total_tokens"] == 10  # "hello" + "" + "world"


class TestAuditAndTracing:
    """Test cases for audit logging and tracing in reconciliation."""

    def test_session_creation_audit(self, tmp_path):
        """Test that session creation is audited."""
        import os
        import sys

        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
        import audit_log as audit_log_module

        # Mock environment
        original_env = os.environ.get("ROUTER_DATA_DIR")
        os.environ["ROUTER_DATA_DIR"] = str(tmp_path)
        os.environ["AUDIT_SECRET"] = "test-secret"  # noqa: S105 test placeholder

        try:
            manager = ParallelSessionManager()
            personas = [{"persona_id": "doctor-1"}]
            manager.create_session("test-session", personas, "first-win")

            # Check audit file was created
            audit_file = tmp_path / "reconciliation_audit.jsonl"
            assert audit_file.exists()

            # Verify audit log integrity
            assert audit_log_module.verify_log(str(audit_file), b"test-secret")

            # Check audit content
            with open(audit_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
                import json

                event = json.loads(lines[0])
                assert event["event"]["event_type"] == "session_created"
                assert event["event"]["session_id"] == "test-session"
        finally:
            if original_env:
                os.environ["ROUTER_DATA_DIR"] = original_env
            else:
                os.environ.pop("ROUTER_DATA_DIR", None)
            os.environ.pop("AUDIT_SECRET", None)

    def test_reconciliation_audit(self, tmp_path):
        """Test that reconciliation completion is audited."""
        import os
        import sys

        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
        import audit_log as audit_log_module

        # Mock environment
        original_env = os.environ.get("ROUTER_DATA_DIR")
        os.environ["ROUTER_DATA_DIR"] = str(tmp_path)
        os.environ["AUDIT_SECRET"] = "test-secret"  # noqa: S105 test placeholder

        try:
            manager = ParallelSessionManager()
            personas = [{"persona_id": "doctor-1"}]
            session = manager.create_session("test-session", personas, "first-win")

            # Transition through proper states
            session.transition_to(ParallelSessionState.DISPATCHED)
            session.transition_to(ParallelSessionState.STREAMING)
            session.transition_to(ParallelSessionState.BUFFERING)
            session.transition_to(ParallelSessionState.RECONCILING)
            session.mark_persona_complete("doctor-1", {"tokens": 100, "latency_ms": 50})

            # Reconcile
            manager.reconcile_session("test-session")

            # Check audit file
            audit_file = tmp_path / "reconciliation_audit.jsonl"
            assert audit_file.exists()

            # Verify integrity
            assert audit_log_module.verify_log(str(audit_file), b"test-secret")

            # Check reconciliation event
            with open(audit_file) as f:
                lines = f.readlines()
                assert len(lines) == 2  # session_created + reconciliation_complete
                import json

                recon_event = json.loads(lines[1])
                assert recon_event["event"]["event_type"] == "reconciliation_complete"
                assert recon_event["event"]["session_id"] == "test-session"
        finally:
            if original_env:
                os.environ["ROUTER_DATA_DIR"] = original_env
            else:
                os.environ.pop("ROUTER_DATA_DIR", None)
            os.environ.pop("AUDIT_SECRET", None)

    def test_tracing_spans_created(self):
        """Test that tracing spans are created for key operations."""
        from unittest.mock import MagicMock, patch

        # Mock tracer
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock()
        mock_tracer._get_current_span.return_value = mock_span

        with patch("router_service.agp_update_handler.get_tracer", return_value=mock_tracer):
            manager = ParallelSessionManager()
            personas = [{"persona_id": "doctor-1"}]

            # Test dispatch span
            session = manager.create_session("test-session", personas, "first-win")
            mock_tracer.start_as_current_span.assert_called_with("dispatch.session")

            # Reset mock
            mock_tracer.reset_mock()

            # Test stream span
            session.transition_to(ParallelSessionState.DISPATCHED)
            session.transition_to(ParallelSessionState.STREAMING)
            session.buffer_stream_data("doctor-1", 1, "test data")
            mock_tracer.start_as_current_span.assert_called_with("stream.buffer")

            # Reset mock
            mock_tracer.reset_mock()

            # Test reconcile span
            session.transition_to(ParallelSessionState.BUFFERING)
            session.transition_to(ParallelSessionState.RECONCILING)
            session.mark_persona_complete("doctor-1", {"tokens": 100, "latency_ms": 50})
            manager.reconcile_session("test-session")
            mock_tracer.start_as_current_span.assert_called_with("reconciliation.session")


class TestStreamingReconciliation:
    """Test cases for streaming reconciliation functionality."""

    def test_incremental_reducer_interface(self):
        """Test that strategies implement the incremental interface."""
        from router_service.agp_update_handler import (
            ConsensusStrategy,
            FirstWinStrategy,
            IncrementalReconciliationStrategy,
            WeightedMergeStrategy,
        )

        strategies = [FirstWinStrategy(), ConsensusStrategy(), WeightedMergeStrategy()]
        for strategy in strategies:
            assert isinstance(strategy, IncrementalReconciliationStrategy)
            assert hasattr(strategy, "can_incremental_reconcile")
            assert hasattr(strategy, "incremental_reconcile")
            assert hasattr(strategy, "should_flush_partial")

    def test_first_win_incremental_reconciliation(self):
        """Test incremental reconciliation with first-win strategy."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}, {"persona_id": "doctor-2"}]
        session = manager.create_session("test-session", personas, "first-win")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Complete first persona
        session.mark_persona_complete("doctor-1", {"tokens": 100})

        # Check incremental reconciliation is possible
        assert session.can_streaming_reconcile()

        # Perform incremental reconciliation
        result = session.streaming_reconcile()
        assert result is not None
        assert "result" in result
        assert result["policy"] == "first-win"
        assert result["incremental"] is True

    def test_consensus_incremental_reconciliation(self):
        """Test incremental reconciliation with consensus strategy."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}, {"persona_id": "doctor-2"}, {"persona_id": "doctor-3"}]
        session = manager.create_session("test-session", personas, "consensus")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Complete first persona (not enough for consensus with 3 personas at 0.5 threshold)
        session.mark_persona_complete("doctor-1", {"tokens": 100})
        assert not session.can_streaming_reconcile()

        # Complete second persona (now 2/3 = 0.67 > 0.5, consensus reached)
        session.mark_persona_complete("doctor-2", {"tokens": 100})
        assert session.can_streaming_reconcile()

        # Perform incremental reconciliation
        result = session.streaming_reconcile()
        assert result is not None
        assert result["policy"] == "consensus"
        assert result["incremental"] is True

    def test_weighted_merge_incremental_reconciliation(self):
        """Test incremental reconciliation with weighted merge strategy."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}, {"persona_id": "doctor-2"}]
        session = manager.create_session("test-session", personas, "weighted-merge")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Complete first persona
        session.mark_persona_complete("doctor-1", {"tokens": 100})
        assert session.can_streaming_reconcile()

        # Perform incremental reconciliation
        result = session.streaming_reconcile()
        assert result is not None
        assert result["policy"] == "weighted-merge"
        assert result["incremental"] is True
        assert result["completed_count"] == 1
        assert result["total_personas"] == 2

    def test_streaming_backpressure_flush(self):
        """Test backpressure-based flushing in streaming reconciliation."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}]
        session = manager.create_session("test-session", personas, "first-win")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Add data to fill buffer (more than 80% of 256)
        session.buffer_stream_data("doctor-1", 1, "x" * 250)  # Large data

        # Check if should flush partial
        assert session.should_flush_streaming()

    def test_streaming_reconciliation_manager_integration(self):
        """Test streaming reconciliation through manager interface."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}]
        session = manager.create_session("test-session", personas, "first-win")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Use manager method to mark complete and check streaming
        result = manager.mark_persona_complete_and_check_streaming("test-session", "doctor-1", {"tokens": 100})

        assert result is not None
        assert result["policy"] == "first-win"
        assert result["incremental"] is True

    def test_streaming_reconciliation_metrics(self):
        """Test that streaming reconciliation increments metrics."""
        manager = ParallelSessionManager()
        personas = [{"persona_id": "doctor-1"}]
        session = manager.create_session("test-session", personas, "first-win")

        # Transition to streaming state
        session.transition_to(ParallelSessionState.DISPATCHED)
        session.transition_to(ParallelSessionState.STREAMING)

        # Mark complete and trigger streaming reconciliation
        initial_count = manager.streaming_reconcile_sessions_total.value
        manager.mark_persona_complete_and_check_streaming("test-session", "doctor-1", {"tokens": 100})

        # Check metric was incremented
        assert manager.streaming_reconcile_sessions_total.value == initial_count + 1


class TestAdaptiveReconciliation:
    """Test cases for adaptive reconciliation functionality."""

    def test_adaptive_strategy_selection_time_pressure(self):
        """Test adaptive strategy selection prioritizes speed under time pressure."""
        from router_service.adaptive_reconciliation import (
            SwitchingContext,
            enable_adaptive_reconciliation,
            get_adaptive_reconciliation_strategy,
        )

        # Enable adaptive reconciliation
        enable_adaptive_reconciliation(True)

        context = SwitchingContext(
            request_complexity=0.8,
            time_pressure=True,
            cost_sensitivity=0.5,
            quality_requirement=0.3,
            persona_count=2,
            convergence_history=[True, True, True],
        )

        strategy = get_adaptive_reconciliation_strategy(context)
        assert strategy == "first-win"

    def test_adaptive_strategy_selection_high_quality(self):
        """Test adaptive strategy selection chooses consensus for high quality requirements."""
        from router_service.adaptive_reconciliation import (
            SwitchingContext,
            enable_adaptive_reconciliation,
            get_adaptive_reconciliation_strategy,
        )

        # Enable adaptive reconciliation
        enable_adaptive_reconciliation(True)

        context = SwitchingContext(
            request_complexity=0.8,
            time_pressure=False,
            cost_sensitivity=0.5,
            quality_requirement=0.9,
            persona_count=2,
            convergence_history=[True, True, True],
        )

        strategy = get_adaptive_reconciliation_strategy(context)
        assert strategy == "consensus"

    def test_adaptive_strategy_selection_many_personas(self):
        """Test adaptive strategy selection chooses arbiter for many personas."""
        from router_service.adaptive_reconciliation import (
            SwitchingContext,
            enable_adaptive_reconciliation,
            get_adaptive_reconciliation_strategy,
        )

        # Enable adaptive reconciliation
        enable_adaptive_reconciliation(True)

        context = SwitchingContext(
            request_complexity=0.8,
            time_pressure=False,
            cost_sensitivity=0.5,
            quality_requirement=0.3,
            persona_count=5,
            convergence_history=[True, True, True],
        )

        strategy = get_adaptive_reconciliation_strategy(context)
        assert strategy == "arbiter"

    def test_parallel_session_adaptive_integration(self):
        """Test ParallelSession integration with adaptive reconciliation."""
        from router_service.adaptive_reconciliation import enable_adaptive_reconciliation

        # Enable adaptive reconciliation
        enable_adaptive_reconciliation(True)

        # Create session with many expert personas (high quality requirement)
        session = ParallelSession(
            session_id="test-adaptive-session",
            config=ParallelSessionConfig(),
            personas=[
                {"id": "persona1", "type": "expert"},
                {"id": "persona2", "type": "expert"},
                {"id": "persona3", "type": "expert"},
                {"id": "persona4", "type": "expert"},
                {"id": "persona5", "type": "expert"},
            ],
            reconciliation_policy="first-win",
            adaptive_reconciliation_enabled=True,
            arbiter_max_usd=0.10,
        )

        # Test context estimation
        complexity = session._estimate_request_complexity()
        quality_req = session._estimate_quality_requirement()

        assert complexity == 1.0  # 5 personas = max complexity
        assert quality_req == 1.0  # All expert personas = max quality requirement

        # Test strategy selection
        strategy = session._get_reconciliation_strategy()
        assert strategy.__class__.__name__ == "ConsensusStrategy"

    def test_parallel_session_context_estimation(self):
        """Test context estimation methods in ParallelSession."""
        session = ParallelSession(
            session_id="test-context-session",
            config=ParallelSessionConfig(reconciliation_timeout_s=5.0),  # Short timeout
            personas=[{"id": "persona1", "type": "reasoning"}, {"id": "persona2", "type": "analysis"}],
            reconciliation_policy="first-win",
            adaptive_reconciliation_enabled=False,
            arbiter_max_usd=0.02,  # Low budget
        )

        # Test time pressure detection
        time_pressure = session._detect_time_pressure()
        assert time_pressure  # Short timeout = high time pressure

        # Test cost sensitivity
        cost_sensitivity = session._estimate_cost_sensitivity()
        assert cost_sensitivity == 0.9  # Low budget = high cost sensitivity

        # Test complexity estimation
        complexity = session._estimate_request_complexity()
        assert complexity == pytest.approx(0.6, abs=1e-10)  # 2 personas + specialized types = 0.4 + 0.2 = 0.6

        # Test quality requirement
        quality_req = session._estimate_quality_requirement()
        assert quality_req == 1.0  # Both personas are specialized types (reasoning/analysis)


if __name__ == "__main__":
    pytest.main([__file__])
