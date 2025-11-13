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

"""Tests for Federated Reward Signal Schema (GAP-371)."""

from datetime import datetime, timezone

from router_service.federated_rewards import (
    FEDERATED_REWARD_SCHEMA_VERSION,
    FederatedRewardSignal,
    aggregate_reward_signals,
    create_cluster_hash,
    validate_federated_reward_signal,
)


class TestFederatedRewardSignal:
    """Test cases for FederatedRewardSignal class."""

    def test_signal_creation(self):
        """Test basic signal creation and serialization."""
        reward_signals = {
            "gpt-4:chat": {
                "success_rate": 0.95,
                "avg_latency": 1.2,
                "total_samples": 1000,
                "quality_score": 0.88,
                "cost_efficiency": 0.002
            }
        }

        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="abc123def4567890",  # Must be at least 16 characters
            reward_signals=reward_signals,
            participant_count=5,
            privacy_budget_used=0.1,
            noise_scale=0.5
        )

        assert signal.schema_version == FEDERATED_REWARD_SCHEMA_VERSION
        assert signal.aggregation_round == 1
        assert signal.cluster_hash == "abc123def4567890"
        assert signal.participant_count == 5
        assert signal.privacy_budget_used == 0.1
        assert signal.noise_scale == 0.5

        # Test serialization
        data = signal.to_dict()
        assert data["schema_version"] == FEDERATED_REWARD_SCHEMA_VERSION
        assert data["aggregation_round"] == 1
        assert "timestamp" in data

        # Test deserialization
        signal2 = FederatedRewardSignal.from_dict(data)
        assert signal2.aggregation_round == signal.aggregation_round
        assert signal2.cluster_hash == signal.cluster_hash

    def test_json_serialization(self):
        """Test JSON serialization and deserialization."""
        signal = FederatedRewardSignal(
            aggregation_round=2,
            cluster_hash="hash1234567890123456",  # Must be at least 16 characters
            reward_signals={"model1:task1": {"success_rate": 0.9, "avg_latency": 2.0, "total_samples": 500}},
            participant_count=3
        )

        json_str = signal.to_json()
        signal2 = FederatedRewardSignal.from_json(json_str)

        assert signal2.aggregation_round == signal.aggregation_round
        assert signal2.reward_signals == signal.reward_signals

    def test_signal_without_optional_fields(self):
        """Test signal creation without optional privacy fields."""
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash456",
            reward_signals={"model1:task1": {"success_rate": 0.8, "avg_latency": 1.5, "total_samples": 200}},
            participant_count=2
        )

        assert signal.privacy_budget_used is None
        assert signal.noise_scale is None

        data = signal.to_dict()
        assert "privacy_budget_used" not in data
        assert "noise_scale" not in data


class TestClusterHash:
    """Test cases for cluster hash creation."""

    def test_cluster_hash_creation(self):
        """Test cluster hash generation."""
        cluster_id = "us-west-2-gpu-cluster"
        hash1 = create_cluster_hash(cluster_id)
        hash2 = create_cluster_hash(cluster_id)

        # Same input should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_cluster_hash_with_salt(self):
        """Test cluster hash with salt for additional privacy."""
        cluster_id = "us-west-2-gpu-cluster"
        hash1 = create_cluster_hash(cluster_id, "salt1")
        hash2 = create_cluster_hash(cluster_id, "salt2")

        # Different salts should produce different hashes
        assert hash1 != hash2
        assert len(hash1) == 64

    def test_cluster_hash_uniqueness(self):
        """Test that different cluster IDs produce different hashes."""
        hash1 = create_cluster_hash("cluster1")
        hash2 = create_cluster_hash("cluster2")

        assert hash1 != hash2


