#!/usr/bin/env python3
"""GAP-270: Adaptive DP Allocation Marketplace for Multi-Tenant Privacy Budget Management."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AllocationStrategy(Enum):
    """Allocation strategies for privacy budget distribution."""

    PROPORTIONAL_FAIR = "proportional_fair"
    PRIORITY_BASED = "priority_based"
    DEMAND_DRIVEN = "demand_driven"
    AUCTION_BASED = "auction_based"


class TenantPriority(Enum):
    """Tenant priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TenantProfile:
    """Profile for a tenant in the marketplace."""

    tenant_id: str
    name: str
    priority: TenantPriority = TenantPriority.MEDIUM
    historical_usage: float = 0.0
    current_allocation: float = 0.0
    fairness_score: float = 1.0
    last_allocation_time: datetime | None = None
    allocation_history: list[float] = field(default_factory=list)


@dataclass
class AllocationRequest:
    """Request for privacy budget allocation."""

    request_id: str
    tenant_id: str
    requested_epsilon: float
    operation_type: str
    data_sensitivity: float = 1.0
    urgency_level: int = 1  # 1-5 scale
    max_wait_time: int = 300  # seconds
    submitted_at: datetime = field(default_factory=datetime.now)
    bid_amount: float = 0.0  # For auction-based allocation


@dataclass
class AllocationResult:
    """Result of an allocation request."""

    request_id: str
    tenant_id: str
    allocated_epsilon: float
    allocation_strategy: AllocationStrategy
    allocated_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    fairness_adjustment: float = 1.0


