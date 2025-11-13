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

"""Tests for Secure Aggregation Protocol for Federated Reward Signals (GAP-372)."""

from metrics import SECURE_AGG_FAILURES_TOTAL
from router_service.federated_rewards import FederatedRewardSignal
from router_service.secure_reward_aggregation import (
    SecureRewardAggregatorCoordinator,
    SecureRewardAggregatorNode,
    create_secure_aggregation_keys,
)


class TestSecureRewardAggregation:
    """Basic tests for secure reward aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.keys = create_secure_aggregation_keys(3)
        self.shared_encryption_key = b"shared_encryption_key_32_bytes"
        self.coordinator = SecureRewardAggregatorCoordinator(
            router_keys={router_id: keys['signing_key'] for router_id, keys in self.keys.items()},
            encryption_key=self.shared_encryption_key
        )

    def test_basic_aggregation(self):
        """Test basic secure aggregation functionality."""
        # Create and collect contributions from multiple routers
        for router_id in ["router_0", "router_1"]:
            node = SecureRewardAggregatorNode(
                router_id=router_id,
                signing_key=self.keys[router_id]['signing_key'],
                encryption_key=self.shared_encryption_key
            )

            reward_signals = {
                "gpt-4:chat": {
                    "success_rate": 0.9,
                    "avg_latency": 1.0,
                    "total_samples": 100
                }
            }
            signal = FederatedRewardSignal(
                aggregation_round=1,
                cluster_hash="test_cluster_1234567890",
                reward_signals=reward_signals,
                participant_count=1
            )

            contribution = node.encrypt_reward_signal(signal)
            result = self.coordinator.collect_contribution(contribution)
            assert result is True

        # Perform aggregation
        aggregated_signal = self.coordinator.perform_secure_aggregation(min_participants=2)

        assert aggregated_signal is not None
        assert aggregated_signal.aggregation_round == 1
        assert aggregated_signal.cluster_hash == "test_cluster_1234567890"
        assert aggregated_signal.participant_count == 2
        assert "gpt-4:chat" in aggregated_signal.reward_signals

    def test_unauthorized_contribution(self):
        """Test rejection of unauthorized contributions."""
        # Create contribution from unauthorized router
        unauthorized_node = SecureRewardAggregatorNode(
            router_id="unauthorized_router",
            signing_key=b"unauthorized_key_32_bytes_long",
            encryption_key=self.shared_encryption_key
        )

        reward_signals = {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}}
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="test_cluster_1234567890",
            reward_signals=reward_signals,
            participant_count=1
        )

        contribution = unauthorized_node.encrypt_reward_signal(signal)

        initial_failures = SECURE_AGG_FAILURES_TOTAL.value
        result = self.coordinator.collect_contribution(contribution)

        assert result is False
        assert SECURE_AGG_FAILURES_TOTAL.value == initial_failures + 1

    def test_insufficient_participants(self):
        """Test aggregation fails with insufficient participants."""
        initial_failures = SECURE_AGG_FAILURES_TOTAL.value
        result = self.coordinator.perform_secure_aggregation(min_participants=2)

        assert result is None
        assert SECURE_AGG_FAILURES_TOTAL.value == initial_failures + 1
