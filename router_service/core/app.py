# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""FastAPI application factory with dependency injection and lifecycle management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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

    # Register services in DI container
    await _register_services(container, lifecycle)

    # Register shutdown coordinator with lifecycle
    lifecycle.register_shutdown_handler(lambda: shutdown_coordinator.shutdown(timeout=30.0))

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


async def _register_services(container: Container, lifecycle: LifecycleManager) -> None:
    """Register all services in the DI container."""
    from ..domain.adapter import AdapterRegistry
    from ..domain.observation import ObservationService
    from ..domain.routing import RoutingService
    from ..infrastructure.database import DatabasePool
    from ..infrastructure.secrets import SecretsService

    # Observation service
    obs_service = ObservationService(buffer_size=10000)
    container.register(ObservationService, obs_service)

    # Adapter registry
    adapter_registry = AdapterRegistry()
    container.register(AdapterRegistry, adapter_registry)

    # Routing service
    routing_service = RoutingService(default_strategy="thompson")
    container.register(RoutingService, routing_service)

    # Secrets service
    secrets_service = SecretsService.from_config()
    container.register(SecretsService, secrets_service)

    # Database pool (if configured)
    db_dsn = secrets_service.backend._cache.get("DATABASE_URL") or await secrets_service.backend.get_secret(
        "DATABASE_URL"
    )
    if db_dsn:
        db_pool = DatabasePool()
        await db_pool.initialize(db_dsn)
        container.register(DatabasePool, db_pool)

        # Register shutdown handler
        lifecycle.register_shutdown_handler(db_pool.close)

    logger.info("All services registered in DI container")


def create_app(title: str = "ATP Router Service", version: str = "2.0.0", debug: bool = False) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        title: Application title
        version: Application version
        debug: Enable debug mode

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(title=title, version=version, debug=debug, lifespan=lifespan)

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

    logger.info("Application created", title=title, version=version, debug=debug)

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers."""
    from ..api.admin.health import router as health_router
    from ..api.v1 import router as v1_router

    # V1 endpoints (ask, plan, observe)
    app.include_router(v1_router, prefix="/v1", tags=["v1"])

    # Health check endpoints
    app.include_router(health_router, tags=["health"])

    logger.info("All API routers registered")


def _add_middleware(app: FastAPI) -> None:
    """Add application middleware."""
    # TODO: Add middleware once implemented
    # from ..middleware import CorrelationIDMiddleware, TracingMiddleware

    # app.add_middleware(CorrelationIDMiddleware)
    # app.add_middleware(TracingMiddleware)

    logger.debug("Middleware added")
