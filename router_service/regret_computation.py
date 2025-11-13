"""GAP-345: Regret & savings computation service.

Provides baseline frontier cost model and regret calculation for SLM evaluation.
Regret measures how much more expensive a chosen model was compared to the optimal choice.
"""

import json
import os
from typing import Any

from metrics.registry import REGISTRY


class RegretComputationService:
    """Computes regret and savings against baseline frontier models."""

    def __init__(self) -> None:
        # GAP-345: Regret computation metrics
        self._slm_regret_pct = REGISTRY.gauge("slm_regret_pct")

        # Load model registry for baseline costs
        self._model_costs = self._load_model_costs()

        # Frontier model (most capable/costly baseline)
        self._frontier_model = self._identify_frontier_model()

    def _load_model_costs(self) -> dict[str, float]:
        """Load model cost estimates from registry."""
        costs = {}
        registry_path = os.path.join(os.path.dirname(__file__), "model_registry.json")

        try:
            with open(registry_path) as f:
                models = json.load(f)

            for model in models:
                model_name = model.get("model", "")
                # Use est_cost_per_1k_tokens_usd if available, otherwise estimate based on params
                if "est_cost_per_1k_tokens_usd" in model:
                    costs[model_name] = model["est_cost_per_1k_tokens_usd"]
                elif "params_b" in model:
                    # Rough heuristic: cost scales with model size
                    costs[model_name] = model["params_b"] * 0.001  # $0.001 per billion params per 1k tokens
                else:
                    # Default fallback cost
                    costs[model_name] = 0.01

        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback costs if registry unavailable
            costs = {
                "cheap-model": 0.005,
                "exp-model": 0.01,
                "mid-model": 0.015,
                "premium-model": 0.03,
                "openrouter:anthropic/claude-3.5-sonnet": 0.002,
            }

        return costs

    def _identify_frontier_model(self) -> str:
        """Identify the frontier model (highest capability/cost baseline)."""
        # For now, use the most expensive model as frontier
        if not self._model_costs:
            return "premium-model"

        return max(self._model_costs.items(), key=lambda x: x[1])[0]

    def get_frontier_cost_per_1k_tokens(self) -> float:
        """Get the frontier model's cost per 1k tokens."""
        return self._model_costs.get(self._frontier_model, 0.03)

    def calculate_regret(self, chosen_model: str, tokens_used: int, actual_cost_usd: float) -> dict[str, Any]:
        """Calculate regret metrics for a model choice.

        Args:
            chosen_model: The model that was selected
            tokens_used: Number of tokens consumed
            actual_cost_usd: Actual cost incurred

        Returns:
            Dict with regret_pct, savings_usd, and frontier_cost_usd
        """
        # Get costs per 1k tokens
        frontier_cost_per_1k = self.get_frontier_cost_per_1k_tokens()

        # Calculate what frontier would have cost for these tokens
        frontier_cost_usd = (tokens_used / 1000) * frontier_cost_per_1k

        # Regret is the difference (positive = we paid more than frontier)
        regret_usd = actual_cost_usd - frontier_cost_usd

        # Regret percentage (how much more we paid vs frontier)
        if frontier_cost_usd > 0:
            regret_pct = (regret_usd / frontier_cost_usd) * 100
        else:
            regret_pct = 0.0

        # Savings (negative regret = we saved money)
        savings_usd = -regret_usd

        # Update metric
        self._slm_regret_pct.set(regret_pct)

        return {
            "regret_pct": regret_pct,
            "savings_usd": savings_usd,
            "frontier_cost_usd": frontier_cost_usd,
            "actual_cost_usd": actual_cost_usd,
            "frontier_model": self._frontier_model,
        }

    def calculate_savings_pct(self, chosen_model: str, tokens_used: int, actual_cost_usd: float) -> float:
        """Calculate savings percentage vs frontier (positive = saved money)."""
        regret_data = self.calculate_regret(chosen_model, tokens_used, actual_cost_usd)
        return -float(regret_data["regret_pct"])  # Savings is negative regret


# Global instance
regret_service = RegretComputationService()
