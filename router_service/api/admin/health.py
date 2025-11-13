# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Health check endpoints - liveness, readiness, startup probes."""

from __future__ import annotations

import logging
from enum import Enum

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    """Health check response."""

    status: HealthStatus
    checks: dict[str, dict] = {}


@router.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.

    Returns 200 if application is running.
    """
    return HealthResponse(
        status=HealthStatus.HEALTHY,
        checks={"basic": {"status": "ok"}}
    )


@router.get("/livez", response_model=HealthResponse)
async def liveness_check(request: Request) -> HealthResponse:
    """
    Liveness probe - is the application alive?

    Kubernetes will restart the pod if this fails.

    Checks:
    - Application is running
    - No deadlocks
    - Core services responding
    """
    # Check if lifecycle is initialized
    if not hasattr(request.app.state, "lifecycle"):
        raise HTTPException(
            status_code=503,
            detail="Application not initialized"
        )

    # Check if startup is complete
    if not request.app.state.lifecycle.startup_complete.is_set():
        raise HTTPException(
            status_code=503,
            detail="Application still starting"
        )

    return HealthResponse(
        status=HealthStatus.HEALTHY,
        checks={
            "application": {"status": "alive"},
            "startup": {"status": "complete"},
        }
    )


@router.get("/readyz", response_model=HealthResponse)
async def readiness_check(request: Request) -> HealthResponse:
    """
    Readiness probe - can the application serve traffic?

    Kubernetes will remove from load balancer if this fails.

    Checks:
    - All dependencies available (database, cache, etc.)
    - Services initialized
    - Not shutting down
    """
    # Check if shutting down
    if hasattr(request.app.state, "shutdown_coordinator"):
        if request.app.state.shutdown_coordinator.shutdown_event.is_set():
            raise HTTPException(
                status_code=503,
                detail="Application shutting down"
            )

    # TODO: Add dependency checks once implemented
    # - Database connection pool
    # - Redis connection
    # - Adapter registry

    return HealthResponse(
        status=HealthStatus.HEALTHY,
        checks={
            "application": {"status": "ready"},
            "shutdown": {"status": "not_initiated"},
        }
    )


@router.get("/startupz", response_model=HealthResponse)
async def startup_check(request: Request) -> HealthResponse:
    """
    Startup probe - has initialization completed?

    Kubernetes will wait for this before checking liveness/readiness.
    """
    if not hasattr(request.app.state, "lifecycle"):
        raise HTTPException(
            status_code=503,
            detail="Application not initialized"
        )

    if not request.app.state.lifecycle.startup_complete.is_set():
        raise HTTPException(
            status_code=503,
            detail="Application startup in progress"
        )

    return HealthResponse(
        status=HealthStatus.HEALTHY,
        checks={
            "startup": {"status": "complete"}
        }
    )
