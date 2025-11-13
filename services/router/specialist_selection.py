"""GAP-346: Specialist selection routing integration.

Provides constraint-based candidate scoring and fallback chain construction for SLM routing.
Integrates with task clustering and regret computation for optimal model selection.
"""

import os
from typing import Any, Optional

from metrics.registry import REGISTRY

from .task_clustering_pipeline import TaskClusteringPipeline


class SpecialistSelectionService:
    """Constraint-based specialist model selection with fallback chains."""

    def __init__(self) -> None:
        # GAP-346: Specialist selection metrics
        self._specialist_hit_rate = REGISTRY.gauge("specialist_hit_rate")

        # Load model registry
        self._model_registry = self._load_model_registry()

        # Initialize task clustering (will be trained separately)
        self._cluster_pipeline = TaskClusteringPipeline()

        # Selection constraints
        self._max_cost_per_1k_tokens = float(os.getenv("SPECIALIST_MAX_COST_PER_1K", "0.01"))
        self._min_quality_score = float(os.getenv("SPECIALIST_MIN_QUALITY", "0.7"))
        self._max_latency_ms = int(os.getenv("SPECIALIST_MAX_LATENCY_MS", "2000"))
        self._required_safety = os.getenv("SPECIALIST_SAFETY_GRADE", "A")

    def _load_model_registry(self) -> dict[str, dict[str, Any]]:
        """Load model registry into a lookup dict."""
        import json

        registry_path = os.path.join(os.path.dirname(__file__), "model_registry.json")

        registry = {}
        try:
            with open(registry_path) as f:
                models = json.load(f)
                for model in models:
                    registry[model["model"]] = model
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback registry
            registry = {
                "cheap-model": {
                    "model": "cheap-model",
                    "capabilities": ["summarize", "extract", "classify"],
                    "safety_grade": "A",
                    "status": "active",
                    "est_cost_per_1k_tokens_usd": 0.005,
                    "est_latency_ms": 900,
                },
                "exp-model": {
                    "model": "exp-model",
                    "capabilities": ["summarize", "classify"],
                    "safety_grade": "A",
                    "status": "shadow",
                    "est_cost_per_1k_tokens_usd": 0.01,
                    "est_latency_ms": 950,
                },
                "premium-model": {
                    "model": "premium-model",
                    "capabilities": ["reasoning", "code", "dialog"],
                    "safety_grade": "A",
                    "status": "fallback",
                    "est_cost_per_1k_tokens_usd": 0.03,
                    "est_latency_ms": 1400,
                },
            }

        return registry

    def select_specialist(
        self,
        task_description: str,
        quality_requirement: str = "balanced",
        max_cost_usd: float = 0.05,
        latency_slo_ms: int = 2000,
        required_capabilities: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Select optimal specialist model with fallback chain.

        Args:
            task_description: Description of the task for clustering
            quality_requirement: Quality level (fast/balanced/high)
            max_cost_usd: Maximum cost per request
            latency_slo_ms: Latency SLO in milliseconds
            required_capabilities: List of required model capabilities

        Returns:
            Selection result with primary model, fallback chain, and metadata
        """
        # Determine task cluster
        cluster_id = self._get_task_cluster(task_description)

        # Get candidate models for this cluster
        candidates = self._get_cluster_candidates(cluster_id, required_capabilities or [])

        # Score and rank candidates
        scored_candidates = self._score_candidates(candidates, quality_requirement, max_cost_usd, latency_slo_ms)

        # Build fallback chain
        primary, fallbacks = self._build_fallback_chain(scored_candidates)

        # Calculate hit rate (1.0 if we found a specialist, 0.0 if fell back to general)
        hit_rate = 1.0 if primary and primary != "premium-model" else 0.0
        self._specialist_hit_rate.set(hit_rate)

        return {
            "primary_model": primary,
            "fallback_chain": fallbacks,
            "cluster_id": cluster_id,
            "specialist_hit": hit_rate == 1.0,
            "total_candidates": len(candidates),
            "scored_candidates": len(scored_candidates),
        }

    def _get_task_cluster(self, task_description: str) -> str:
        """Get cluster ID for task description."""
        if not self._cluster_pipeline.is_trained:
            return "default"

        # Use clustering pipeline to classify task
        cluster_result = self._cluster_pipeline.classify_task(task_description)
        return cluster_result if cluster_result else "default"

    def _get_cluster_candidates(self, cluster_id: str, required_capabilities: list[str]) -> list[dict[str, Any]]:
        """Get candidate models for a cluster, filtered by capabilities."""
        candidates = []

        for _model_name, model_info in self._model_registry.items():
            # Filter by status (active or shadow)
            status = model_info.get("status", "active")
            if status not in ["active", "shadow"]:
                continue

            # Filter by safety grade
            safety_grade = model_info.get("safety_grade", "C")
            if safety_grade > self._required_safety:
                continue

            # Filter by capabilities if specified
            capabilities = model_info.get("capabilities", [])
            if required_capabilities and not all(cap in capabilities for cap in required_capabilities):
                continue

            candidates.append(model_info)

        return candidates

    def _score_candidates(
        self, candidates: list[dict[str, Any]], quality_requirement: str, max_cost_usd: float, latency_slo_ms: int
    ) -> list[tuple[dict[str, Any], float]]:
        """Score candidates based on constraints and return sorted list."""
        quality_thresholds = {"fast": 0.6, "balanced": 0.75, "high": 0.85}
        min_quality = quality_thresholds.get(quality_requirement, 0.75)

        scored = []

        for candidate in candidates:
            # Get cost estimate
            cost_per_1k = candidate.get("est_cost_per_1k_tokens_usd", 0.01)
            est_cost_usd = cost_per_1k * 10  # Assume ~10k tokens for scoring

            # Get latency estimate
            est_latency = candidate.get("est_latency_ms", 1000)

            # Basic quality estimate based on model size/capabilities
            quality_score = self._estimate_quality(candidate)

            # Constraint checks
            cost_ok = est_cost_usd <= max_cost_usd
            latency_ok = est_latency <= latency_slo_ms
            quality_ok = quality_score >= min_quality

            if not (cost_ok and latency_ok and quality_ok):
                continue

            # Score = combination of cost efficiency and quality
            # Lower cost = higher score, higher quality = higher score
            cost_score = 1.0 / (1.0 + est_cost_usd)  # Normalize cost (lower better)
            quality_score_norm = quality_score  # Already 0-1
            latency_score = 1.0 / (1.0 + est_latency / 1000.0)  # Normalize latency

            total_score = 0.4 * cost_score + 0.4 * quality_score_norm + 0.2 * latency_score

            scored.append((candidate, total_score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _estimate_quality(self, candidate: dict[str, Any]) -> float:
        """Estimate model quality based on capabilities and size."""
        capabilities = list(candidate.get("capabilities", []))
        params_b = float(candidate.get("params_b", 1.0))

        # Base quality from model size
        base_quality = min(0.95, params_b / 10.0)  # Larger models generally better

        # Capability bonuses
        capability_bonus = 0.0
        if "reasoning" in capabilities:
            capability_bonus += 0.1
        if "code" in capabilities:
            capability_bonus += 0.1
        if "dialog" in capabilities:
            capability_bonus += 0.05

        return min(1.0, base_quality + capability_bonus)

    def _build_fallback_chain(
        self, scored_candidates: list[tuple[dict[str, Any], float]]
    ) -> tuple[Optional[str], list[str]]:
        """Build primary model and fallback chain from scored candidates."""
        if not scored_candidates:
            return "premium-model", []  # Ultimate fallback

        primary = scored_candidates[0][0]["model"]
        fallbacks = [candidate[0]["model"] for candidate in scored_candidates[1:]]

        # Always include premium as final fallback
        if "premium-model" not in fallbacks and primary != "premium-model":
            fallbacks.append("premium-model")

        return primary, fallbacks


# Global instance
specialist_selector = SpecialistSelectionService()