class AdaptiveDPMarketplace:
    """Adaptive Differential Privacy Allocation Marketplace."""

    def __init__(
        self,
        total_budget: float = 10.0,
        allocation_window: int = 3600,  # 1 hour
        strategy: AllocationStrategy = AllocationStrategy.PROPORTIONAL_FAIR,
    ):
        self.total_budget = total_budget
        self.allocation_window = allocation_window
        self.strategy = strategy

        # Core data structures
        self.tenants: dict[str, TenantProfile] = {}
        self.active_allocations: dict[str, AllocationResult] = {}
        self.pending_requests: list[AllocationRequest] = []
        self.allocation_history: list[AllocationResult] = []

        # Market dynamics
        self.market_pressure: float = 1.0  # Demand/supply ratio
        self.fairness_weights: dict[str, float] = {}
        self.strategy_metrics: dict[str, Any] = {}

        # Initialize marketplace
        self._initialize_marketplace()

    def _initialize_marketplace(self):
        """Initialize marketplace with default settings."""
        self.strategy_metrics = {
            "total_requests_processed": 0,
            "allocation_success_rate": 0.0,
            "average_wait_time": 0.0,
            "fairness_index": 1.0,
            "market_efficiency": 0.0,
        }

    def register_tenant(self, tenant_id: str, name: str, priority: TenantPriority = TenantPriority.MEDIUM) -> bool:
        """Register a new tenant in the marketplace."""
        if tenant_id in self.tenants:
            return False

        self.tenants[tenant_id] = TenantProfile(tenant_id=tenant_id, name=name, priority=priority)

        # Initialize fairness weight
        self.fairness_weights[tenant_id] = 1.0
        return True

    def submit_allocation_request(self, request: AllocationRequest) -> str:
        """Submit an allocation request to the marketplace."""
        if request.tenant_id not in self.tenants:
            raise ValueError(f"Tenant {request.tenant_id} not registered")

        self.pending_requests.append(request)
        self.strategy_metrics["total_requests_processed"] += 1

        # Trigger allocation if using demand-driven strategy
        if self.strategy == AllocationStrategy.DEMAND_DRIVEN:
            self._process_pending_requests()

        return request.request_id

    def allocate_budget(self, request: AllocationRequest) -> AllocationResult:
        """Allocate budget using the configured strategy."""
        if request.tenant_id not in self.tenants:
            raise ValueError(f"Tenant {request.tenant_id} not registered")

        tenant = self.tenants[request.tenant_id]
        available_budget = self._calculate_available_budget()

        if available_budget <= 0:
            result = AllocationResult(
                request_id=request.request_id,
                tenant_id=request.tenant_id,
                allocated_epsilon=0.0,
                allocation_strategy=self.strategy,
            )
            # Record failed allocation
            self.allocation_history.append(result)
            self.strategy_metrics["total_requests_processed"] += 1
            return result

        allocated_epsilon = 0.0

        if self.strategy == AllocationStrategy.PROPORTIONAL_FAIR:
            allocated_epsilon = self._allocate_proportional_fair(request, available_budget)
        elif self.strategy == AllocationStrategy.PRIORITY_BASED:
            allocated_epsilon = self._allocate_priority_based(request, available_budget)
        elif self.strategy == AllocationStrategy.DEMAND_DRIVEN:
            allocated_epsilon = self._allocate_demand_driven(request, available_budget)
        elif self.strategy == AllocationStrategy.AUCTION_BASED:
            allocated_epsilon = self._allocate_auction_based(request, available_budget)

        # Apply fairness adjustment
        fairness_factor = self._calculate_fairness_adjustment(request.tenant_id)
        allocated_epsilon *= fairness_factor

        # Cap at requested amount and available budget
        # For proportional fair, allow up to 2x requested amount if market has capacity
        if self.strategy == AllocationStrategy.PROPORTIONAL_FAIR:
            max_allocation = min(request.requested_epsilon * 2.0, available_budget)
        else:
            max_allocation = min(request.requested_epsilon, available_budget)

        allocated_epsilon = min(allocated_epsilon, max_allocation)

        result = AllocationResult(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            allocated_epsilon=allocated_epsilon,
            allocation_strategy=self.strategy,
            fairness_adjustment=fairness_factor,
        )

        # Update tenant state
        self._update_tenant_allocation(tenant, allocated_epsilon)

        # Record allocation
        self.active_allocations[request.request_id] = result
        self.allocation_history.append(result)
        self.strategy_metrics["total_requests_processed"] += 1

        return result

    def _allocate_proportional_fair(self, request: AllocationRequest, available_budget: float) -> float:
        """Proportional fair allocation based on tenant usage history."""
        tenant = self.tenants[request.tenant_id]

        # Calculate proportional share based on historical usage
        total_historical_usage = sum(t.historical_usage for t in self.tenants.values())
        if total_historical_usage == 0:
            # Equal share for new tenants
            tenant_count = len(self.tenants)
            return min(available_budget / tenant_count, request.requested_epsilon)

        # Proportional to inverse of historical usage (fairness)
        tenant_share = (1.0 / (1.0 + tenant.historical_usage)) / sum(
            1.0 / (1.0 + t.historical_usage) for t in self.tenants.values()
        )

        return tenant_share * available_budget

    def _allocate_priority_based(self, request: AllocationRequest, available_budget: float) -> float:
        """Priority-based allocation favoring high-priority tenants."""
        tenant = self.tenants[request.tenant_id]

        # Priority multipliers
        priority_multipliers = {
            TenantPriority.LOW: 0.5,
            TenantPriority.MEDIUM: 1.0,
            TenantPriority.HIGH: 2.0,
            TenantPriority.CRITICAL: 3.0,
        }

        base_allocation = available_budget * 0.1  # Base 10% of available
        priority_multiplier = priority_multipliers[tenant.priority]

        return min(base_allocation * priority_multiplier, request.requested_epsilon)

    def _allocate_demand_driven(self, request: AllocationRequest, available_budget: float) -> float:
        """Demand-driven allocation based on request urgency and market pressure."""
        urgency_factor = request.urgency_level / 5.0  # Normalize to 0-1
        market_factor = min(self.market_pressure, 2.0)  # Cap at 2x

        base_allocation = available_budget * 0.2  # Base 20% of available
        demand_allocation = base_allocation * urgency_factor * market_factor

        return min(demand_allocation, request.requested_epsilon)

    def _allocate_auction_based(self, request: AllocationRequest, available_budget: float) -> float:
        """Auction-based allocation using bid amounts."""
        if request.bid_amount <= 0:
            return 0.0

        # Simple auction: higher bids get more allocation
        # In a real implementation, this would compare against other bids
        bid_factor = min(request.bid_amount / 10.0, 2.0)  # Normalize bid amount

        return min(available_budget * bid_factor * 0.1, request.requested_epsilon)

    def _calculate_fairness_adjustment(self, tenant_id: str) -> float:
        """Calculate fairness adjustment factor for a tenant."""
        tenant = self.tenants[tenant_id]

        # Adjust based on recent allocation history
        if len(tenant.allocation_history) < 3:
            return 1.0  # No adjustment for new tenants

        recent_avg = sum(tenant.allocation_history[-3:]) / 3
        overall_avg = sum(tenant.allocation_history) / len(tenant.allocation_history)

        # More sensitive fairness adjustment
        if recent_avg < overall_avg * 0.9:  # Changed from 0.8 to 0.9
            # Under-allocated recently, boost allocation
            return 1.3  # Increased from 1.2
        elif recent_avg > overall_avg * 1.1:  # Changed from 1.2 to 1.1
            # Over-allocated recently, reduce allocation
            return 0.8  # Changed from 0.9

        return 1.0

    def _calculate_available_budget(self) -> float:
        """Calculate currently available budget."""
        active_allocation_total = sum(result.allocated_epsilon for result in self.active_allocations.values())
        return max(0.0, self.total_budget - active_allocation_total)

    def _update_tenant_allocation(self, tenant: TenantProfile, allocated_epsilon: float):
        """Update tenant allocation tracking."""
        tenant.current_allocation += allocated_epsilon
        tenant.allocation_history.append(allocated_epsilon)
        tenant.last_allocation_time = datetime.now()

        # Update historical usage (exponential moving average)
        alpha = 0.1  # Smoothing factor
        tenant.historical_usage = (1 - alpha) * tenant.historical_usage + alpha * allocated_epsilon

        # Update fairness score
        tenant.fairness_score = self._calculate_tenant_fairness(tenant)

    def _calculate_tenant_fairness(self, tenant: TenantProfile) -> float:
        """Calculate fairness score for a tenant."""
        if not tenant.allocation_history:
            return 1.0

        # Fairness based on allocation variance
        if len(tenant.allocation_history) < 2:
            return 1.0

        mean_allocation = sum(tenant.allocation_history) / len(tenant.allocation_history)
        variance = sum((x - mean_allocation) ** 2 for x in tenant.allocation_history) / len(tenant.allocation_history)
        std_dev = math.sqrt(variance)

        # Lower variance = higher fairness score
        fairness = max(0.1, 1.0 - (std_dev / (mean_allocation + 1e-6)))
        return fairness

    def _process_pending_requests(self):
        """Process pending allocation requests."""
        # Sort by priority/urgency for demand-driven allocation
        if self.strategy == AllocationStrategy.DEMAND_DRIVEN:
            self.pending_requests.sort(key=lambda r: (r.urgency_level, r.submitted_at), reverse=True)

        # Process requests in order
        for request in self.pending_requests[:]:
            try:
                result = self.allocate_budget(request)
                if result.allocated_epsilon > 0:
                    self.pending_requests.remove(request)
            except Exception as e:
                # Log error but continue processing
                logging.error(f"Error processing allocation request {request.request_id}: {e}")
                continue

    def release_allocation(self, request_id: str) -> bool:
        """Release an active allocation."""
        if request_id not in self.active_allocations:
            return False

        result = self.active_allocations[request_id]
        tenant = self.tenants[result.tenant_id]
        tenant.current_allocation -= result.allocated_epsilon

        del self.active_allocations[request_id]
        return True

    def get_market_status(self) -> dict[str, Any]:
        """Get comprehensive market status."""
        available_budget = self._calculate_available_budget()
        active_allocation_total = sum(result.allocated_epsilon for result in self.active_allocations.values())

        # Calculate fairness index across all tenants
        if self.tenants:
            fairness_scores = [t.fairness_score for t in self.tenants.values()]
            fairness_index = sum(fairness_scores) / len(fairness_scores)
        else:
            fairness_index = 1.0

        return {
            "total_budget": self.total_budget,
            "available_budget": available_budget,
            "active_allocations": active_allocation_total,
            "utilization_rate": active_allocation_total / self.total_budget,
            "pending_requests": len(self.pending_requests),
            "registered_tenants": len(self.tenants),
            "allocation_strategy": self.strategy.value,
            "fairness_index": fairness_index,
            "market_pressure": self.market_pressure,
            "total_requests_processed": self.strategy_metrics["total_requests_processed"],
            "strategy_metrics": self.strategy_metrics,
        }

    def get_tenant_status(self, tenant_id: str) -> dict[str, Any] | None:
        """Get status for a specific tenant."""
        if tenant_id not in self.tenants:
            return None

        tenant = self.tenants[tenant_id]
        active_allocations = [result for result in self.active_allocations.values() if result.tenant_id == tenant_id]

        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "priority": tenant.priority.name,  # Return string name instead of enum value
            "current_allocation": tenant.current_allocation,
            "historical_usage": tenant.historical_usage,
            "fairness_score": tenant.fairness_score,
            "active_allocations_count": len(active_allocations),
            "last_allocation_time": tenant.last_allocation_time.isoformat() if tenant.last_allocation_time else None,
        }

    def update_market_pressure(self):
        """Update market pressure based on demand patterns."""
        if not self.tenants:
            self.market_pressure = 1.0
            return

        # Calculate demand vs supply ratio
        pending_demand = sum(r.requested_epsilon for r in self.pending_requests)
        available_supply = self._calculate_available_budget()

        if available_supply == 0:
            self.market_pressure = 10.0  # High pressure
        else:
            # More sensitive pressure calculation
            base_pressure = pending_demand / available_supply
            # Add pressure from pending request count
            queue_pressure = len(self.pending_requests) / max(1, len(self.tenants))
            self.market_pressure = base_pressure + queue_pressure
            self.market_pressure = max(0.1, min(self.market_pressure, 5.0))  # Clamp to reasonable range

    def optimize_allocation_strategy(self):
        """Dynamically optimize allocation strategy based on market conditions."""
        status = self.get_market_status()

        # Switch strategies based on market conditions
        if (status["utilization_rate"] > 0.9 or len(self.pending_requests) > 5) and len(self.pending_requests) > 0:
            # High utilization or high demand - switch to priority-based
            if self.strategy != AllocationStrategy.PRIORITY_BASED:
                self.strategy = AllocationStrategy.PRIORITY_BASED
        elif status["fairness_index"] < 0.7:
            # Low fairness - switch to proportional fair
            if self.strategy != AllocationStrategy.PROPORTIONAL_FAIR:
                self.strategy = AllocationStrategy.PROPORTIONAL_FAIR
        elif len(self.pending_requests) > 10:
            # High demand - switch to demand-driven
            if self.strategy != AllocationStrategy.DEMAND_DRIVEN:
                self.strategy = AllocationStrategy.DEMAND_DRIVEN


