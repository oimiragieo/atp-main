"""Adapter registry for managing adapter capabilities and registration.

Implements GAP-123: Adapter capability advertisement.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from metrics.registry import ADAPTERS_REGISTERED

logger = logging.getLogger(__name__)


@dataclass
class AdapterCapability:
    """Represents an adapter's advertised capabilities."""

    adapter_id: str
    adapter_type: str
    capabilities: list[str]
    models: list[str]
    max_tokens: int | None = None
    supported_languages: list[str] | None = None
    cost_per_token_micros: int | None = None
    health_endpoint: str | None = None
    version: str | None = None
    metadata: dict[str, Any] | None = None
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    p95_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    requests_per_second: float | None = None
    error_rate: float | None = None
    queue_depth: int | None = None
    memory_usage_mb: float | None = None
    cpu_usage_percent: float | None = None
    uptime_seconds: int | None = None
    last_health_update: float = 0.0

    def update_last_seen(self) -> None:
        """Update the last seen timestamp."""
        self.last_seen = time.time()

    def is_healthy(self, timeout_seconds: int = 300) -> bool:
        """Check if adapter is considered healthy based on last seen time."""
        return (time.time() - self.last_seen) < timeout_seconds


class AdapterRegistry:
    """Registry for managing adapter capabilities and registration."""

    def __init__(self) -> None:
        self._adapters: dict[str, AdapterCapability] = {}
        self._adapter_types: dict[str, list[str]] = {}  # type -> adapter_ids

    def register_capability(self, capability_data: dict[str, Any]) -> bool:
        """Register or update an adapter's capabilities.

        Args:
            capability_data: Dictionary containing capability information

        Returns:
            True if registration was successful, False otherwise
        """
        try:
            # Validate required fields
            required_fields = ["adapter_id", "adapter_type", "capabilities", "models"]
            for field in required_fields:
                if field not in capability_data:
                    logger.error(f"Missing required field: {field}")
                    return False

            adapter_id = capability_data["adapter_id"]
            adapter_type = capability_data["adapter_type"]

            # Create or update capability
            capability = AdapterCapability(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                capabilities=capability_data["capabilities"],
                models=capability_data["models"],
                max_tokens=capability_data.get("max_tokens"),
                supported_languages=capability_data.get("supported_languages"),
                cost_per_token_micros=capability_data.get("cost_per_token_micros"),
                health_endpoint=capability_data.get("health_endpoint"),
                version=capability_data.get("version"),
                metadata=capability_data.get("metadata"),
                registered_at=time.time(),
                last_seen=time.time(),
                p95_latency_ms=capability_data.get("p95_latency_ms"),
                p50_latency_ms=capability_data.get("p50_latency_ms"),
                p99_latency_ms=capability_data.get("p99_latency_ms"),
                requests_per_second=capability_data.get("requests_per_second"),
                error_rate=capability_data.get("error_rate"),
                queue_depth=capability_data.get("queue_depth"),
                memory_usage_mb=capability_data.get("memory_usage_mb"),
                cpu_usage_percent=capability_data.get("cpu_usage_percent"),
                uptime_seconds=capability_data.get("uptime_seconds"),
                last_health_update=time.time()
            )

            # Check if this is a new registration
            is_new = adapter_id not in self._adapters

            self._adapters[adapter_id] = capability

            # Update type index
            if adapter_type not in self._adapter_types:
                self._adapter_types[adapter_type] = []
            if adapter_id not in self._adapter_types[adapter_type]:
                self._adapter_types[adapter_type].append(adapter_id)

            # Update metrics
            ADAPTERS_REGISTERED.set(len(self._adapters))

            if is_new:
                logger.info(f"Registered new adapter: {adapter_id} (type: {adapter_type})")
            else:
                logger.info(f"Updated adapter capabilities: {adapter_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to register adapter capability: {e}")
            return False

    def unregister_adapter(self, adapter_id: str) -> bool:
        """Unregister an adapter.

        Args:
            adapter_id: ID of the adapter to unregister

        Returns:
            True if unregistration was successful, False otherwise
        """
        if adapter_id not in self._adapters:
            logger.warning(f"Attempted to unregister unknown adapter: {adapter_id}")
            return False

        capability = self._adapters[adapter_id]
        adapter_type = capability.adapter_type

        # Remove from main registry
        del self._adapters[adapter_id]

        # Remove from type index
        if adapter_type in self._adapter_types:
            if adapter_id in self._adapter_types[adapter_type]:
                self._adapter_types[adapter_type].remove(adapter_id)
            if not self._adapter_types[adapter_type]:
                del self._adapter_types[adapter_type]

        # Update metrics
        ADAPTERS_REGISTERED.set(len(self._adapters))

        logger.info(f"Unregistered adapter: {adapter_id}")
        return True

    def get_adapter(self, adapter_id: str) -> AdapterCapability | None:
        """Get capability information for a specific adapter."""
        return self._adapters.get(adapter_id)

    def get_adapters_by_type(self, adapter_type: str) -> list[AdapterCapability]:
        """Get all adapters of a specific type."""
        adapter_ids = self._adapter_types.get(adapter_type, [])
        return [self._adapters[aid] for aid in adapter_ids if aid in self._adapters]

    def get_all_adapters(self) -> list[AdapterCapability]:
        """Get all registered adapters."""
        return list(self._adapters.values())

    def get_adapter_types(self) -> list[str]:
        """Get all registered adapter types."""
        return list(self._adapter_types.keys())

    def heartbeat(self, adapter_id: str) -> bool:
        """Update last seen time for an adapter (heartbeat)."""
        if adapter_id not in self._adapters:
            logger.warning(f"Heartbeat from unknown adapter: {adapter_id}")
            return False

        self._adapters[adapter_id].update_last_seen()
        return True

    def cleanup_stale_adapters(self, timeout_seconds: int = 300) -> int:
        """Remove adapters that haven't been seen recently.

        Args:
            timeout_seconds: Time after which an adapter is considered stale

        Returns:
            Number of adapters removed
        """
        current_time = time.time()
        stale_adapters = []

        for adapter_id, capability in self._adapters.items():
            if (current_time - capability.last_seen) > timeout_seconds:
                stale_adapters.append(adapter_id)

        for adapter_id in stale_adapters:
            self.unregister_adapter(adapter_id)

        if stale_adapters:
            logger.info(f"Cleaned up {len(stale_adapters)} stale adapters")

        return len(stale_adapters)

    def update_health_telemetry(self, adapter_id: str, health_data: dict[str, Any]) -> bool:
        """Update health telemetry data for an existing adapter.

        Args:
            adapter_id: ID of the adapter to update
            health_data: Dictionary containing health telemetry data

        Returns:
            True if update was successful, False otherwise
        """
        if adapter_id not in self._adapters:
            logger.warning(f"Attempted to update health for unknown adapter: {adapter_id}")
            return False

        capability = self._adapters[adapter_id]

        # Update health telemetry fields
        if "p95_latency_ms" in health_data:
            capability.p95_latency_ms = health_data["p95_latency_ms"]
        if "p50_latency_ms" in health_data:
            capability.p50_latency_ms = health_data["p50_latency_ms"]
        if "p99_latency_ms" in health_data:
            capability.p99_latency_ms = health_data["p99_latency_ms"]
        if "requests_per_second" in health_data:
            capability.requests_per_second = health_data["requests_per_second"]
        if "error_rate" in health_data:
            capability.error_rate = health_data["error_rate"]
        if "queue_depth" in health_data:
            capability.queue_depth = health_data["queue_depth"]
        if "memory_usage_mb" in health_data:
            capability.memory_usage_mb = health_data["memory_usage_mb"]
        if "cpu_usage_percent" in health_data:
            capability.cpu_usage_percent = health_data["cpu_usage_percent"]
        if "uptime_seconds" in health_data:
            capability.uptime_seconds = health_data["uptime_seconds"]

        capability.last_health_update = time.time()
        capability.last_seen = time.time()  # Also update last seen

        logger.info(f"Updated health telemetry for adapter: {adapter_id}")
        return True


# Global adapter registry instance
_adapter_registry = AdapterRegistry()


def get_adapter_registry() -> AdapterRegistry:
    """Get the global adapter registry instance."""
    return _adapter_registry
