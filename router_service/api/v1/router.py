# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""V1 API endpoints for routing operations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...domain.observation import Observation, ObservationService
from ...domain.routing import RoutingService

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class AskRequest(BaseModel):
    """Request model for /v1/ask endpoint."""

    prompt: str = Field(..., description="The prompt to process")
    quality: str = Field(default="balanced", description="Quality target (fast/balanced/high)")
    max_cost_usd: float | None = Field(default=None, description="Maximum cost in USD")
    latency_slo_ms: int | None = Field(default=None, description="Latency SLO in milliseconds")
    stream: bool = Field(default=False, description="Enable streaming response")


class AskResponse(BaseModel):
    """Response model for /v1/ask endpoint."""

    model_used: str
    response: str
    latency_ms: float
    cost_usd: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    """Request model for /v1/plan endpoint."""

    prompt: str
    quality: str = "balanced"
    max_cost_usd: float | None = None
    latency_slo_ms: int | None = None


class PlanResponse(BaseModel):
    """Response model for /v1/plan endpoint."""

    selected_model: str
    candidates: list[dict[str, Any]]
    reasoning: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObserveRequest(BaseModel):
    """Request model for /v1/observe endpoint."""

    request_id: str
    model: str
    latency_ms: float
    cost_usd: float | None = None
    quality_score: float | None = None
    tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# Dependency injection
def get_routing_service(request: Request) -> RoutingService:
    """Get routing service from DI container."""
    if not hasattr(request.app.state, "container"):
        raise HTTPException(status_code=500, detail="DI container not initialized")

    return request.app.state.container.get(RoutingService)


def get_observation_service(request: Request) -> ObservationService:
    """Get observation service from DI container."""
    if not hasattr(request.app.state, "container"):
        raise HTTPException(status_code=500, detail="DI container not initialized")

    return request.app.state.container.get(ObservationService)


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    routing_service: RoutingService = Depends(get_routing_service),  # noqa: B008
    observation_service: ObservationService = Depends(get_observation_service),  # noqa: B008
) -> AskResponse:
    """
    Process a completion request with intelligent routing.

    This endpoint:
    1. Selects the best model based on constraints
    2. Routes the request to the selected adapter
    3. Logs observation for learning
    4. Returns the response

    Args:
        request: The completion request
        routing_service: Routing service (injected)
        observation_service: Observation service (injected)

    Returns:
        Completion response with metadata
    """
    logger.info(
        "Processing ask request",
        prompt_length=len(request.prompt),
        quality=request.quality,
    )

    # Step 1: Select model
    model_id, metadata = await routing_service.select_model(
        prompt=request.prompt,
        quality_target=request.quality,
        max_cost_usd=request.max_cost_usd,
        latency_slo_ms=request.latency_slo_ms,
    )

    # Step 2: Route to adapter (placeholder - actual implementation would call adapter)
    # TODO: Implement actual adapter call
    response_text = f"[Response from {model_id}] Processed: {request.prompt[:50]}..."
    latency_ms = 100.0  # Placeholder
    cost_usd = 0.01  # Placeholder

    # Step 3: Log observation
    observation = Observation(
        request_id=f"req_{id(request)}",
        model=model_id,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        tokens=len(request.prompt.split()),
        metadata=metadata,
    )
    await observation_service.add(observation)

    # Step 4: Update statistics
    await routing_service.update_statistics(
        model_id=model_id,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        success=True,
    )

    return AskResponse(
        model_used=model_id,
        response=response_text,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        metadata=metadata,
    )


@router.post("/plan", response_model=PlanResponse)
async def plan(
    request: PlanRequest,
    routing_service: RoutingService = Depends(get_routing_service),  # noqa: B008
) -> PlanResponse:
    """
    Get routing plan without executing the request.

    Returns the model selection and reasoning without actually
    making a call to the adapter.

    Args:
        request: The plan request
        routing_service: Routing service (injected)

    Returns:
        Routing plan with candidates and reasoning
    """
    logger.info(
        "Processing plan request",
        prompt_length=len(request.prompt),
        quality=request.quality,
    )

    # Select model
    model_id, metadata = await routing_service.select_model(
        prompt=request.prompt,
        quality_target=request.quality,
        max_cost_usd=request.max_cost_usd,
        latency_slo_ms=request.latency_slo_ms,
    )

    # Get all available models as candidates
    all_models = routing_service.get_available_models()
    candidates = [
        {
            "model": m,
            "stats": routing_service.get_model_stats(m) or {},
        }
        for m in all_models
    ]

    reasoning = (
        f"Selected {model_id} based on {metadata.get('strategy', 'unknown')} strategy "
        f"with {metadata.get('candidates', 0)} candidates"
    )

    return PlanResponse(
        selected_model=model_id,
        candidates=candidates,
        reasoning=reasoning,
        metadata=metadata,
    )


@router.post("/observe")
async def observe(
    request: ObserveRequest,
    observation_service: ObservationService = Depends(get_observation_service),  # noqa: B008
) -> dict[str, str]:
    """
    Log an observation manually.

    Allows external systems to log observations.

    Args:
        request: The observation request
        observation_service: Observation service (injected)

    Returns:
        Status message
    """
    logger.info(
        "Logging observation",
        request_id=request.request_id,
        model=request.model,
    )

    observation = Observation(
        request_id=request.request_id,
        model=request.model,
        latency_ms=request.latency_ms,
        cost_usd=request.cost_usd,
        quality_score=request.quality_score,
        tokens=request.tokens,
        metadata=request.metadata,
    )

    await observation_service.add(observation)

    return {"status": "ok", "message": "Observation logged"}
