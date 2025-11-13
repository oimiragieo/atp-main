# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Application lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manages application startup and shutdown lifecycle.

    Coordinates graceful shutdown of all services including:
    - WebSocket connections
    - Background tasks
    - Database connections
    - Cache connections
    """

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.startup_complete = asyncio.Event()
        self.shutdown_handlers: list[Callable[[], Awaitable[None]]] = []
        self.startup_handlers: list[Callable[[], Awaitable[None]]] = []

    def register_startup_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
        """Register a handler to run on startup."""
        self.startup_handlers.append(handler)
        logger.debug(f"Registered startup handler: {handler.__name__}")

    def register_shutdown_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
        """Register a handler to run on shutdown."""
        self.shutdown_handlers.append(handler)
        logger.debug(f"Registered shutdown handler: {handler.__name__}")

    async def startup(self) -> None:
        """Run all startup handlers."""
        logger.info("Starting application lifecycle", handlers=len(self.startup_handlers))

        start_time = time.time()

        for handler in self.startup_handlers:
            try:
                logger.debug(f"Running startup handler: {handler.__name__}")
                await handler()
            except Exception as e:
                logger.error(f"Startup handler failed: {handler.__name__}", exc_info=e)
                raise

        elapsed = time.time() - start_time
        self.startup_complete.set()

        logger.info("Application startup complete", elapsed_seconds=elapsed, handlers_run=len(self.startup_handlers))

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Run all shutdown handlers with timeout.

        Args:
            timeout: Maximum time to wait for shutdown (seconds)
        """
        if self.shutdown_event.is_set():
            logger.warning("Shutdown already initiated")
            return

        logger.info("Initiating graceful shutdown", timeout=timeout, handlers=len(self.shutdown_handlers))

        # Set shutdown event (signals all services to stop)
        self.shutdown_event.set()

        start_time = time.time()

        # Run all shutdown handlers
        for handler in self.shutdown_handlers:
            try:
                remaining_timeout = timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    logger.warning(f"Shutdown timeout exceeded, skipping handler: {handler.__name__}")
                    continue

                logger.debug(f"Running shutdown handler: {handler.__name__}", remaining_timeout=remaining_timeout)

                await asyncio.wait_for(handler(), timeout=remaining_timeout)

            except asyncio.TimeoutError:
                logger.warning(f"Shutdown handler timed out: {handler.__name__}")
            except Exception as e:
                logger.error(f"Shutdown handler failed: {handler.__name__}", exc_info=e)

        elapsed = time.time() - start_time

        logger.info("Graceful shutdown complete", elapsed_seconds=elapsed, handlers_run=len(self.shutdown_handlers))

    def install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""

        def handle_signal(signum: int, frame: Any = None) -> None:
            """Handle shutdown signals."""
            sig_name = signal.Signals(signum).name
            logger.info(f"Received signal: {sig_name}")

            # Create task for async shutdown
            asyncio.create_task(self.shutdown())

        # Register signal handlers
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        logger.info("Signal handlers installed (SIGTERM, SIGINT)")
