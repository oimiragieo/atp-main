"""Cost-aware model selection with dynamic pricing integration."""

import logging
import time
from typing import Any

from ..cost_optimization import get_cost_optimizer
from ..pricing import get_pricing_manager
from ..routing_constants import Candidate
from .selection_config import LOCAL_MODEL_INDICATORS, SelectionConfig

logger = logging.getLogger(__name__)


class CostAwareSelector:
    """Model selector that optimizes for cost-quality tradeoffs with real-time pricing."""

    def __init__(self, config: SelectionConfig | None = None):
        self.config = config or SelectionConfig.from_environment()

        # Integration with pricing and optimization systems
        self.pricing_manager = get_pricing_manager()
        self.cost_optimizer = get_cost_optimizer()

        # Selection performance tracking
        self._selection_history: list[dict[str, Any]] = []
        self._performance_cache: dict[str, dict[str, float]] = {}

        logger.info("Cost-aware selector initialized")

    async def select_optimal_model(
        self,
        candidates: list[Candidate],
        quality_requirement: str,
        latency_slo_ms: int,
        estimated_tokens: int = 1000,
        tenant_id: str | None = None,
        project_id: str | None = None,
        registry: dict[str, Any] | None = None,
    ) -> tuple[list[Candidate], dict[str, Any]]:
        """Select optimal model with cost awareness."""

        selection_metadata = {
            "selection_strategy": self.config.selection_strategy,
            "cost_awareness_enabled": self.config.cost_awareness_enabled,
            "candidates_evaluated": len(candidates),
            "selection_time": time.time(),
        }

        try:
            # 1. Get tenant/project preferences
            preferences = await self._get_selection_preferences(tenant_id, project_id)

            # 2. Enhance candidates with real-time pricing
            enhanced_candidates = await self._enhance_candidates_with_pricing(candidates, estimated_tokens)

            # 3. Apply cost optimization
            if self.config.cost_awareness_enabled:
                optimized_candidates = await self._apply_cost_optimization(
                    enhanced_candidates, tenant_id, project_id, estimated_tokens
                )
            else:
                optimized_candidates = enhanced_candidates

            # 4. Apply selection strategy
            if self.config.selection_strategy == "cost_aware_bandit":
                selected_candidates = await self._cost_aware_bandit_selection(
                    optimized_candidates, quality_requirement, latency_slo_ms, preferences
                )
            elif self.config.selection_strategy == "pure_cost":
                selected_candidates = self._pure_cost_selection(optimized_candidates, latency_slo_ms)
            elif self.config.selection_strategy == "pure_quality":
                selected_candidates = self._pure_quality_selection(optimized_candidates, latency_slo_ms)
            elif self.config.selection_strategy == "balanced":
                selected_candidates = self._balanced_selection(
                    optimized_candidates, quality_requirement, latency_slo_ms, preferences
                )
            else:
                # Fallback to original logic
                selected_candidates = self._fallback_selection(candidates, quality_requirement, latency_slo_ms)

            # 5. Apply local model preference if enabled
            if self.config.local_model_preference:
                selected_candidates = self._apply_local_preference(selected_candidates)

            # 6. Record selection for performance tracking
            if self.config.track_selection_performance:
                await self._record_selection(selected_candidates, selection_metadata)

            # 7. Update selection metadata
            selection_metadata.update(
                {
                    "selected_models": [c.name for c in selected_candidates],
                    "primary_model": selected_candidates[0].name if selected_candidates else None,
                    "total_estimated_cost": sum(getattr(c, "estimated_cost_usd", 0) for c in selected_candidates),
                    "cost_optimization_applied": self.config.cost_awareness_enabled,
                    "local_preference_applied": self.config.local_model_preference,
                }
            )

            return selected_candidates, selection_metadata

        except Exception as e:
            logger.error(f"Error in cost-aware model selection: {e}")

            # Fallback to simple selection
            fallback_candidates = self._fallback_selection(candidates, quality_requirement, latency_slo_ms)
            selection_metadata.update(
                {"error": str(e), "fallback_used": True, "selected_models": [c.name for c in fallback_candidates]}
            )

            return fallback_candidates, selection_metadata

    async def _get_selection_preferences(
        self, tenant_id: str | None = None, project_id: str | None = None
    ) -> dict[str, float]:
        """Get selection preferences for tenant/project."""
        preferences = {
            "cost_weight": self.config.cost_weight,
            "quality_weight": self.config.quality_weight,
            "latency_weight": self.config.latency_weight,
        }

        # Apply tenant preferences
        if tenant_id and self.config.tenant_preferences:
            tenant_prefs = self.config.tenant_preferences.get(tenant_id, {})
            preferences.update(tenant_prefs)

        # Apply project preferences (override tenant)
        if project_id and self.config.project_preferences:
            project_prefs = self.config.project_preferences.get(project_id, {})
            preferences.update(project_prefs)

        # Normalize weights to sum to 1.0
        total_weight = preferences["cost_weight"] + preferences["quality_weight"] + preferences["latency_weight"]
        if total_weight > 0:
            preferences = {k: v / total_weight for k, v in preferences.items()}

        return preferences

    async def _enhance_candidates_with_pricing(
        self, candidates: list[Candidate], estimated_tokens: int
    ) -> list[Candidate]:
        """Enhance candidates with real-time pricing data."""
        enhanced_candidates = []

        for candidate in candidates:
            enhanced_candidate = candidate

            if self.config.use_real_time_pricing:
                try:
                    # Try to get real-time pricing
                    provider = self._extract_provider_from_model(candidate.name)
                    pricing = await self.pricing_manager.get_model_pricing(provider, candidate.name)

                    if pricing:
                        # Calculate cost with real-time pricing
                        input_cost = (estimated_tokens * 0.7 / 1000.0) * pricing.get("input", 0)  # 70% input
                        output_cost = (estimated_tokens * 0.3 / 1000.0) * pricing.get("output", 0)  # 30% output
                        total_cost = input_cost + output_cost

                        # Create enhanced candidate with updated cost
                        enhanced_candidate = Candidate(
                            name=candidate.name,
                            cost_per_1k_tokens=total_cost * 1000 / estimated_tokens,  # Convert back to per-1k
                            quality_pred=candidate.quality_pred,
                            latency_p95=candidate.latency_p95,
                        )

                        # Add additional attributes
                        enhanced_candidate.estimated_cost_usd = total_cost
                        enhanced_candidate.real_time_pricing = pricing
                        enhanced_candidate.pricing_timestamp = time.time()

                    else:
                        # Use static pricing
                        enhanced_candidate.estimated_cost_usd = (
                            estimated_tokens / 1000.0
                        ) * candidate.cost_per_1k_tokens
                        enhanced_candidate.real_time_pricing = None

                except Exception as e:
                    logger.warning(f"Failed to get real-time pricing for {candidate.name}: {e}")
                    enhanced_candidate.estimated_cost_usd = (estimated_tokens / 1000.0) * candidate.cost_per_1k_tokens
                    enhanced_candidate.real_time_pricing = None

            else:
                # Use static pricing
                enhanced_candidate.estimated_cost_usd = (estimated_tokens / 1000.0) * candidate.cost_per_1k_tokens

            enhanced_candidates.append(enhanced_candidate)

        return enhanced_candidates

    def _extract_provider_from_model(self, model_name: str) -> str:
        """Extract provider name from model name."""
        model_lower = model_name.lower()

        if "gpt" in model_lower or "openai" in model_lower:
            return "openai"
        elif "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        elif "gemini" in model_lower or "bison" in model_lower or "google" in model_lower:
            return "google"
        elif any(indicator in model_lower for indicator in LOCAL_MODEL_INDICATORS):
            return "local"
        else:
            return "unknown"

    async def _apply_cost_optimization(
        self,
        candidates: list[Candidate],
        tenant_id: str | None = None,
        project_id: str | None = None,
        estimated_tokens: int = 1000,
    ) -> list[Candidate]:
        """Apply cost optimization to candidate selection."""
        optimized_candidates = []

        for candidate in candidates:
            try:
                # Check if request would be optimized
                estimated_cost = getattr(candidate, "estimated_cost_usd", 0)
                provider = self._extract_provider_from_model(candidate.name)

                optimization_result = await self.cost_optimizer.optimize_request(
                    provider=provider,
                    model=candidate.name,
                    estimated_cost=estimated_cost,
                    tokens=estimated_tokens,
                    tenant_id=tenant_id,
                    quality_requirement="balanced",
                )

                if optimization_result.get("optimization_applied", False):
                    # Use optimized model
                    optimized_request = optimization_result["optimized_request"]

                    # Create new candidate with optimized parameters
                    optimized_candidate = Candidate(
                        name=optimized_request["model"],
                        cost_per_1k_tokens=optimized_request["estimated_cost"] * 1000 / estimated_tokens,
                        quality_pred=candidate.quality_pred * 0.95,  # Assume slight quality reduction
                        latency_p95=candidate.latency_p95,
                    )

                    optimized_candidate.estimated_cost_usd = optimized_request["estimated_cost"]
                    optimized_candidate.optimization_applied = True
                    optimized_candidate.original_candidate = candidate
                    optimized_candidate.savings_usd = optimization_result["potential_savings"]

                    optimized_candidates.append(optimized_candidate)
                else:
                    # Keep original candidate
                    candidate.optimization_applied = False
                    optimized_candidates.append(candidate)

            except Exception as e:
                logger.warning(f"Failed to apply cost optimization to {candidate.name}: {e}")
                candidate.optimization_applied = False
                optimized_candidates.append(candidate)

        return optimized_candidates

    async def _cost_aware_bandit_selection(
        self, candidates: list[Candidate], quality_requirement: str, latency_slo_ms: int, preferences: dict[str, float]
    ) -> list[Candidate]:
        """Cost-aware bandit selection algorithm."""
        if not candidates:
            return []

        # Filter candidates by latency SLO
        viable_candidates = [c for c in candidates if c.latency_p95 <= latency_slo_ms]
        if not viable_candidates:
            viable_candidates = candidates  # Fallback to all candidates

        # Calculate composite scores
        scored_candidates = []
        for candidate in viable_candidates:
            score = await self._calculate_composite_score(candidate, preferences)
            scored_candidates.append((candidate, score))

        # Sort by score (higher is better)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply bandit algorithm
        selected = []

        # Primary selection (exploitation)
        if scored_candidates:
            primary_candidate, primary_score = scored_candidates[0]
            selected.append(primary_candidate)

            # Add exploration candidate with probability
            import random

            if len(scored_candidates) > 1 and random.random() < self.config.exploration_rate:
                # Select exploration candidate from remaining viable options
                exploration_candidates = [c for c, s in scored_candidates[1:] if s > 0.5]
                if exploration_candidates:
                    exploration_candidate = random.choice(exploration_candidates)
                    selected.append(exploration_candidate)

        return selected

    async def _calculate_composite_score(self, candidate: Candidate, preferences: dict[str, float]) -> float:
        """Calculate composite score for a candidate."""
        try:
            # Normalize metrics to 0-1 scale

            # Cost score (lower cost = higher score)
            estimated_cost = getattr(candidate, "estimated_cost_usd", candidate.cost_per_1k_tokens / 1000)
            cost_score = 1.0 / (1.0 + estimated_cost * 10)  # Normalize cost

            # Quality score (already 0-1)
            quality_score = candidate.quality_pred

            # Latency score (lower latency = higher score)
            latency_score = 1.0 / (1.0 + candidate.latency_p95 / 1000.0)  # Normalize latency

            # Apply local model bonuses
            if self.config.local_model_preference and self._is_local_model(candidate.name):
                cost_score *= 1.0 + self.config.local_model_cost_multiplier  # Cost bonus
                quality_score += self.config.local_model_quality_bonus  # Quality bonus
                latency_score *= 1.0 / self.config.local_model_latency_penalty  # Latency penalty

            # Calculate weighted composite score
            composite_score = (
                preferences["cost_weight"] * cost_score
                + preferences["quality_weight"] * quality_score
                + preferences["latency_weight"] * latency_score
            )

            # Apply performance-based adjustments
            performance_multiplier = await self._get_performance_multiplier(candidate.name)
            composite_score *= performance_multiplier

            return max(0.0, min(1.0, composite_score))  # Clamp to 0-1

        except Exception as e:
            logger.error(f"Error calculating composite score for {candidate.name}: {e}")
            return 0.5  # Neutral score on error

    def _is_local_model(self, model_name: str) -> bool:
        """Check if a model is a local model."""
        model_lower = model_name.lower()
        return any(indicator in model_lower for indicator in LOCAL_MODEL_INDICATORS)

    async def _get_performance_multiplier(self, model_name: str) -> float:
        """Get performance-based multiplier for model selection."""
        if model_name not in self._performance_cache:
            return 1.0

        performance_data = self._performance_cache[model_name]

        # Calculate multiplier based on recent performance
        success_rate = performance_data.get("success_rate", 1.0)
        avg_quality = performance_data.get("avg_quality", 0.8)
        avg_latency_ratio = performance_data.get("avg_latency_ratio", 1.0)  # actual/expected

        # Performance multiplier (0.5 to 1.5 range)
        multiplier = success_rate * 0.4 + avg_quality * 0.4 + (1.0 / max(avg_latency_ratio, 0.1)) * 0.2

        return max(0.5, min(1.5, multiplier))

    def _pure_cost_selection(self, candidates: list[Candidate], latency_slo_ms: int) -> list[Candidate]:
        """Pure cost-based selection (cheapest viable)."""
        # Filter by latency
        viable = [c for c in candidates if c.latency_p95 <= latency_slo_ms]
        if not viable:
            viable = candidates

        # Sort by cost
        viable.sort(key=lambda c: getattr(c, "estimated_cost_usd", c.cost_per_1k_tokens))

        return viable[:1]  # Return cheapest

    def _pure_quality_selection(self, candidates: list[Candidate], latency_slo_ms: int) -> list[Candidate]:
        """Pure quality-based selection (highest quality viable)."""
        # Filter by latency
        viable = [c for c in candidates if c.latency_p95 <= latency_slo_ms]
        if not viable:
            viable = candidates

        # Sort by quality
        viable.sort(key=lambda c: c.quality_pred, reverse=True)

        return viable[:1]  # Return highest quality

    def _balanced_selection(
        self, candidates: list[Candidate], quality_requirement: str, latency_slo_ms: int, preferences: dict[str, float]
    ) -> list[Candidate]:
        """Balanced selection using weighted scoring."""
        # This is similar to cost_aware_bandit but without exploration
        viable_candidates = [c for c in candidates if c.latency_p95 <= latency_slo_ms]
        if not viable_candidates:
            viable_candidates = candidates

        # Calculate scores synchronously (simplified version)
        scored_candidates = []
        for candidate in viable_candidates:
            # Simplified scoring without async calls
            estimated_cost = getattr(candidate, "estimated_cost_usd", candidate.cost_per_1k_tokens / 1000)
            cost_score = 1.0 / (1.0 + estimated_cost * 10)
            quality_score = candidate.quality_pred
            latency_score = 1.0 / (1.0 + candidate.latency_p95 / 1000.0)

            composite_score = (
                preferences["cost_weight"] * cost_score
                + preferences["quality_weight"] * quality_score
                + preferences["latency_weight"] * latency_score
            )

            scored_candidates.append((candidate, composite_score))

        # Sort by score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        return [scored_candidates[0][0]] if scored_candidates else []

    def _fallback_selection(
        self, candidates: list[Candidate], quality_requirement: str, latency_slo_ms: int
    ) -> list[Candidate]:
        """Fallback selection using original logic."""
        from ..routing_constants import QUALITY_THRESH

        q_min = QUALITY_THRESH.get(quality_requirement, 0.75)
        ordered = sorted(candidates, key=lambda c: c.cost_per_1k_tokens)

        # Find first viable candidate
        for candidate in ordered:
            if candidate.quality_pred >= q_min and candidate.latency_p95 <= latency_slo_ms:
                return [candidate]

        # Fallback to highest quality under latency or cheapest overall
        viable = [c for c in ordered if c.latency_p95 <= latency_slo_ms] or ordered
        if viable:
            return [max(viable, key=lambda c: c.quality_pred)]

        return []

    def _apply_local_preference(self, candidates: list[Candidate]) -> list[Candidate]:
        """Apply local model preference to selection."""
        if not candidates:
            return candidates

        # Separate local and cloud models
        local_models = [c for c in candidates if self._is_local_model(c.name)]
        cloud_models = [c for c in candidates if not self._is_local_model(c.name)]

        # If we have viable local models, prefer them
        if local_models:
            # Check if local model meets quality requirements
            best_local = max(local_models, key=lambda c: c.quality_pred)

            if best_local.quality_pred >= self.config.min_quality_threshold:
                # Prefer local model
                return [best_local] + cloud_models

        return candidates

    async def _record_selection(self, selected_candidates: list[Candidate], metadata: dict[str, Any]) -> None:
        """Record selection for performance tracking."""
        selection_record = {
            "timestamp": time.time(),
            "selected_models": [c.name for c in selected_candidates],
            "primary_model": selected_candidates[0].name if selected_candidates else None,
            "metadata": metadata,
        }

        self._selection_history.append(selection_record)

        # Keep only recent history (last 1000 selections)
        if len(self._selection_history) > 1000:
            self._selection_history = self._selection_history[-1000:]

    def get_selection_statistics(self) -> dict[str, Any]:
        """Get selection performance statistics."""
        if not self._selection_history:
            return {"error": "No selection history available"}

        # Analyze selection patterns
        model_selections = {}
        strategy_usage = {}

        for record in self._selection_history[-100:]:  # Last 100 selections
            primary_model = record.get("primary_model")
            if primary_model:
                model_selections[primary_model] = model_selections.get(primary_model, 0) + 1

            strategy = record.get("metadata", {}).get("selection_strategy", "unknown")
            strategy_usage[strategy] = strategy_usage.get(strategy, 0) + 1

        return {
            "total_selections": len(self._selection_history),
            "recent_selections": len(self._selection_history[-100:]),
            "most_selected_models": dict(sorted(model_selections.items(), key=lambda x: x[1], reverse=True)),
            "strategy_usage": strategy_usage,
            "config": {
                "cost_weight": self.config.cost_weight,
                "quality_weight": self.config.quality_weight,
                "latency_weight": self.config.latency_weight,
                "selection_strategy": self.config.selection_strategy,
            },
        }
