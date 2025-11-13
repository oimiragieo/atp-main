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

"""Tests for GAP-373: Reinforcement Prior Update Integration."""

import time

from metrics.registry import (
    ACTIVE_PRIORS,
    PRIOR_UPDATES_APPLIED_TOTAL,
)
from router_service.federated_rewards import FederatedRewardSignal
from router_service.multi_objective_scorer import ObjectiveVector
from router_service.reinforcement_prior_integration import (
    PriorAwareMultiObjectiveScorer,
    ReinforcementPrior,
    ReinforcementPriorManager,
    get_prior_aware_scorer,
    get_prior_manager,
    update_priors_from_aggregation,
)


class TestReinforcementPrior:
    """Test the ReinforcementPrior class."""

    def test_prior_initialization(self):
        """Test prior initialization with default values."""
        prior = ReinforcementPrior(
            model_task_key="gpt-4:chat",
            success_rate_prior=0.9,
            latency_prior_ms=1000.0,
            quality_prior=0.8,
            sample_count=100,
            last_updated=time.time(),
            confidence=0.5
        )

        assert prior.model_task_key == "gpt-4:chat"
        assert prior.success_rate_prior == 0.9
        assert prior.latency_prior_ms == 1000.0
        assert prior.quality_prior == 0.8
        assert prior.sample_count == 100
        assert prior.confidence == 0.5

    def test_update_from_signal(self):
        """Test updating prior from federated reward signal."""
        prior = ReinforcementPrior(
            model_task_key="gpt-4:chat",
            success_rate_prior=0.8,
            latency_prior_ms=1200.0,
            quality_prior=0.7,
            sample_count=50,
            last_updated=time.time() - 100,
            confidence=0.3
        )

        # Create a signal with updated data
        reward_signals = {
            "gpt-4:chat": {
                "success_rate": 0.95,
                "avg_latency": 800.0,
                "quality_score": 0.9,
                "total_samples": 200
            }
        }
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )

        # Update the prior
        result = prior.update_from_signal(signal)
        assert result is True

        # Check that priors were updated
        assert prior.success_rate_prior > 0.8  # Should increase
        assert prior.latency_prior_ms < 1200.0  # Should decrease
        assert prior.quality_prior > 0.7  # Should increase
        assert prior.sample_count == 250  # 50 + 200
        assert prior.confidence == 0.25  # 250 / 1000 = 0.25
        assert prior.last_updated > time.time() - 10  # Recently updated

    def test_update_from_signal_wrong_key(self):
        """Test updating prior with wrong model/task key."""
        prior = ReinforcementPrior(
            model_task_key="gpt-4:chat",
            success_rate_prior=0.8,
            latency_prior_ms=1200.0,
            quality_prior=0.7,
            sample_count=50,
            last_updated=time.time(),
            confidence=0.3
        )

        # Create a signal with different key
        reward_signals = {
            "claude-3:chat": {
                "success_rate": 0.95,
                "avg_latency": 800.0,
                "total_samples": 200
            }
        }
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )

        # Update should fail
        result = prior.update_from_signal(signal)
        assert result is False

        # Prior should remain unchanged
        assert prior.success_rate_prior == 0.8
        assert prior.sample_count == 50

    def test_get_adjusted_score(self):
        """Test getting adjusted objective scores."""
        prior = ReinforcementPrior(
            model_task_key="gpt-4:chat",
            success_rate_prior=0.9,
            latency_prior_ms=1000.0,
            quality_prior=0.8,
            sample_count=1000,
            last_updated=time.time(),
            confidence=0.8
        )

        base_objectives = ObjectiveVector(
            cost=1.0,
            latency=1200.0,
            quality_score=0.7,
            carbon_intensity=100.0
        )

        adjusted = prior.get_adjusted_score(base_objectives)

        # Success rate adjustment (cost increase due to lower success)
        assert adjusted.cost > base_objectives.cost

        # Latency adjustment
        assert adjusted.latency > base_objectives.latency

        # Quality adjustment (should decrease quality score)
        assert adjusted.quality_score < base_objectives.quality_score

        # Carbon intensity should remain unchanged
        assert adjusted.carbon_intensity == base_objectives.carbon_intensity

    def test_get_adjusted_score_low_confidence(self):
        """Test that low confidence priors don't adjust scores."""
        prior = ReinforcementPrior(
            model_task_key="gpt-4:chat",
            success_rate_prior=0.9,
            latency_prior_ms=1000.0,
            quality_prior=0.8,
            sample_count=10,  # Low sample count = low confidence
            last_updated=time.time(),
            confidence=0.05  # Below threshold
        )

        base_objectives = ObjectiveVector(
            cost=1.0,
            latency=1200.0,
            quality_score=0.7,
            carbon_intensity=100.0
        )

        adjusted = prior.get_adjusted_score(base_objectives)

        # Should return base objectives unchanged
        assert adjusted.cost == base_objectives.cost
        assert adjusted.latency == base_objectives.latency
        assert adjusted.quality_score == base_objectives.quality_score
        assert adjusted.carbon_intensity == base_objectives.carbon_intensity


