# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Async database connection pool."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Async PostgreSQL connection pool using asyncpg.

    Provides efficient connection reuse and automatic connection management.
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._min_size = 10
        self._max_size = 20

    async def initialize(
        self,
        dsn: str,
        min_size: int = 10,
        max_size: int = 20,
        command_timeout: float = 60.0,
    ) -> None:
        """
        Initialize connection pool.

        Args:
            dsn: Database connection string
            min_size: Minimum pool size
            max_size: Maximum pool size
            command_timeout: Command timeout in seconds
        """
        try:
            import asyncpg
        except ImportError:
            logger.error("asyncpg not installed, database pool unavailable")
            raise

        self._min_size = min_size
        self._max_size = max_size

        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
            server_settings={
                "application_name": "atp-router",
                "jit": "off",  # Disable JIT for predictable performance
            },
        )

        logger.info(
            "Database pool initialized",
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            await self._pool.close()
            logger.info("Database pool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.

        Usage:
            async with pool.acquire() as conn:
                result = await conn.fetch("SELECT * FROM table")
        """
        if self._pool is None:
            raise RuntimeError("Database pool not initialized")

        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args: Any) -> str:
        """
        Execute a query without returning results.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Query execution status
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """
        Fetch multiple rows from query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of records
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """
        Fetch a single row from query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single record or None
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """
        Fetch a single value from query.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single value
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    def get_size(self) -> tuple[int, int]:
        """
        Get current pool size.

        Returns:
            Tuple of (current_size, max_size)
        """
        if self._pool is None:
            return (0, 0)

        return (self._pool.get_size(), self._pool.get_max_size())

    def get_idle_size(self) -> int:
        """Get number of idle connections."""
        if self._pool is None:
            return 0

        return self._pool.get_idle_size()