def main():
    """Demonstrate the Adaptive DP Allocation Marketplace."""
    print("Adaptive DP Allocation Marketplace POC")
    print("=" * 50)

    # Initialize marketplace
    marketplace = AdaptiveDPMarketplace(total_budget=5.0)

    # Register tenants
    tenants = [
        ("tenant_a", "Analytics Corp", TenantPriority.HIGH),
        ("tenant_b", "Research Lab", TenantPriority.MEDIUM),
        ("tenant_c", "Startup Inc", TenantPriority.LOW),
    ]

    for tenant_id, name, priority in tenants:
        marketplace.register_tenant(tenant_id, name, priority)
        print(f"Registered tenant: {name} ({priority.value})")

    print(f"\nMarket Status: {marketplace.get_market_status()}")

    # Submit allocation requests
    requests = [
        AllocationRequest("req1", "tenant_a", 1.0, "count_query", urgency_level=4),
        AllocationRequest("req2", "tenant_b", 0.8, "mean_query", urgency_level=3),
        AllocationRequest("req3", "tenant_c", 0.5, "federation", urgency_level=2),
        AllocationRequest("req4", "tenant_a", 0.7, "count_query", urgency_level=5),
    ]

    print("\nProcessing Allocation Requests:")
    for request in requests:
        result = marketplace.allocate_budget(request)
        tenant_name = marketplace.tenants[request.tenant_id].name
        print(
            f"  {tenant_name}: requested {request.requested_epsilon:.1f}, "
            f"allocated {result.allocated_epsilon:.3f} (fairness: {result.fairness_adjustment:.2f})"
        )

    print(f"\nFinal Market Status: {marketplace.get_market_status()}")

    # Show tenant statuses
    print("\nTenant Status Summary:")
    for tenant_id in marketplace.tenants:
        status = marketplace.get_tenant_status(tenant_id)
        if status:
            print(
                f"  {status['name']}: allocation={status['current_allocation']:.3f}, "
                f"fairness={status['fairness_score']:.3f}"
            )

    print("\nPOC completed successfully!")


if __name__ == "__main__":
    main()
