# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Routing strategies for model selection."""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...adaptive_stats import ModelStats

logger = logging.getLogger(__name__)


class RoutingStrategy(ABC):
    """Base class for routing strategies."""

    @abstractmethod
    async def select(
        self,
        prompt: str,
        quality_target: str,
        max_cost: float | None,
        latency_slo: int | None,
        stats: ModelStats | None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Select a model based on the strategy.

        Args:
            prompt: The user prompt
            quality_target: Quality target (fast, balanced, high)
            max_cost: Maximum cost constraint
            latency_slo: Latency SLO constraint
            stats: Model statistics

        Returns:
            Tuple of (model_id, metadata)
        """


class ThompsonSamplingStrategy(RoutingStrategy):
    """Thompson sampling bandit strategy."""

    async def select(
        self,
        prompt: str,
        quality_target: str,
        max_cost: float | None,
        latency_slo: int | None,
        stats: ModelStats | None,
    ) -> tuple[str, dict[str, Any]]:
        """Select model using Thompson sampling."""
        # Import here to avoid circular dependency
        from ...adaptive_stats import thompson_select

        if stats is None:
            # Fallback to default model
            return "gpt-4", {"strategy": "thompson", "fallback": True}

        # Get candidates that meet constraints
        candidates = self._filter_candidates(
            stats=stats,
            max_cost=max_cost,
            latency_slo=latency_slo,
        )

        if not candidates:
            logger.warning("No candidates meet constraints, using fallback")
            return "gpt-4", {"strategy": "thompson", "fallback": True}

        # Use Thompson sampling
        model_id = thompson_select(candidates, stats)

        return model_id, {
            "strategy": "thompson",
            "candidates": len(candidates),
            "quality_target": quality_target,
        }

    def _filter_candidates(
        self,
        stats: ModelStats,
        max_cost: float | None,
        latency_slo: int | None,
    ) -> list[str]:
        """Filter models by constraints."""
        all_models = stats.get_all_models()

        candidates = []
        for model_id in all_models:
            model_stats = stats.get_stats(model_id)
            if model_stats is None:
                continue

            # Check cost constraint
            if max_cost is not None:
                avg_cost = model_stats.get("avg_cost", 0)
                if avg_cost > max_cost:
                    continue

            # Check latency constraint
            if latency_slo is not None:
                avg_latency = model_stats.get("avg_latency", 0)
                if avg_latency > latency_slo:
                    continue

            candidates.append(model_id)

        return candidates


class ContextualUCBStrategy(RoutingStrategy):
    """Contextual Upper Confidence Bound strategy."""

    def __init__(self, exploration_constant: float = 2.0):
        """
        Initialize UCB strategy.

        Args:
            exploration_constant: Exploration vs exploitation tradeoff
        """
        self.exploration_constant = exploration_constant

    async def select(
        self,
        prompt: str,
        quality_target: str,
        max_cost: float | None,
        latency_slo: int | None,
        stats: ModelStats | None,
    ) -> tuple[str, dict[str, Any]]:
        """Select model using contextual UCB."""
        # Import here to avoid circular dependency
        from ...adaptive_stats import ucb_select

        if stats is None:
            return "gpt-4", {"strategy": "ucb", "fallback": True}

        # Get candidates
        candidates = self._filter_candidates(
            stats=stats,
            max_cost=max_cost,
            latency_slo=latency_slo,
        )

        if not candidates:
            logger.warning("No candidates meet constraints, using fallback")
            return "gpt-4", {"strategy": "ucb", "fallback": True}

        # Use UCB selection
        model_id = ucb_select(candidates, stats, self.exploration_constant)

        return model_id, {
            "strategy": "ucb",
            "candidates": len(candidates),
            "exploration_constant": self.exploration_constant,
        }

    def _filter_candidates(
        self,
        stats: ModelStats,
        max_cost: float | None,
        latency_slo: int | None,
    ) -> list[str]:
        """Filter models by constraints."""
        all_models = stats.get_all_models()

        candidates = []
        for model_id in all_models:
            model_stats = stats.get_stats(model_id)
            if model_stats is None:
                continue

            # Check cost constraint
            if max_cost is not None:
                avg_cost = model_stats.get("avg_cost", 0)
                if avg_cost > max_cost:
                    continue

            # Check latency constraint
            if latency_slo is not None:
                avg_latency = model_stats.get("avg_latency", 0)
                if avg_latency > latency_slo:
                    continue

            candidates.append(model_id)

        return candidates


class GreedyStrategy(RoutingStrategy):
    """Greedy strategy - always select best performing model."""

    async def select(
        self,
        prompt: str,
        quality_target: str,
        max_cost: float | None,
        latency_slo: int | None,
        stats: ModelStats | None,
    ) -> tuple[str, dict[str, Any]]:
        """Select model greedily based on past performance."""
        if stats is None:
            return "gpt-4", {"strategy": "greedy", "fallback": True}

        # Get candidates
        candidates = self._filter_candidates(
            stats=stats,
            max_cost=max_cost,
            latency_slo=latency_slo,
        )

        if not candidates:
            return "gpt-4", {"strategy": "greedy", "fallback": True}

        # Select model with best average quality
        best_model = None
        best_quality = -1.0

        for model_id in candidates:
            model_stats = stats.get_stats(model_id)
            if model_stats is None:
                continue

            avg_quality = model_stats.get("avg_quality", 0.0)
            if avg_quality > best_quality:
                best_quality = avg_quality
                best_model = model_id

        if best_model is None:
            # Fallback to random selection
            best_model = random.choice(candidates)

        return best_model, {
            "strategy": "greedy",
            "best_quality": best_quality,
            "candidates": len(candidates),
        }

    def _filter_candidates(
        self,
        stats: ModelStats,
        max_cost: float | None,
        latency_slo: int | None,
    ) -> list[str]:
        """Filter models by constraints."""
        all_models = stats.get_all_models()

        candidates = []
        for model_id in all_models:
            model_stats = stats.get_stats(model_id)
            if model_stats is None:
                continue

            # Check cost constraint
            if max_cost is not None:
                avg_cost = model_stats.get("avg_cost", 0)
                if avg_cost > max_cost:
                    continue

            # Check latency constraint
            if latency_slo is not None:
                avg_latency = model_stats.get("avg_latency", 0)
                if avg_latency > latency_slo:
                    continue

            candidates.append(model_id)

        return candidates