class TestReinforcementPriorManager:
    """Test the ReinforcementPriorManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ReinforcementPriorManager()

    def test_initialization(self):
        """Test manager initialization."""
        assert len(self.manager.priors) == 0
        assert self.manager.last_aggregation_round == 0

    def test_update_from_aggregated_signal(self):
        """Test updating priors from aggregated signal."""
        initial_updates = PRIOR_UPDATES_APPLIED_TOTAL.value
        initial_active = ACTIVE_PRIORS.value

        # Create aggregated signal
        reward_signals = {
            "gpt-4:chat": {
                "success_rate": 0.9,
                "avg_latency": 1000.0,
                "quality_score": 0.8,
                "total_samples": 100
            },
            "claude-3:code": {
                "success_rate": 0.85,
                "avg_latency": 1200.0,
                "total_samples": 80
            }
        }
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=5
        )

        # Update priors
        updates = self.manager.update_from_aggregated_signal(signal)

        assert updates == 2  # Two new priors created
        assert len(self.manager.priors) == 2
        assert self.manager.last_aggregation_round == 1

        # Check metrics
        assert PRIOR_UPDATES_APPLIED_TOTAL.value == initial_updates + 2
        assert ACTIVE_PRIORS.value == initial_active + 2

        # Check that priors were created
        assert "gpt-4:chat" in self.manager.priors
        assert "claude-3:code" in self.manager.priors

    def test_update_existing_priors(self):
        """Test updating existing priors."""
        # First update
        reward_signals = {
            "gpt-4:chat": {
                "success_rate": 0.8,
                "avg_latency": 1200.0,
                "total_samples": 50
            }
        }
        signal1 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal1)

        initial_sample_count = self.manager.priors["gpt-4:chat"].sample_count

        # Second update with same key
        reward_signals = {
            "gpt-4:chat": {
                "success_rate": 0.95,
                "avg_latency": 800.0,
                "total_samples": 75
            }
        }
        signal2 = FederatedRewardSignal(
            aggregation_round=2,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        updates = self.manager.update_from_aggregated_signal(signal2)

        assert updates == 1  # One prior updated
        assert self.manager.priors["gpt-4:chat"].sample_count == initial_sample_count + 75
        assert self.manager.last_aggregation_round == 2

    def test_skip_outdated_round(self):
        """Test skipping outdated aggregation rounds."""
        # Process round 5 first
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 100}}
        signal5 = FederatedRewardSignal(
            aggregation_round=5,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal5)

        # Try to process round 3 (should be skipped)
        signal3 = FederatedRewardSignal(
            aggregation_round=3,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        updates = self.manager.update_from_aggregated_signal(signal3)

        assert updates == 0  # Should be skipped
        assert self.manager.last_aggregation_round == 5  # Should remain 5

    def test_get_prior_for_model_task(self):
        """Test getting prior for specific model/task."""
        # Add a prior
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 100}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal)

        # Get existing prior
        prior = self.manager.get_prior_for_model_task("gpt-4:chat")
        assert prior is not None
        assert prior.model_task_key == "gpt-4:chat"

        # Get non-existing prior
        prior = self.manager.get_prior_for_model_task("nonexistent:model")
        assert prior is None

    def test_get_adjusted_objectives(self):
        """Test getting adjusted objectives."""
        # Add a prior
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 1000}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal)

        base_objectives = ObjectiveVector(
            cost=1.0,
            latency=1200.0,
            quality_score=0.7,
            carbon_intensity=100.0
        )

        # Get adjusted objectives
        adjusted = self.manager.get_adjusted_objectives("gpt-4:chat", base_objectives)

        # Should be different from base
        assert adjusted != base_objectives

        # Get adjusted for non-existing prior
        adjusted = self.manager.get_adjusted_objectives("nonexistent:model", base_objectives)
        assert adjusted == base_objectives  # Should return base unchanged

    def test_cleanup_stale_priors(self):
        """Test cleaning up stale priors."""
        # Add a prior
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 100}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal)

        assert len(self.manager.priors) == 1

        # Manually set the prior to be old
        self.manager.priors["gpt-4:chat"].last_updated = time.time() - 10000  # 10000 seconds ago

        # Clean up with reasonable max age
        removed = self.manager.cleanup_stale_priors(max_age_seconds=5000)
        assert removed == 1
        assert len(self.manager.priors) == 0


class TestPriorAwareMultiObjectiveScorer:
    """Test the PriorAwareMultiObjectiveScorer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ReinforcementPriorManager()
        self.scorer = PriorAwareMultiObjectiveScorer(self.manager)

    def test_initialization(self):
        """Test scorer initialization."""
        assert self.scorer.prior_manager is self.manager
        assert self.scorer.weights is not None

    def test_calculate_scalar_score_without_prior(self):
        """Test calculating score without prior."""
        objectives = ObjectiveVector(
            cost=1.0,
            latency=1000.0,
            quality_score=0.8,
            carbon_intensity=50.0
        )

        score = self.scorer.calculate_scalar_score(objectives)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_calculate_scalar_score_with_prior(self):
        """Test calculating score with prior adjustment."""
        # Add a prior
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 1000}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal)

        objectives = ObjectiveVector(
            cost=1.0,
            latency=1200.0,
            quality_score=0.7,
            carbon_intensity=50.0
        )

        # Score without prior
        score_without_prior = self.scorer.calculate_scalar_score(objectives)

        # Score with prior
        score_with_prior = self.scorer.calculate_scalar_score(objectives, "gpt-4:chat")

        # Scores should be different
        assert score_with_prior != score_without_prior

    def test_score_candidates(self):
        """Test scoring multiple candidates."""
        # Add priors
        reward_signals = {
            "gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 1000},
            "claude-3:chat": {"success_rate": 0.8, "avg_latency": 1200.0, "total_samples": 1000}
        }
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )
        self.manager.update_from_aggregated_signal(signal)

        candidates = [
            {
                "model_task_key": "gpt-4:chat",
                "objectives": ObjectiveVector(cost=1.0, latency=1100.0, quality_score=0.8, carbon_intensity=50.0),
                "model": "gpt-4"
            },
            {
                "model_task_key": "claude-3:chat",
                "objectives": ObjectiveVector(cost=0.8, latency=1300.0, quality_score=0.7, carbon_intensity=60.0),
                "model": "claude-3"
            }
        ]

        scored = self.scorer.score_candidates(candidates, {})

        assert len(scored) == 2
        assert "reinforcement_score" in scored[0]
        assert "adjusted_objectives" in scored[0]

        # Should be sorted by score (highest first)
        assert scored[0]["reinforcement_score"] >= scored[1]["reinforcement_score"]


class TestGlobalFunctions:
    """Test global functions and singleton pattern."""

    def test_get_prior_manager(self):
        """Test getting the global prior manager."""
        manager1 = get_prior_manager()
        manager2 = get_prior_manager()

        assert manager1 is manager2  # Should be the same instance

    def test_get_prior_aware_scorer(self):
        """Test getting the global prior-aware scorer."""
        scorer1 = get_prior_aware_scorer()
        scorer2 = get_prior_aware_scorer()

        assert scorer1 is scorer2  # Should be the same instance
        assert scorer1.prior_manager is get_prior_manager()

    def test_update_priors_from_aggregation(self):
        """Test the convenience function for updating priors."""
        reward_signals = {"gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1000.0, "total_samples": 100}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=3
        )

        updates = update_priors_from_aggregation(signal)
        assert updates == 1
