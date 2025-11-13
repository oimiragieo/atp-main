# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Observation service - replaces global observation buffer."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Observation

logger = logging.getLogger(__name__)


class ObservationService:
    """
    Service for logging and managing observations.

    Replaces the global _OBS_BUFFER with a proper service.
    Thread-safe and async-compatible.
    """

    def __init__(self, buffer_size: int = 10000):
        self._buffer: list[Observation] = []
        self._lock = asyncio.Lock()
        self._buffer_size = buffer_size

    async def add(self, observation: Observation) -> None:
        """
        Add an observation to the buffer.

        Args:
            observation: The observation to add
        """
        async with self._lock:
            self._buffer.append(observation)

            # Prevent unbounded growth
            if len(self._buffer) > self._buffer_size:
                # Remove oldest observations
                self._buffer = self._buffer[-self._buffer_size :]
                logger.warning("Observation buffer exceeded limit, trimming", limit=self._buffer_size)

        logger.debug(
            "Observation added",
            request_id=observation.request_id,
            model=observation.model,
            latency_ms=observation.latency_ms,
        )

    async def get_all(self) -> list[Observation]:
        """Get all observations in the buffer."""
        async with self._lock:
            return self._buffer.copy()

    async def get_recent(self, limit: int = 100) -> list[Observation]:
        """Get the most recent observations."""
        async with self._lock:
            return self._buffer[-limit:]

    async def flush(self) -> list[Observation]:
        """
        Flush and return all observations.

        Clears the buffer after returning.
        """
        async with self._lock:
            observations = self._buffer.copy()
            self._buffer.clear()

            logger.info("Observation buffer flushed", count=len(observations))

            return observations

    async def clear(self) -> None:
        """Clear all observations."""
        async with self._lock:
            count = len(self._buffer)
            self._buffer.clear()

            logger.debug("Observation buffer cleared", count=count)

    def size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)
