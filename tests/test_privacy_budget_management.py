#!/usr/bin/env python3
"""Test for GAP-221: Privacy Budget Management Tests."""

from tools.privacy_budget_manager import (
    PrivacyBudgetManager,
    PrivacyOperation,
    add_laplace_noise,
    apply_differential_privacy,
)


class TestPrivacyBudgetManagement:
    """Test privacy budget management functionality."""

    def test_budget_allocation(self):
        """Test basic budget allocation."""
        manager = PrivacyBudgetManager(total_epsilon_budget=1.0)

        # Test allocation
        allocation = manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.1, "test_op", "Test operation")

        assert allocation.allocated_epsilon == 0.1
        assert allocation.operation == PrivacyOperation.COUNT_QUERY
        assert allocation.operation_id == "test_op"

        # Check remaining budget
        remaining = manager.get_remaining_budget()
        assert remaining == 0.9

    def test_budget_exhaustion(self):
        """Test budget exhaustion handling."""
        manager = PrivacyBudgetManager(total_epsilon_budget=0.5)

        # First allocation should succeed
        alloc1 = manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.3, "op1")
        assert alloc1.allocated_epsilon == 0.1  # Limited by operation cost

        # Second allocation should be limited
        alloc2 = manager.allocate_budget(PrivacyOperation.MEAN_QUERY, 0.3, "op2")
        assert alloc2.allocated_epsilon == 0.2  # Limited by operation cost

        # Third allocation should succeed (0.1 remaining budget, 0.1 requested)
        alloc3 = manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.1, "op3")
        assert alloc3.allocated_epsilon == 0.1  # Should succeed with remaining budget

    def test_operation_cost_estimation(self):
        """Test operation cost estimation."""
        manager = PrivacyBudgetManager(total_epsilon_budget=2.0)

        # Test different operations have different costs
        count_cost = manager.get_operation_cost_estimate(PrivacyOperation.COUNT_QUERY, 1000)
        mean_cost = manager.get_operation_cost_estimate(PrivacyOperation.MEAN_QUERY, 1000)
        fed_cost = manager.get_operation_cost_estimate(PrivacyOperation.FEDERATION_AGGREGATION, 1000)

        assert count_cost < mean_cost < fed_cost

    def test_differential_privacy_noise(self):
        """Test differential privacy noise injection."""
        # Test Laplace noise generation
        value = 100.0
        sensitivity = 1.0
        epsilon = 0.5

        # Generate multiple noisy values
        noisy_values = []
        for _ in range(10):
            noisy = add_laplace_noise(value, sensitivity, epsilon)
            noisy_values.append(noisy)

        # Check that noise is added (values should vary)
        assert len(set(noisy_values)) > 1

        # Check that values are reasonably close to original
        for noisy in noisy_values:
            assert 90 < noisy < 110  # Within expected noise range

    def test_privacy_application_to_dataset(self):
        """Test applying differential privacy to a dataset."""
        test_data = {"requests": 1000, "latency": 500.0, "success_rate": 0.95}

        # Apply DP with reasonable epsilon
        privatized = apply_differential_privacy(test_data, epsilon=0.5)

        # Check that all keys are preserved
        assert set(privatized.keys()) == set(test_data.keys())

        # Check that values are reasonably close
        assert abs(privatized["requests"] - test_data["requests"]) < 100
        assert abs(privatized["latency"] - test_data["latency"]) < 50
        assert abs(privatized["success_rate"] - test_data["success_rate"]) < 0.1

    def test_budget_utilization_tracking(self):
        """Test budget utilization tracking."""
        manager = PrivacyBudgetManager(total_epsilon_budget=1.0)

        # Allocate some budget
        manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.1, "op1")
        manager.allocate_budget(PrivacyOperation.MEAN_QUERY, 0.2, "op2")

        # Check utilization
        utilization = manager.get_budget_utilization()

        assert utilization["total_budget"] == 1.0
        assert abs(utilization["spent_epsilon"] - 0.3) < 1e-10  # 0.1 + 0.2
        assert abs(utilization["remaining_budget"] - 0.7) < 1e-10
        assert abs(utilization["utilization_rate"] - 0.3) < 1e-10
        assert utilization["active_allocations"] == 2

    def test_allocation_release(self):
        """Test releasing budget allocations."""
        manager = PrivacyBudgetManager(total_epsilon_budget=1.0)

        # Allocate budget
        manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.1, "test_op")

        # Verify allocation exists
        status = manager.get_allocation_status("test_op")
        assert status is not None
        assert status.allocated_epsilon == 0.1

        # Release allocation
        released = manager.release_allocation("test_op")
        assert released is True

        # Verify budget is restored
        remaining = manager.get_remaining_budget()
        assert remaining == 1.0

        # Verify allocation is gone
        status = manager.get_allocation_status("test_op")
        assert status is None

    def test_zero_epsilon_handling(self):
        """Test handling of zero epsilon (no privacy)."""
        test_data = {"value": 100.0}

        # With zero epsilon, should return original data
        result = apply_differential_privacy(test_data, epsilon=0.0)
        assert result == test_data

        # With very small epsilon, should still work
        result = apply_differential_privacy(test_data, epsilon=0.001)
        assert "value" in result
        assert isinstance(result["value"], float)
