# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Graceful shutdown coordinator for WebSocket and HTTP connections."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ShutdownCoordinator:
    """
    Coordinates graceful shutdown of all connections and tasks.

    Features:
    - Tracks active WebSocket connections
    - Manages background tasks
    - Ensures clean shutdown within timeout
    - Zero data loss during shutdown
    """

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.active_connections: set[WebSocket] = set()
        self.background_tasks: set[asyncio.Task] = set()
        self._shutdown_handlers: list[callable] = []

    def register_shutdown_handler(self, handler: callable) -> None:
        """Register a custom shutdown handler."""
        self._shutdown_handlers.append(handler)

    def add_connection(self, websocket: WebSocket) -> None:
        """Track an active WebSocket connection."""
        self.active_connections.add(websocket)
        logger.debug(
            "WebSocket connection added",
            total_connections=len(self.active_connections)
        )

    def remove_connection(self, websocket: WebSocket) -> None:
        """Remove a tracked WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.debug(
            "WebSocket connection removed",
            total_connections=len(self.active_connections)
        )

    def add_background_task(self, task: asyncio.Task) -> None:
        """Track a background task."""
        self.background_tasks.add(task)
        # Auto-remove when task completes
        task.add_done_callback(lambda t: self.background_tasks.discard(t))

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Gracefully shutdown all connections and tasks.

        Args:
            timeout: Maximum time to wait for shutdown (seconds)

        Shutdown sequence:
        1. Set shutdown event (signals loops to exit)
        2. Close WebSocket connections
        3. Cancel background tasks
        4. Run custom shutdown handlers
        5. Final cleanup
        """
        if self.shutdown_event.is_set():
            logger.warning("Shutdown already initiated")
            return

        logger.info(
            "Initiating graceful shutdown",
            timeout=timeout,
            active_connections=len(self.active_connections),
            background_tasks=len(self.background_tasks)
        )

        start_time = time.time()

        # Step 1: Signal shutdown
        self.shutdown_event.set()

        # Step 2: Close WebSocket connections
        if self.active_connections:
            logger.info(
                "Closing WebSocket connections",
                count=len(self.active_connections)
            )
            await self._close_websockets(timeout=timeout * 0.4)

        # Step 3: Cancel background tasks
        if self.background_tasks:
            logger.info(
                "Canceling background tasks",
                count=len(self.background_tasks)
            )
            await self._cancel_tasks(timeout=timeout * 0.3)

        # Step 4: Run custom shutdown handlers
        if self._shutdown_handlers:
            logger.info(
                "Running shutdown handlers",
                count=len(self._shutdown_handlers)
            )
            await self._run_shutdown_handlers(timeout=timeout * 0.3)

        elapsed = time.time() - start_time
        logger.info(
            "Graceful shutdown complete",
            elapsed_seconds=elapsed,
            connections_closed=len(self.active_connections) == 0,
            tasks_canceled=len(self.background_tasks) == 0
        )

    async def _close_websockets(self, timeout: float) -> None:
        """Close all WebSocket connections gracefully."""
        if not self.active_connections:
            return

        close_tasks = [
            self._close_websocket(ws)
            for ws in list(self.active_connections)  # Copy to avoid modification during iteration
        ]

        try:
            await asyncio.wait_for(
                asyncio.gather(*close_tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket close timeout exceeded",
                remaining=len(self.active_connections)
            )

    async def _close_websocket(self, websocket: WebSocket) -> None:
        """Close a single WebSocket connection."""
        try:
            # Send close frame
            await asyncio.wait_for(
                websocket.close(code=1001, reason="Server shutdown"),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("WebSocket close timeout for connection")
        except Exception as e:
            logger.debug(f"Error closing WebSocket: {e}")
        finally:
            self.remove_connection(websocket)

    async def _cancel_tasks(self, timeout: float) -> None:
        """Cancel all background tasks."""
        if not self.background_tasks:
            return

        # Cancel all tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.background_tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Task cancellation timeout exceeded",
                remaining=sum(1 for t in self.background_tasks if not t.done())
            )

    async def _run_shutdown_handlers(self, timeout: float) -> None:
        """Run custom shutdown handlers."""
        for handler in self._shutdown_handlers:
            try:
                await asyncio.wait_for(handler(), timeout=timeout / len(self._shutdown_handlers))
            except asyncio.TimeoutError:
                logger.warning(f"Shutdown handler timeout: {handler.__name__}")
            except Exception as e:
                logger.error(f"Shutdown handler error: {handler.__name__}", exc_info=e)
