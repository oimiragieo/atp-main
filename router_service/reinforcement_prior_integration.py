# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GAP-373: Reinforcement Prior Update Integration.

This module integrates aggregated federated reward signals into routing score calculations,
enabling reinforcement learning across the router federation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from metrics.registry import (
    ACTIVE_PRIORS,
    PRIOR_UPDATE_FAILURES_TOTAL,
    PRIOR_UPDATE_LATENCY_SECONDS,
    PRIOR_UPDATES_APPLIED_TOTAL,
)
from router_service.federated_rewards import FederatedRewardSignal
from router_service.multi_objective_scorer import MultiObjectiveScorer, ObjectiveVector

logger = logging.getLogger(__name__)

# Metrics for reinforcement prior updates
CTR_PRIOR_UPDATES_APPLIED = PRIOR_UPDATES_APPLIED_TOTAL
CTR_PRIOR_UPDATE_FAILURES = PRIOR_UPDATE_FAILURES_TOTAL
GAUGE_ACTIVE_PRIORS = ACTIVE_PRIORS
HIST_PRIOR_UPDATE_LATENCY = PRIOR_UPDATE_LATENCY_SECONDS


@dataclass
class ReinforcementPrior:
    """A reinforcement learning prior for model/task combinations."""

    model_task_key: str  # e.g., "gpt-4:chat", "claude-3:code"
    success_rate_prior: float  # Bayesian prior for success rate (0-1)
    latency_prior_ms: float  # Bayesian prior for latency in milliseconds
    quality_prior: float  # Bayesian prior for quality score (0-1)
    sample_count: int  # Number of samples contributing to this prior
    last_updated: float  # Timestamp of last update
    confidence: float  # Confidence in the prior (0-1)

    def update_from_signal(self, signal: FederatedRewardSignal) -> bool:
        """Update this prior from a federated reward signal.

        Uses Bayesian updating to incorporate new evidence.
        """
        # Validate input signal before processing
        from router_service.federated_rewards import validate_federated_reward_signal

        validation_errors = validate_federated_reward_signal(signal.to_dict())
        if validation_errors:
            logger.warning(f"Invalid federated reward signal in update_from_signal: {validation_errors}")
            return False

        if self.model_task_key not in signal.reward_signals:
            return False

        reward_data = signal.reward_signals[self.model_task_key]

        # Bayesian update for success rate
        # Prior: Beta distribution with alpha = success_rate_prior * sample_count
        # Posterior: Add new observations
        prior_alpha = self.success_rate_prior * self.sample_count
        prior_beta = (1 - self.success_rate_prior) * self.sample_count

        new_successes = int(reward_data["success_rate"] * reward_data["total_samples"])
        new_failures = reward_data["total_samples"] - new_successes

        posterior_alpha = prior_alpha + new_successes
        posterior_beta = prior_beta + new_failures
        self.success_rate_prior = posterior_alpha / (posterior_alpha + posterior_beta)

        # Update latency prior (simple exponential moving average)
        alpha = 0.1  # Learning rate
        self.latency_prior_ms = (1 - alpha) * self.latency_prior_ms + alpha * reward_data["avg_latency"]

        # Update quality prior if available
        if "quality_score" in reward_data:
            self.quality_prior = (1 - alpha) * self.quality_prior + alpha * reward_data["quality_score"]

        # Update sample count and confidence
        self.sample_count += reward_data["total_samples"]
        self.last_updated = time.time()

        # Confidence increases with more samples (diminishing returns)
        self.confidence = min(1.0, self.sample_count / 1000.0)

        return True

    def get_adjusted_score(self, base_objectives: ObjectiveVector) -> ObjectiveVector:
        """Get adjusted objective vector incorporating this prior."""
        if self.confidence < 0.1:  # Not enough confidence
            return base_objectives

        # Adjust success rate (inverted to cost for minimization)
        success_adjustment = (1 - self.success_rate_prior) * self.confidence

        # Adjust latency
        latency_adjustment = self.latency_prior_ms * self.confidence

        # Adjust quality (negative because we want to maximize quality)
        quality_adjustment = (1 - self.quality_prior) * self.confidence

        return ObjectiveVector(
            cost=base_objectives.cost + success_adjustment,
            latency=base_objectives.latency + latency_adjustment,
            quality_score=max(0, base_objectives.quality_score - quality_adjustment),
            carbon_intensity=base_objectives.carbon_intensity,  # No prior for carbon yet
        )


