# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""FastAPI application factory with dependency injection and lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .container import Container, get_container
from .lifecycle import LifecycleManager
from .shutdown import ShutdownCoordinator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.

    Handles:
    - Dependency injection setup
    - Service initialization
    - Graceful shutdown
    """
    logger.info("Application starting...")

    # Initialize container
    container = get_container()
    app.state.container = container

    # Initialize lifecycle manager
    lifecycle = LifecycleManager()
    app.state.lifecycle = lifecycle

    # Initialize shutdown coordinator
    shutdown_coordinator = ShutdownCoordinator()
    app.state.shutdown_coordinator = shutdown_coordinator

    # Register shutdown coordinator with lifecycle
    lifecycle.register_shutdown_handler(
        lambda: shutdown_coordinator.shutdown(timeout=30.0)
    )

    # Install signal handlers
    lifecycle.install_signal_handlers()

    try:
        # Run startup handlers
        await lifecycle.startup()

        logger.info("Application ready to serve traffic")
        yield

    finally:
        # Run shutdown handlers
        logger.info("Application shutting down...")
        await lifecycle.shutdown(timeout=30.0)
        logger.info("Application shutdown complete")


def create_app(
    title: str = "ATP Router Service",
    version: str = "2.0.0",
    debug: bool = False
) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        title: Application title
        version: Application version
        debug: Enable debug mode

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=title,
        version=version,
        debug=debug,
        lifespan=lifespan
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure from settings
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    _register_routers(app)

    # Add middleware
    _add_middleware(app)

    logger.info(
        "Application created",
        title=title,
        version=version,
        debug=debug
    )

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers."""
    # TODO: Import and register routers once they're created
    # from ..api.v1 import router as v1_router
    # from ..api.admin import router as admin_router
    # from ..api.websocket import router as ws_router

    # app.include_router(v1_router, prefix="/v1", tags=["v1"])
    # app.include_router(admin_router, prefix="/admin", tags=["admin"])
    # app.include_router(ws_router, tags=["websocket"])

    logger.debug("Routers registered")


def _add_middleware(app: FastAPI) -> None:
    """Add application middleware."""
    # TODO: Add middleware once implemented
    # from ..middleware import CorrelationIDMiddleware, TracingMiddleware

    # app.add_middleware(CorrelationIDMiddleware)
    # app.add_middleware(TracingMiddleware)

    logger.debug("Middleware added")