class TestValidation:
    """Test cases for signal validation."""

    def test_valid_signal_validation(self):
        """Test validation of a valid signal."""
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="a" * 32,  # 32 character hash
            reward_signals={
                "gpt-4:chat": {
                    "success_rate": 0.95,
                    "avg_latency": 1.2,
                    "total_samples": 1000
                }
            },
            participant_count=5
        )

        data = signal.to_dict()
        errors = validate_federated_reward_signal(data)
        assert len(errors) == 0

    def test_invalid_schema_version(self):
        """Test validation with invalid schema version."""
        data = {
            "schema_version": 999,
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("schema version" in error for error in errors)

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 1
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("timestamp" in error for error in errors)

    def test_invalid_aggregation_round(self):
        """Test validation with invalid aggregation round."""
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 0,  # Invalid: must be positive
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("aggregation_round" in error for error in errors)

    def test_invalid_cluster_hash(self):
        """Test validation with invalid cluster hash."""
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 1,
            "cluster_hash": "short",  # Too short
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("cluster_hash" in error for error in errors)

    def test_invalid_reward_signals(self):
        """Test validation with invalid reward signals."""
        # Missing required field in reward signal
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0}},  # Missing total_samples
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("total_samples" in error for error in errors)

    def test_invalid_success_rate(self):
        """Test validation with invalid success rate."""
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 1.5, "avg_latency": 1.0, "total_samples": 100}},  # > 1.0
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("success_rate" in error for error in errors)

    def test_invalid_participant_count(self):
        """Test validation with invalid participant count."""
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 0,  # Invalid: must be positive
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("participant_count" in error for error in errors)

    def test_optional_fields_validation(self):
        """Test validation of optional fields."""
        data = {
            "schema_version": FEDERATED_REWARD_SCHEMA_VERSION,
            "aggregation_round": 1,
            "cluster_hash": "a" * 32,
            "reward_signals": {"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            "participant_count": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "privacy_budget_used": -0.1  # Invalid: negative
        }

        errors = validate_federated_reward_signal(data)
        assert len(errors) > 0
        assert any("privacy_budget_used" in error for error in errors)


class TestAggregation:
    """Test cases for signal aggregation."""

    def test_aggregate_empty_list(self):
        """Test aggregation of empty signal list."""
        result = aggregate_reward_signals([])
        assert result is None

    def test_aggregate_single_signal(self):
        """Test aggregation of single signal."""
        signal = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={
                "gpt-4:chat": {
                    "success_rate": 0.9,
                    "avg_latency": 1.5,
                    "total_samples": 100
                }
            },
            participant_count=2
        )

        result = aggregate_reward_signals([signal])
        assert result is not None
        assert result.aggregation_round == 1
        assert result.cluster_hash == "hash123"
        assert result.participant_count == 2
        assert result.reward_signals["gpt-4:chat"]["success_rate"] == 0.9

    def test_aggregate_multiple_signals(self):
        """Test aggregation of multiple signals."""
        signal1 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={
                "gpt-4:chat": {
                    "success_rate": 0.8,
                    "avg_latency": 2.0,
                    "total_samples": 100,
                    "quality_score": 0.85
                }
            },
            participant_count=2,
            privacy_budget_used=0.1
        )

        signal2 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={
                "gpt-4:chat": {
                    "success_rate": 0.95,
                    "avg_latency": 1.0,
                    "total_samples": 200,
                    "quality_score": 0.90
                }
            },
            participant_count=3,
            privacy_budget_used=0.15
        )

        result = aggregate_reward_signals([signal1, signal2])
        assert result is not None
        assert result.aggregation_round == 1
        assert result.cluster_hash == "hash123"
        assert result.participant_count == 5  # 2 + 3

        # Check weighted average: (0.8*100 + 0.95*200) / (100+200) = (80 + 190) / 300 = 270/300 = 0.9
        assert abs(result.reward_signals["gpt-4:chat"]["success_rate"] - 0.9) < 0.001

        # Check latency: (2.0*100 + 1.0*200) / 300 = (200 + 200) / 300 = 400/300 ≈ 1.333
        assert abs(result.reward_signals["gpt-4:chat"]["avg_latency"] - 1.333) < 0.001

        # Check total samples
        assert result.reward_signals["gpt-4:chat"]["total_samples"] == 300

        # Check quality score: (0.85*100 + 0.90*200) / 300 = (85 + 180) / 300 = 265/300 ≈ 0.883
        assert abs(result.reward_signals["gpt-4:chat"]["quality_score"] - 0.883) < 0.001

        # Check privacy budget aggregation
        assert result.privacy_budget_used == 0.25  # 0.1 + 0.15

    def test_aggregate_incompatible_signals(self):
        """Test aggregation of incompatible signals."""
        signal1 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            participant_count=1
        )

        signal2 = FederatedRewardSignal(
            aggregation_round=2,  # Different round
            cluster_hash="hash123",
            reward_signals={"model:task": {"success_rate": 0.8, "avg_latency": 1.5, "total_samples": 100}},
            participant_count=1
        )

        result = aggregate_reward_signals([signal1, signal2])
        assert result is None

    def test_aggregate_different_clusters(self):
        """Test aggregation of signals from different clusters."""
        signal1 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={"model:task": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100}},
            participant_count=1
        )

        signal2 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash456",  # Different cluster
            reward_signals={"model:task": {"success_rate": 0.8, "avg_latency": 1.5, "total_samples": 100}},
            participant_count=1
        )

        result = aggregate_reward_signals([signal1, signal2])
        assert result is None

    def test_aggregate_with_missing_keys(self):
        """Test aggregation when some signals don't have certain keys."""
        signal1 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={
                "gpt-4:chat": {"success_rate": 0.9, "avg_latency": 1.0, "total_samples": 100},
                "gpt-3.5:chat": {"success_rate": 0.85, "avg_latency": 0.8, "total_samples": 50}
            },
            participant_count=1
        )

        signal2 = FederatedRewardSignal(
            aggregation_round=1,
            cluster_hash="hash123",
            reward_signals={
                "gpt-4:chat": {"success_rate": 0.95, "avg_latency": 1.2, "total_samples": 150}
                # Missing gpt-3.5:chat
            },
            participant_count=1
        )

        result = aggregate_reward_signals([signal1, signal2])
        assert result is not None

        # Both keys should be present
        assert "gpt-4:chat" in result.reward_signals
        assert "gpt-3.5:chat" in result.reward_signals

        # gpt-4:chat should be aggregated from both signals
        gpt4_signal = result.reward_signals["gpt-4:chat"]
        expected_success = (0.9 * 100 + 0.95 * 150) / (100 + 150)
        assert abs(gpt4_signal["success_rate"] - expected_success) < 0.001

        # gpt-3.5:chat should only come from signal1
        gpt35_signal = result.reward_signals["gpt-3.5:chat"]
        assert gpt35_signal["success_rate"] == 0.85
        assert gpt35_signal["total_samples"] == 50