class ReinforcementPriorManager:
    """Manages reinforcement priors for routing decisions."""

    def __init__(self):
        self.priors: dict[str, ReinforcementPrior] = {}
        self.last_aggregation_round: int = 0

    def update_from_aggregated_signal(self, aggregated_signal: FederatedRewardSignal) -> int:
        """Update priors from an aggregated federated reward signal.

        Returns the number of priors updated.
        """
        # Validate input signal before processing
        from router_service.federated_rewards import validate_federated_reward_signal

        validation_errors = validate_federated_reward_signal(aggregated_signal.to_dict())
        if validation_errors:
            logger.warning(f"Invalid aggregated federated reward signal: {validation_errors}")
            return 0

        start_time = time.time()
        updates_applied = 0

        try:
            # Check if this is a new aggregation round
            if aggregated_signal.aggregation_round <= self.last_aggregation_round:
                logger.debug(f"Skipping outdated aggregation round {aggregated_signal.aggregation_round}")
                return 0

            self.last_aggregation_round = aggregated_signal.aggregation_round

            # Update priors for each model/task combination
            for model_task_key, reward_data in aggregated_signal.reward_signals.items():
                if model_task_key not in self.priors:
                    # Initialize new prior
                    self.priors[model_task_key] = ReinforcementPrior(
                        model_task_key=model_task_key,
                        success_rate_prior=reward_data["success_rate"],
                        latency_prior_ms=reward_data["avg_latency"],
                        quality_prior=reward_data.get("quality_score", 0.5),
                        sample_count=reward_data["total_samples"],
                        last_updated=time.time(),
                        confidence=min(1.0, reward_data["total_samples"] / 100.0),
                    )
                    updates_applied += 1  # Count new prior creation as an update
                else:
                    # Update existing prior
                    if self.priors[model_task_key].update_from_signal(aggregated_signal):
                        updates_applied += 1

            CTR_PRIOR_UPDATES_APPLIED.inc(updates_applied)
            GAUGE_ACTIVE_PRIORS.set(len(self.priors))

            update_time = time.time() - start_time
            HIST_PRIOR_UPDATE_LATENCY.observe(update_time)

            logger.info(
                f"Applied {updates_applied} prior updates from aggregation round {aggregated_signal.aggregation_round}"
            )
            return updates_applied

        except Exception as e:
            CTR_PRIOR_UPDATE_FAILURES.inc()
            logger.error(f"Failed to update priors from aggregated signal: {e}")
            return 0

    def get_prior_for_model_task(self, model_task_key: str) -> ReinforcementPrior | None:
        """Get the reinforcement prior for a specific model/task combination."""
        return self.priors.get(model_task_key)

    def get_adjusted_objectives(self, model_task_key: str, base_objectives: ObjectiveVector) -> ObjectiveVector:
        """Get adjusted objective vector incorporating reinforcement priors."""
        prior = self.get_prior_for_model_task(model_task_key)
        if prior is None:
            return base_objectives

        return prior.get_adjusted_score(base_objectives)

    def cleanup_stale_priors(self, max_age_seconds: float = 86400 * 7) -> int:
        """Remove priors that haven't been updated recently.

        Returns the number of priors removed.
        """
        current_time = time.time()
        stale_keys = [key for key, prior in self.priors.items() if current_time - prior.last_updated > max_age_seconds]

        for key in stale_keys:
            del self.priors[key]

        if stale_keys:
            logger.info(f"Cleaned up {len(stale_keys)} stale priors")
            GAUGE_ACTIVE_PRIORS.set(len(self.priors))

        return len(stale_keys)


class PriorAwareMultiObjectiveScorer(MultiObjectiveScorer):
    """Multi-objective scorer that incorporates reinforcement priors."""

    def __init__(self, prior_manager: ReinforcementPriorManager | None = None):
        super().__init__()
        self.prior_manager = prior_manager or ReinforcementPriorManager()

    def calculate_scalar_score(self, objectives: ObjectiveVector, model_task_key: str | None = None) -> float:
        """Calculate weighted scalar score with optional prior adjustment."""
        # Apply reinforcement prior if available
        if model_task_key and self.prior_manager:
            adjusted_objectives = self.prior_manager.get_adjusted_objectives(model_task_key, objectives)
        else:
            adjusted_objectives = objectives

        # Use parent implementation with adjusted objectives
        return super().calculate_scalar_score(adjusted_objectives)

    def score_candidates(self, candidates: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Score multiple candidates with reinforcement prior integration.

        Args:
            candidates: List of candidate dictionaries with 'model_task_key' and 'objectives'
            context: Context information (unused for now)

        Returns:
            Candidates sorted by score (highest first)
        """
        scored_candidates = []

        for candidate in candidates:
            model_task_key = candidate.get("model_task_key")
            objectives = candidate.get("objectives")

            if not isinstance(objectives, ObjectiveVector):
                # Convert dict to ObjectiveVector if needed
                objectives = ObjectiveVector(**objectives)

            score = self.calculate_scalar_score(objectives, model_task_key)
            scored_candidates.append(
                {
                    **candidate,
                    "reinforcement_score": score,
                    "adjusted_objectives": self.prior_manager.get_adjusted_objectives(model_task_key, objectives)
                    if model_task_key
                    else objectives,
                }
            )

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x["reinforcement_score"], reverse=True)
        return scored_candidates


# Global instance for singleton pattern
_prior_manager: ReinforcementPriorManager | None = None
_prior_aware_scorer: PriorAwareMultiObjectiveScorer | None = None


def get_prior_manager() -> ReinforcementPriorManager:
    """Get the global reinforcement prior manager instance."""
    global _prior_manager
    if _prior_manager is None:
        _prior_manager = ReinforcementPriorManager()
    return _prior_manager


def get_prior_aware_scorer() -> PriorAwareMultiObjectiveScorer:
    """Get the global prior-aware multi-objective scorer instance."""
    global _prior_aware_scorer
    if _prior_aware_scorer is None:
        _prior_aware_scorer = PriorAwareMultiObjectiveScorer(get_prior_manager())
    return _prior_aware_scorer


def update_priors_from_aggregation(aggregated_signal: FederatedRewardSignal) -> int:
    """Convenience function to update priors from aggregated signal.

    Returns the number of priors updated.
    """
    return get_prior_manager().update_from_aggregated_signal(aggregated_signal)
