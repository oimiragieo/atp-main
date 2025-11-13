# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Routing service - intelligent model selection and request routing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...adaptive_stats import ModelStats

logger = logging.getLogger(__name__)


class RoutingService:
    """
    Service for intelligent model selection and routing.

    Uses bandit algorithms (Thompson sampling, UCB) for adaptive model selection.
    Supports cost, quality, and latency optimization.
    """

    def __init__(
        self,
        stats_tracker: ModelStats | None = None,
        default_strategy: str = "thompson",
    ):
        """
        Initialize routing service.

        Args:
            stats_tracker: Model statistics tracker
            default_strategy: Default selection strategy (thompson, ucb, greedy)
        """
        self.stats_tracker = stats_tracker
        self.default_strategy = default_strategy
        self._strategies = {}
        self._register_strategies()

    def _register_strategies(self) -> None:
        """Register available routing strategies."""
        from .strategies import (
            ContextualUCBStrategy,
            GreedyStrategy,
            ThompsonSamplingStrategy,
        )

        self._strategies = {
            "thompson": ThompsonSamplingStrategy(),
            "ucb": ContextualUCBStrategy(),
            "greedy": GreedyStrategy(),
        }

    async def select_model(
        self,
        prompt: str,
        quality_target: str = "balanced",
        max_cost_usd: float | None = None,
        latency_slo_ms: int | None = None,
        strategy: str | None = None,
    ) -> tuple[str, dict]:
        """
        Select the best model for a given request.

        Args:
            prompt: The user prompt
            quality_target: Quality target (fast, balanced, high)
            max_cost_usd: Maximum cost constraint
            latency_slo_ms: Latency SLO constraint
            strategy: Override default strategy

        Returns:
            Tuple of (model_id, metadata)
        """
        # Use default strategy if not specified
        strategy_name = strategy or self.default_strategy

        if strategy_name not in self._strategies:
            logger.warning(
                f"Unknown strategy: {strategy_name}, using default",
                strategy=strategy_name,
                default=self.default_strategy,
            )
            strategy_name = self.default_strategy

        # Get strategy
        routing_strategy = self._strategies[strategy_name]

        # Select model using strategy
        model_id, metadata = await routing_strategy.select(
            prompt=prompt,
            quality_target=quality_target,
            max_cost=max_cost_usd,
            latency_slo=latency_slo_ms,
            stats=self.stats_tracker,
        )

        logger.info(
            "Model selected",
            model=model_id,
            strategy=strategy_name,
            quality_target=quality_target,
        )

        return model_id, metadata

    async def update_statistics(
        self,
        model_id: str,
        latency_ms: float,
        cost_usd: float,
        quality_score: float | None = None,
        success: bool = True,
    ) -> None:
        """
        Update model statistics after request completion.

        Args:
            model_id: The model that was used
            latency_ms: Observed latency
            cost_usd: Observed cost
            quality_score: Quality score (if available)
            success: Whether request succeeded
        """
        if self.stats_tracker is None:
            return

        await self.stats_tracker.update(
            model_id=model_id,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            quality_score=quality_score,
            success=success,
        )

        logger.debug(
            "Statistics updated",
            model=model_id,
            latency_ms=latency_ms,
            success=success,
        )

    def get_available_models(self) -> list[str]:
        """Get list of available models."""
        if self.stats_tracker is None:
            return []

        return self.stats_tracker.get_all_models()

    def get_model_stats(self, model_id: str) -> dict | None:
        """Get statistics for a specific model."""
        if self.stats_tracker is None:
            return None

        return self.stats_tracker.get_stats(model_id)
