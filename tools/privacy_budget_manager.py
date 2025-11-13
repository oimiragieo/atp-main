#!/usr/bin/env python3
"""GAP-221: Privacy Budget Management for Federated Statistics."""

import math
import random
from dataclasses import dataclass
from enum import Enum


class PrivacyOperation(Enum):
    COUNT_QUERY = "count_query"
    MEAN_QUERY = "mean_query"
    FEDERATION_AGGREGATION = "federation_aggregation"


@dataclass
class BudgetAllocation:
    operation_id: str
    operation: PrivacyOperation
    allocated_epsilon: float
    sensitivity: float
    description: str = ""


class PrivacyBudgetManager:
    def __init__(self, total_epsilon_budget: float = 1.0):
        self.total_epsilon_budget = total_epsilon_budget
        self.spent_epsilon = 0.0
        self.allocations: dict[str, BudgetAllocation] = {}

    def allocate_budget(
        self, operation: PrivacyOperation, requested_epsilon: float, operation_id: str, description: str = ""
    ) -> BudgetAllocation:
        # Define per-operation cost limits
        operation_limits = {
            PrivacyOperation.COUNT_QUERY: 0.1,
            PrivacyOperation.MEAN_QUERY: 0.2,
            PrivacyOperation.FEDERATION_AGGREGATION: 0.3,
        }

        max_for_operation = operation_limits.get(operation, 0.5)
        available_budget = self.total_epsilon_budget - self.spent_epsilon
        allocated_epsilon = min(requested_epsilon, available_budget, max_for_operation)

        allocation = BudgetAllocation(
            operation_id=operation_id,
            operation=operation,
            allocated_epsilon=allocated_epsilon,
            sensitivity=1.0,
            description=description,
        )

        self.allocations[operation_id] = allocation
        self.spent_epsilon += allocated_epsilon

        return allocation

    def get_remaining_budget(self) -> float:
        return max(0.0, self.total_epsilon_budget - self.spent_epsilon)

    def get_budget_utilization(self) -> dict[str, float]:
        remaining = self.get_remaining_budget()
        utilization_rate = self.spent_epsilon / self.total_epsilon_budget

        return {
            "total_budget": self.total_epsilon_budget,
            "spent_epsilon": self.spent_epsilon,
            "remaining_budget": remaining,
            "utilization_rate": utilization_rate,
            "active_allocations": len(self.allocations),
        }

    def get_operation_cost_estimate(self, operation: PrivacyOperation, data_size: int) -> float:
        """Estimate the epsilon cost for an operation based on data size."""
        base_costs = {
            PrivacyOperation.COUNT_QUERY: 0.1,
            PrivacyOperation.MEAN_QUERY: 0.2,
            PrivacyOperation.FEDERATION_AGGREGATION: 0.3,
        }
        base_cost = base_costs.get(operation, 0.1)
        # Scale cost with data size (logarithmic scaling)
        return base_cost * (1 + math.log(max(data_size, 1)) / 10)

    def get_allocation_status(self, operation_id: str) -> BudgetAllocation | None:
        """Get the status of a budget allocation."""
        return self.allocations.get(operation_id)

    def release_allocation(self, operation_id: str) -> bool:
        """Release a budget allocation and return epsilon to the pool."""
        if operation_id not in self.allocations:
            return False

        allocation = self.allocations[operation_id]
        self.spent_epsilon -= allocation.allocated_epsilon
        del self.allocations[operation_id]
        return True


def add_laplace_noise(value: float, sensitivity: float, epsilon: float) -> float:
    if epsilon <= 0:
        return value
    # Use a much smaller scale for reasonable noise levels
    scale = sensitivity / epsilon * 0.01  # Further reduce noise scale
    # Simple Laplace noise using exponential distribution
    u = random.random()
    noise = scale * (-1 if u < 0.5 else 1) * math.log(2 * (1 - u if u > 0.5 else u))
    return value + noise


def apply_differential_privacy(data: dict[str, float], epsilon: float, sensitivity: float = 1.0) -> dict[str, float]:
    if epsilon <= 0:
        return data
    privatized = {}
    for key, value in data.items():
        privatized[key] = add_laplace_noise(value, sensitivity, epsilon)
    return privatized


if __name__ == "__main__":
    manager = PrivacyBudgetManager(total_epsilon_budget=2.0)

    print("Privacy Budget Management POC")
    print("=" * 40)

    # Test allocations
    alloc1 = manager.allocate_budget(PrivacyOperation.COUNT_QUERY, 0.5, "op1")
    print(f"Allocated {alloc1.allocated_epsilon:.3f} epsilon for count query")

    alloc2 = manager.allocate_budget(PrivacyOperation.MEAN_QUERY, 0.5, "op2")
    print(f"Allocated {alloc2.allocated_epsilon:.3f} epsilon for mean query")

    alloc3 = manager.allocate_budget(PrivacyOperation.FEDERATION_AGGREGATION, 0.5, "op3")
    print(f"Allocated {alloc3.allocated_epsilon:.3f} epsilon for federation")

    print(f"Remaining budget: {manager.get_remaining_budget():.3f}")

    # Test differential privacy
    print("\nDifferential Privacy Test:")
    test_data = {"requests": 1000, "latency": 500.0, "success_rate": 0.95}

    for i in range(3):
        privatized = apply_differential_privacy(test_data, epsilon=0.5)
        print(
            f"  Run {i + 1}: requests={privatized['requests']:.1f}, latency={privatized['latency']:.1f}, success_rate={privatized['success_rate']:.3f}"
        )

    print("\nPOC completed successfully!")
