# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Adapter registry - manages LLM provider adapters."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AdapterInfo:
    """Information about a registered adapter."""

    adapter_id: str
    adapter_type: str
    capabilities: list[str]
    models: list[str]
    endpoint: str | None = None
    max_tokens: int | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Health tracking
    is_healthy: bool = True
    last_health_check: float = field(default_factory=time.time)
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    error_rate: float = 0.0
    requests_per_second: float = 0.0


class AdapterRegistry:
    """
    Registry for LLM provider adapters.

    Tracks adapter capabilities, health status, and performance metrics.
    Supports dynamic adapter registration and discovery.
    """

    def __init__(self):
        self._adapters: dict[str, AdapterInfo] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        adapter_id: str,
        adapter_type: str,
        capabilities: list[str],
        models: list[str],
        endpoint: str | None = None,
        max_tokens: int | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register an adapter.

        Args:
            adapter_id: Unique adapter identifier
            adapter_type: Type of adapter (anthropic, openai, etc.)
            capabilities: List of capabilities
            models: List of supported models
            endpoint: Optional endpoint URL
            max_tokens: Optional max tokens
            version: Optional version
            metadata: Optional metadata
        """
        async with self._lock:
            adapter_info = AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                capabilities=capabilities,
                models=models,
                endpoint=endpoint,
                max_tokens=max_tokens,
                version=version,
                metadata=metadata or {},
            )

            self._adapters[adapter_id] = adapter_info

            logger.info(
                "Adapter registered",
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                models=models,
            )

    async def unregister(self, adapter_id: str) -> bool:
        """
        Unregister an adapter.

        Args:
            adapter_id: The adapter to unregister

        Returns:
            True if adapter was unregistered, False if not found
        """
        async with self._lock:
            if adapter_id in self._adapters:
                del self._adapters[adapter_id]
                logger.info("Adapter unregistered", adapter_id=adapter_id)
                return True

            logger.warning("Adapter not found for unregistration", adapter_id=adapter_id)
            return False

    async def update_health(
        self,
        adapter_id: str,
        is_healthy: bool,
        p50_latency_ms: float | None = None,
        p95_latency_ms: float | None = None,
        error_rate: float | None = None,
        requests_per_second: float | None = None,
    ) -> None:
        """
        Update adapter health status.

        Args:
            adapter_id: The adapter to update
            is_healthy: Whether adapter is healthy
            p50_latency_ms: P50 latency in milliseconds
            p95_latency_ms: P95 latency in milliseconds
            error_rate: Error rate (0.0 to 1.0)
            requests_per_second: Requests per second
        """
        async with self._lock:
            if adapter_id not in self._adapters:
                logger.warning("Adapter not found for health update", adapter_id=adapter_id)
                return

            adapter = self._adapters[adapter_id]
            adapter.is_healthy = is_healthy
            adapter.last_health_check = time.time()

            if p50_latency_ms is not None:
                adapter.p50_latency_ms = p50_latency_ms
            if p95_latency_ms is not None:
                adapter.p95_latency_ms = p95_latency_ms
            if error_rate is not None:
                adapter.error_rate = error_rate
            if requests_per_second is not None:
                adapter.requests_per_second = requests_per_second

            logger.debug(
                "Adapter health updated",
                adapter_id=adapter_id,
                is_healthy=is_healthy,
                p95_latency_ms=p95_latency_ms,
            )

    def get(self, adapter_id: str) -> AdapterInfo | None:
        """Get adapter information."""
        return self._adapters.get(adapter_id)

    def get_all(self) -> list[AdapterInfo]:
        """Get all registered adapters."""
        return list(self._adapters.values())

    async def get_healthy_adapters(self) -> list[AdapterInfo]:
        """Get all healthy adapters."""
        async with self._lock:
            return [adapter for adapter in self._adapters.values() if adapter.is_healthy]

    async def get_adapters_by_type(self, adapter_type: str) -> list[AdapterInfo]:
        """Get all adapters of a specific type."""
        async with self._lock:
            return [adapter for adapter in self._adapters.values() if adapter.adapter_type == adapter_type]

    async def get_adapters_with_capability(self, capability: str) -> list[AdapterInfo]:
        """Get all adapters with a specific capability."""
        async with self._lock:
            return [adapter for adapter in self._adapters.values() if capability in adapter.capabilities]

    def count(self) -> int:
        """Get total number of registered adapters."""
        return len(self._adapters)

    async def count_healthy(self) -> int:
        """Get number of healthy adapters."""
        healthy = await self.get_healthy_adapters()
        return len(healthy)
