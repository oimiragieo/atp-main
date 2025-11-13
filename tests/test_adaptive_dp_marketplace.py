#!/usr/bin/env python3
"""Comprehensive tests for GAP-270: Adaptive DP Allocation Marketplace."""

import pytest

from tools.adaptive_dp_marketplace import (
    AdaptiveDPMarketplace,
    AllocationRequest,
    AllocationStrategy,
    TenantPriority,
)


class TestTenantManagement:
    """Test tenant registration and management."""

    def test_tenant_registration(self):
        """Test registering tenants in the marketplace."""
        marketplace = AdaptiveDPMarketplace()

        # Register a tenant
        success = marketplace.register_tenant("tenant1", "Test Corp", TenantPriority.HIGH)
        assert success is True

        # Check tenant was registered
        assert "tenant1" in marketplace.tenants
        tenant = marketplace.tenants["tenant1"]
        assert tenant.name == "Test Corp"
        assert tenant.priority == TenantPriority.HIGH

        # Try to register duplicate tenant
        success = marketplace.register_tenant("tenant1", "Another Corp")
        assert success is False

    def test_tenant_profile_initialization(self):
        """Test tenant profile initialization."""
        marketplace = AdaptiveDPMarketplace()
        marketplace.register_tenant("tenant1", "Test Corp", TenantPriority.MEDIUM)

        tenant = marketplace.tenants["tenant1"]
        assert tenant.tenant_id == "tenant1"
        assert tenant.name == "Test Corp"
        assert tenant.priority == TenantPriority.MEDIUM
        assert tenant.historical_usage == 0.0
        assert tenant.current_allocation == 0.0
        assert tenant.fairness_score == 1.0
        assert len(tenant.allocation_history) == 0


class TestAllocationStrategies:
    """Test different allocation strategies."""

    def test_proportional_fair_allocation(self):
        """Test proportional fair allocation strategy."""
        marketplace = AdaptiveDPMarketplace(total_budget=4.0, strategy=AllocationStrategy.PROPORTIONAL_FAIR)

        # Register tenants with different usage histories
        marketplace.register_tenant("tenant1", "High Usage Corp")
        marketplace.register_tenant("tenant2", "Low Usage Corp")

        # Set up different historical usage
        marketplace.tenants["tenant1"].historical_usage = 2.0
        marketplace.tenants["tenant2"].historical_usage = 0.5

        # Create allocation requests
        request1 = AllocationRequest("req1", "tenant1", 1.0, "count_query")
        request2 = AllocationRequest("req2", "tenant2", 1.0, "count_query")

        # Allocate budget
        result1 = marketplace.allocate_budget(request1)
        result2 = marketplace.allocate_budget(request2)

        # Low usage tenant should get more allocation
        assert result2.allocated_epsilon > result1.allocated_epsilon

    def test_priority_based_allocation(self):
        """Test priority-based allocation strategy."""
        marketplace = AdaptiveDPMarketplace(total_budget=3.0, strategy=AllocationStrategy.PRIORITY_BASED)

        # Register tenants with different priorities
        marketplace.register_tenant("tenant1", "High Priority", TenantPriority.HIGH)
        marketplace.register_tenant("tenant2", "Low Priority", TenantPriority.LOW)

        # Create allocation requests
        request1 = AllocationRequest("req1", "tenant1", 1.0, "count_query")
        request2 = AllocationRequest("req2", "tenant2", 1.0, "count_query")

        # Allocate budget
        result1 = marketplace.allocate_budget(request1)
        result2 = marketplace.allocate_budget(request2)

        # High priority tenant should get more allocation
        assert result1.allocated_epsilon > result2.allocated_epsilon

    def test_demand_driven_allocation(self):
        """Test demand-driven allocation strategy."""
        marketplace = AdaptiveDPMarketplace(total_budget=2.0, strategy=AllocationStrategy.DEMAND_DRIVEN)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Create requests with different urgency levels
        request1 = AllocationRequest("req1", "tenant1", 1.0, "count_query", urgency_level=5)
        request2 = AllocationRequest("req2", "tenant1", 1.0, "count_query", urgency_level=1)

        # Allocate budget
        result1 = marketplace.allocate_budget(request1)
        result2 = marketplace.allocate_budget(request2)

        # High urgency request should get more allocation
        assert result1.allocated_epsilon > result2.allocated_epsilon

    def test_auction_based_allocation(self):
        """Test auction-based allocation strategy."""
        marketplace = AdaptiveDPMarketplace(total_budget=2.0, strategy=AllocationStrategy.AUCTION_BASED)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Create requests with different bid amounts
        request1 = AllocationRequest("req1", "tenant1", 1.0, "count_query", bid_amount=10.0)
        request2 = AllocationRequest("req2", "tenant1", 1.0, "count_query", bid_amount=5.0)

        # Allocate budget
        result1 = marketplace.allocate_budget(request1)
        result2 = marketplace.allocate_budget(request2)

        # Higher bid should get more allocation
        assert result1.allocated_epsilon > result2.allocated_epsilon


