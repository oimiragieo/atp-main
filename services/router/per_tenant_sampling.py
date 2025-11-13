"""Per-tenant dynamic sampling policies (GAP-366).

Extends error-budget aware tail sampling to support tenant-specific sampling
policies. Each tenant can have different base sampling rates, error budget
thresholds, and sampling behavior based on their specific needs and SLOs.
"""

from __future__ import annotations

import logging

from .error_budget_tail_sampler import ErrorBudgetAwareTailSampler

logger = logging.getLogger(__name__)


class TenantSamplingPolicy:
    """Configuration for a tenant's sampling policy."""

    def __init__(
        self,
        tenant_id: str,
        base_sampling_rate: float = 0.1,
        max_sampling_rate: float = 1.0,
        window_size_minutes: int = 10,
        high_consumption_threshold: float = 50.0,
        high_error_rate_threshold: float = 5.0,
        adjustment_factor: float = 2.0,
        enabled: bool = True,
    ):
        self.tenant_id = tenant_id
        self.base_sampling_rate = base_sampling_rate
        self.max_sampling_rate = max_sampling_rate
        self.window_size_minutes = window_size_minutes
        self.high_consumption_threshold = high_consumption_threshold
        self.high_error_rate_threshold = high_error_rate_threshold
        self.adjustment_factor = adjustment_factor
        self.enabled = enabled

    def to_dict(self) -> dict:
        """Convert policy to dictionary for serialization."""
        return {
            "tenant_id": self.tenant_id,
            "base_sampling_rate": self.base_sampling_rate,
            "max_sampling_rate": self.max_sampling_rate,
            "window_size_minutes": self.window_size_minutes,
            "high_consumption_threshold": self.high_consumption_threshold,
            "high_error_rate_threshold": self.high_error_rate_threshold,
            "adjustment_factor": self.adjustment_factor,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TenantSamplingPolicy:
        """Create policy from dictionary."""
        return cls(
            tenant_id=data["tenant_id"],
            base_sampling_rate=data.get("base_sampling_rate", 0.1),
            max_sampling_rate=data.get("max_sampling_rate", 1.0),
            window_size_minutes=data.get("window_size_minutes", 10),
            high_consumption_threshold=data.get("high_consumption_threshold", 50.0),
            high_error_rate_threshold=data.get("high_error_rate_threshold", 5.0),
            adjustment_factor=data.get("adjustment_factor", 2.0),
            enabled=data.get("enabled", True),
        )


class PerTenantSamplingManager:
    """Manages per-tenant sampling policies and samplers."""

    def __init__(self):
        self._policies: dict[str, TenantSamplingPolicy] = {}
        self._samplers: dict[str, ErrorBudgetAwareTailSampler] = {}
        self._default_policy = TenantSamplingPolicy("default")

    def add_tenant_policy(self, policy: TenantSamplingPolicy) -> None:
        """Add or update a tenant's sampling policy."""
        self._policies[policy.tenant_id] = policy

        # Create or update the sampler for this tenant
        if policy.enabled:
            sampler = ErrorBudgetAwareTailSampler(
                base_sampling_rate=policy.base_sampling_rate,
                max_sampling_rate=policy.max_sampling_rate,
                window_size_minutes=policy.window_size_minutes,
                high_consumption_threshold=policy.high_consumption_threshold,
                high_error_rate_threshold=policy.high_error_rate_threshold,
                adjustment_factor=policy.adjustment_factor,
            )
            self._samplers[policy.tenant_id] = sampler
        else:
            # Remove sampler if policy is disabled
            self._samplers.pop(policy.tenant_id, None)

        logger.info(f"Updated sampling policy for tenant {policy.tenant_id}")

    def get_tenant_policy(self, tenant_id: str) -> TenantSamplingPolicy:
        """Get the sampling policy for a tenant."""
        return self._policies.get(tenant_id, self._default_policy)

    def get_tenant_sampler(self, tenant_id: str) -> ErrorBudgetAwareTailSampler:
        """Get the error budget aware sampler for a tenant."""
        if tenant_id not in self._samplers:
            # Create sampler with default policy if not exists
            policy = self.get_tenant_policy(tenant_id)
            if policy.enabled:
                sampler = ErrorBudgetAwareTailSampler(
                    base_sampling_rate=policy.base_sampling_rate,
                    max_sampling_rate=policy.max_sampling_rate,
                    window_size_minutes=policy.window_size_minutes,
                    high_consumption_threshold=policy.high_consumption_threshold,
                    high_error_rate_threshold=policy.high_error_rate_threshold,
                    adjustment_factor=policy.adjustment_factor,
                )
                self._samplers[tenant_id] = sampler
            else:
                # Return a disabled sampler (always returns base rate)
                sampler = ErrorBudgetAwareTailSampler(
                    base_sampling_rate=policy.base_sampling_rate,
                    max_sampling_rate=policy.base_sampling_rate,  # Same as base to disable adjustment
                )
                self._samplers[tenant_id] = sampler

        return self._samplers[tenant_id]

    def record_tenant_error_budget(
        self, tenant_id: str, budget_consumed_percent: float, error_rate_percent: float
    ) -> None:
        """Record error budget measurement for a specific tenant."""
        sampler = self.get_tenant_sampler(tenant_id)
        sampler.record_error_budget_measurement(budget_consumed_percent, error_rate_percent)

    def should_sample_for_tenant(self, tenant_id: str) -> bool:
        """Determine if a trace should be sampled for the given tenant."""
        sampler = self.get_tenant_sampler(tenant_id)
        return sampler.should_sample()

    def get_tenant_sampling_rate(self, tenant_id: str) -> float:
        """Get the current sampling rate for a tenant."""
        sampler = self.get_tenant_sampler(tenant_id)
        return sampler.get_current_sampling_rate()

    def get_all_policies(self) -> dict[str, TenantSamplingPolicy]:
        """Get all tenant policies."""
        return self._policies.copy()

    def remove_tenant_policy(self, tenant_id: str) -> None:
        """Remove a tenant's sampling policy."""
        self._policies.pop(tenant_id, None)
        self._samplers.pop(tenant_id, None)
        logger.info(f"Removed sampling policy for tenant {tenant_id}")

    def load_policies_from_config(self, config: dict) -> None:
        """Load tenant policies from configuration dictionary."""
        tenant_policies = config.get("tenant_sampling_policies", {})

        for tenant_id, policy_data in tenant_policies.items():
            policy = TenantSamplingPolicy.from_dict({"tenant_id": tenant_id, **policy_data})
            self.add_tenant_policy(policy)

        logger.info(f"Loaded {len(tenant_policies)} tenant sampling policies from config")


# Global instance
_tenant_sampling_manager: PerTenantSamplingManager | None = None


def get_tenant_sampling_manager() -> PerTenantSamplingManager:
    """Get the global per-tenant sampling manager."""
    global _tenant_sampling_manager
    if _tenant_sampling_manager is None:
        _tenant_sampling_manager = PerTenantSamplingManager()
    return _tenant_sampling_manager


def init_per_tenant_sampling(config: dict | None = None) -> PerTenantSamplingManager:
    """Initialize the global per-tenant sampling manager."""
    global _tenant_sampling_manager
    _tenant_sampling_manager = PerTenantSamplingManager()

    if config:
        _tenant_sampling_manager.load_policies_from_config(config)

    return _tenant_sampling_manager


def should_sample_for_tenant(tenant_id: str) -> bool:
    """Determine if a trace should be sampled for the given tenant."""
    manager = get_tenant_sampling_manager()
    return manager.should_sample_for_tenant(tenant_id)


def record_tenant_error_budget(tenant_id: str, budget_consumed_percent: float, error_rate_percent: float) -> None:
    """Record error budget measurement for a specific tenant."""
    manager = get_tenant_sampling_manager()
    manager.record_tenant_error_budget(tenant_id, budget_consumed_percent, error_rate_percent)