class TestFairnessMechanisms:
    """Test fairness adjustment mechanisms."""

    def test_fairness_adjustment_calculation(self):
        """Test fairness adjustment calculation."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp")

        # Test with no allocation history
        adjustment = marketplace._calculate_fairness_adjustment("tenant1")
        assert adjustment == 1.0

        # Add some allocation history
        tenant = marketplace.tenants["tenant1"]
        tenant.allocation_history = [1.0, 1.0, 1.0]  # Consistent allocation

        adjustment = marketplace._calculate_fairness_adjustment("tenant1")
        assert adjustment == 1.0

        # Add under-allocation scenario
        tenant.allocation_history.extend([0.5, 0.5, 0.5])  # Recent under-allocation
        adjustment = marketplace._calculate_fairness_adjustment("tenant1")
        assert adjustment > 1.0  # Should get boost

    def test_tenant_fairness_score_calculation(self):
        """Test tenant fairness score calculation."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp")

        tenant = marketplace.tenants["tenant1"]

        # Test with no history
        score = marketplace._calculate_tenant_fairness(tenant)
        assert score == 1.0

        # Test with consistent allocations
        tenant.allocation_history = [1.0, 1.0, 1.0, 1.0]
        score = marketplace._calculate_tenant_fairness(tenant)
        assert score > 0.9  # High fairness score

        # Test with variable allocations
        tenant.allocation_history = [0.1, 2.0, 0.1, 2.0]
        score = marketplace._calculate_tenant_fairness(tenant)
        assert score < 0.8  # Lower fairness score


class TestMarketDynamics:
    """Test market dynamics and status reporting."""

    def test_market_status_reporting(self):
        """Test comprehensive market status reporting."""
        marketplace = AdaptiveDPMarketplace(total_budget=10.0)

        # Register tenants and make allocations
        marketplace.register_tenant("tenant1", "Test Corp")
        request = AllocationRequest("req1", "tenant1", 2.0, "count_query")
        marketplace.allocate_budget(request)

        status = marketplace.get_market_status()

        assert status["total_budget"] == 10.0
        assert status["available_budget"] == 8.0
        assert status["active_allocations"] == 2.0
        assert status["utilization_rate"] == 0.2
        assert status["registered_tenants"] == 1
        assert "fairness_index" in status
        assert "strategy_metrics" in status

    def test_tenant_status_reporting(self):
        """Test individual tenant status reporting."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp", TenantPriority.HIGH)

        # Make an allocation
        request = AllocationRequest("req1", "tenant1", 1.5, "count_query")
        marketplace.allocate_budget(request)

        status = marketplace.get_tenant_status("tenant1")

        assert status is not None
        assert status["tenant_id"] == "tenant1"
        assert status["name"] == "Test Corp"
        assert status["priority"] == "HIGH"
        assert status["current_allocation"] == 1.5
        assert status["active_allocations_count"] == 1

    def test_market_pressure_update(self):
        """Test market pressure calculation and updates."""
        marketplace = AdaptiveDPMarketplace(total_budget=5.0)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Add pending requests to create demand
        requests = [
            AllocationRequest("req1", "tenant1", 1.0, "count_query"),
            AllocationRequest("req2", "tenant1", 1.0, "mean_query"),
            AllocationRequest("req3", "tenant1", 1.0, "federation"),
        ]

        for req in requests:
            marketplace.submit_allocation_request(req)

        marketplace.update_market_pressure()

        # Market pressure should increase with pending demand
        assert marketplace.market_pressure > 1.0

    def test_allocation_release(self):
        """Test releasing active allocations."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp")

        # Make an allocation
        request = AllocationRequest("req1", "tenant1", 2.0, "count_query")
        marketplace.allocate_budget(request)

        # Verify allocation is active
        assert "req1" in marketplace.active_allocations
        assert marketplace.tenants["tenant1"].current_allocation == 2.0

        # Release allocation
        success = marketplace.release_allocation("req1")
        assert success is True

        # Verify allocation is released
        assert "req1" not in marketplace.active_allocations
        assert marketplace.tenants["tenant1"].current_allocation == 0.0

        # Try to release non-existent allocation
        success = marketplace.release_allocation("nonexistent")
        assert success is False


class TestAllocationLifecycle:
    """Test complete allocation request lifecycle."""

    def test_allocation_request_submission(self):
        """Test submitting allocation requests."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp")

        request = AllocationRequest("req1", "tenant1", 1.0, "count_query")

        # Submit request
        request_id = marketplace.submit_allocation_request(request)

        assert request_id == "req1"
        assert len(marketplace.pending_requests) == 1
        assert marketplace.pending_requests[0].request_id == "req1"

    def test_allocation_for_unregistered_tenant(self):
        """Test allocation request for unregistered tenant."""
        marketplace = AdaptiveDPMarketplace()

        request = AllocationRequest("req1", "nonexistent", 1.0, "count_query")

        with pytest.raises(ValueError, match="Tenant nonexistent not registered"):
            marketplace.allocate_budget(request)

    def test_budget_exhaustion_handling(self):
        """Test handling when budget is exhausted."""
        marketplace = AdaptiveDPMarketplace(total_budget=1.0)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Exhaust the budget
        request1 = AllocationRequest("req1", "tenant1", 1.0, "count_query")
        result1 = marketplace.allocate_budget(request1)

        assert result1.allocated_epsilon == 1.0

        # Try to allocate more
        request2 = AllocationRequest("req2", "tenant1", 1.0, "count_query")
        result2 = marketplace.allocate_budget(request2)

        assert result2.allocated_epsilon == 0.0

    def test_allocation_result_structure(self):
        """Test allocation result structure and content."""
        marketplace = AdaptiveDPMarketplace()

        marketplace.register_tenant("tenant1", "Test Corp")

        request = AllocationRequest("req1", "tenant1", 1.5, "count_query")
        result = marketplace.allocate_budget(request)

        assert result.request_id == "req1"
        assert result.tenant_id == "tenant1"
        assert result.allocated_epsilon <= 1.5
        assert result.allocation_strategy == AllocationStrategy.PROPORTIONAL_FAIR
        assert result.fairness_adjustment >= 0.9  # Should be close to 1.0 for new tenant
        assert result.allocated_at is not None


class TestStrategyOptimization:
    """Test dynamic strategy optimization."""

    def test_strategy_optimization_under_high_utilization(self):
        """Test strategy switching under high utilization."""
        marketplace = AdaptiveDPMarketplace(total_budget=1.0, strategy=AllocationStrategy.PROPORTIONAL_FAIR)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Create high utilization scenario
        for i in range(10):
            request = AllocationRequest(f"req{i}", "tenant1", 0.1, "count_query")
            marketplace.submit_allocation_request(request)

        # Trigger optimization
        marketplace.optimize_allocation_strategy()

        # Should switch to priority-based under high utilization
        assert marketplace.strategy == AllocationStrategy.PRIORITY_BASED

    def test_strategy_optimization_under_low_fairness(self):
        """Test strategy switching under low fairness conditions."""
        marketplace = AdaptiveDPMarketplace(strategy=AllocationStrategy.PRIORITY_BASED)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Create low fairness scenario by manipulating tenant fairness score
        marketplace.tenants["tenant1"].fairness_score = 0.5

        # Trigger optimization
        marketplace.optimize_allocation_strategy()

        # Should switch to proportional fair under low fairness
        assert marketplace.strategy == AllocationStrategy.PROPORTIONAL_FAIR


class TestIntegrationScenarios:
    """Test complex integration scenarios."""

    def test_multi_tenant_allocation_scenario(self):
        """Test allocation across multiple tenants with different characteristics."""
        marketplace = AdaptiveDPMarketplace(total_budget=10.0)

        # Register diverse tenants
        tenants = [
            ("tenant1", "Enterprise Corp", TenantPriority.HIGH),
            ("tenant2", "Research Lab", TenantPriority.MEDIUM),
            ("tenant3", "Startup Inc", TenantPriority.LOW),
        ]

        for tenant_id, name, priority in tenants:
            marketplace.register_tenant(tenant_id, name, priority)

        # Submit various requests
        requests = [
            AllocationRequest("req1", "tenant1", 2.0, "count_query", urgency_level=5),
            AllocationRequest("req2", "tenant2", 1.5, "mean_query", urgency_level=3),
            AllocationRequest("req3", "tenant3", 1.0, "federation", urgency_level=2),
            AllocationRequest("req4", "tenant1", 1.8, "count_query", urgency_level=4),
        ]

        total_allocated = 0
        for request in requests:
            result = marketplace.allocate_budget(request)
            total_allocated += result.allocated_epsilon

        # Verify allocations
        assert total_allocated > 0
        assert total_allocated <= 10.0

        # Check that high priority tenant got preferential treatment
        tenant1_allocation = marketplace.tenants["tenant1"].current_allocation
        tenant3_allocation = marketplace.tenants["tenant3"].current_allocation
        assert tenant1_allocation >= tenant3_allocation

    def test_market_evolution_over_time(self):
        """Test how market dynamics evolve over multiple allocation cycles."""
        marketplace = AdaptiveDPMarketplace(total_budget=5.0)

        marketplace.register_tenant("tenant1", "Test Corp")

        # Simulate multiple allocation cycles
        for cycle in range(5):
            request = AllocationRequest(f"req{cycle}", "tenant1", 1.0, "count_query")
            marketplace.allocate_budget(request)

            # Update market pressure periodically
            if cycle % 2 == 0:
                marketplace.update_market_pressure()

        # Verify tenant has allocation history (may be less than 5 due to budget exhaustion)
        tenant = marketplace.tenants["tenant1"]
        assert len(tenant.allocation_history) >= 3  # At least 3 successful allocations
        assert tenant.historical_usage > 0

        # Verify market has evolved
        status = marketplace.get_market_status()
        assert status["total_requests_processed"] >= 5  # All requests were processed
        assert status["active_allocations"] <= 5.0


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_allocation_request_validation(self):
        """Test validation of allocation requests."""
        marketplace = AdaptiveDPMarketplace()

        # Try to submit request for unregistered tenant
        request = AllocationRequest("req1", "nonexistent", 1.0, "count_query")

        with pytest.raises(ValueError):
            marketplace.allocate_budget(request)

    def test_budget_calculation_edge_cases(self):
        """Test budget calculation in edge cases."""
        marketplace = AdaptiveDPMarketplace(total_budget=0.0)  # Zero budget

        marketplace.register_tenant("tenant1", "Test Corp")

        request = AllocationRequest("req1", "tenant1", 1.0, "count_query")
        result = marketplace.allocate_budget(request)

        # Should allocate zero budget
        assert result.allocated_epsilon == 0.0

    def test_empty_marketplace_operations(self):
        """Test operations on empty marketplace."""
        marketplace = AdaptiveDPMarketplace()

        # Test status with no tenants
        status = marketplace.get_market_status()
        assert status["registered_tenants"] == 0
        assert status["fairness_index"] == 1.0

        # Test tenant status for non-existent tenant
        tenant_status = marketplace.get_tenant_status("nonexistent")
        assert tenant_status is None


if __name__ == "__main__":
    pytest.main([__file__])
