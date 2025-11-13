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

"""Secure Aggregation Protocol for Federated Reward Signals (GAP-372).

Extends the secure aggregation POC to work with federated reward signals,
providing privacy-preserving aggregation of reward statistics across routers.
"""

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from tools.secure_aggregation_poc import SimpleHomomorphicEncryption

from metrics import FEDERATED_ROUNDS_COMPLETED, SECURE_AGG_FAILURES_TOTAL
from router_service.federated_rewards import FederatedRewardSignal


@dataclass
class EncryptedRewardContribution:
    """Encrypted contribution of federated reward signals."""

    router_id: str
    aggregation_round: int
    cluster_hash: str
    encrypted_signals: dict[str, dict[str, str]]  # model_task -> field -> encrypted_value
    timestamp: float
    signature: str
    privacy_budget_used: float | None = None
    noise_scale: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "router_id": self.router_id,
            "aggregation_round": self.aggregation_round,
            "cluster_hash": self.cluster_hash,
            "encrypted_signals": self.encrypted_signals,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }
        if self.privacy_budget_used is not None:
            result["privacy_budget_used"] = self.privacy_budget_used
        if self.noise_scale is not None:
            result["noise_scale"] = self.noise_scale
        return result


class SecureRewardAggregatorNode:
    """Router node that participates in secure reward signal aggregation."""

    def __init__(self, router_id: str, signing_key: bytes, encryption_key: bytes, deterministic_noise: bool = True):
        self.router_id = router_id
        self.signing_key = signing_key
        self.encryption = SimpleHomomorphicEncryption(encryption_key)
        self.deterministic_noise = deterministic_noise

    def encrypt_reward_signal(
        self, signal: FederatedRewardSignal, noise_scale: float = 1.0, fixed_timestamp: float | None = None
    ) -> EncryptedRewardContribution:
        """Encrypt a federated reward signal for secure aggregation.

        Args:
            signal: The federated reward signal to encrypt
            noise_scale: Scale factor for differential privacy noise

        Returns:
            Encrypted contribution ready for aggregation
        """
        # Validate input signal before processing
        from router_service.federated_rewards import validate_federated_reward_signal

        validation_errors = validate_federated_reward_signal(signal.to_dict())
        if validation_errors:
            raise ValueError(f"Invalid federated reward signal: {validation_errors}")

        encrypted_signals = {}

        for model_task, reward_data in signal.reward_signals.items():
            encrypted_signals[model_task] = {}

            # Encrypt each numeric field with differential privacy noise
            for field, value in reward_data.items():
                if isinstance(value, (int, float)):
                    # Convert float to int for encryption (multiply by 1000 for precision)
                    if isinstance(value, float):
                        int_value = int(value * 1000)
                    else:
                        int_value = value

                    # Generate noise seed based on router_id, model_task, and field
                    noise_seed = hash(f"{self.router_id}:{model_task}:{field}:{signal.aggregation_round}") % 1000000

                    # Apply differential privacy noise
                    if self.deterministic_noise:
                        noise = int((hash(str(noise_seed)) % 100 - 50) * noise_scale)
                    else:
                        noise = int(secrets.randbelow(100) - 50) * int(noise_scale)

                    noisy_value = int_value + noise

                    encrypted_signals[model_task][field] = self.encryption.encrypt_int(
                        noisy_value, noise_seed, self.deterministic_noise
                    )

        # Create signature
        timestamp = fixed_timestamp if fixed_timestamp is not None else time.time()
        payload = json.dumps(
            {
                "router_id": self.router_id,
                "aggregation_round": signal.aggregation_round,
                "cluster_hash": signal.cluster_hash,
                "encrypted_signals": encrypted_signals,
                "timestamp": timestamp,
            },
            sort_keys=True,
        ).encode()

        signature = hmac.new(self.signing_key, payload, hashlib.sha256).hexdigest()

        return EncryptedRewardContribution(
            router_id=self.router_id,
            aggregation_round=signal.aggregation_round,
            cluster_hash=signal.cluster_hash,
            encrypted_signals=encrypted_signals,
            timestamp=timestamp,
            signature=signature,
            privacy_budget_used=signal.privacy_budget_used,
            noise_scale=noise_scale,
        )

    def verify_contribution(self, contribution: EncryptedRewardContribution, expected_key: bytes) -> bool:
        """Verify the signature of an encrypted contribution."""
        payload = json.dumps(
            {
                "router_id": contribution.router_id,
                "aggregation_round": contribution.aggregation_round,
                "cluster_hash": contribution.cluster_hash,
                "encrypted_signals": contribution.encrypted_signals,
                "timestamp": contribution.timestamp,
            },
            sort_keys=True,
        ).encode()

        expected_sig = hmac.new(expected_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(contribution.signature, expected_sig)


class SecureRewardAggregatorCoordinator:
    """Coordinator for secure aggregation of federated reward signals."""

    def __init__(self, router_keys: dict[str, bytes], encryption_key: bytes):
        self.router_keys = router_keys
        self.encryption = SimpleHomomorphicEncryption(encryption_key)
        self.contributions: dict[str, EncryptedRewardContribution] = {}

    def collect_contribution(self, contribution: EncryptedRewardContribution) -> bool:
        """Collect encrypted contribution from a router.

        Returns:
            True if contribution was accepted, False otherwise
        """
        # Verify router is authorized
        if contribution.router_id not in self.router_keys:
            SECURE_AGG_FAILURES_TOTAL.inc()
            return False

        # Verify signature
        if not self._verify_contribution(contribution):
            SECURE_AGG_FAILURES_TOTAL.inc()
            return False

        # Check for duplicate contributions from same router
        if contribution.router_id in self.contributions:
            SECURE_AGG_FAILURES_TOTAL.inc()
            return False

        self.contributions[contribution.router_id] = contribution
        return True

    def _verify_contribution(self, contribution: EncryptedRewardContribution) -> bool:
        """Verify a contribution's signature."""
        expected_key = self.router_keys.get(contribution.router_id)
        if not expected_key:
            return False

        payload = json.dumps(
            {
                "router_id": contribution.router_id,
                "aggregation_round": contribution.aggregation_round,
                "cluster_hash": contribution.cluster_hash,
                "encrypted_signals": contribution.encrypted_signals,
                "timestamp": contribution.timestamp,
            },
            sort_keys=True,
        ).encode()

        expected_sig = hmac.new(expected_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(contribution.signature, expected_sig)

    def perform_secure_aggregation(
        self, min_participants: int = 2, max_participants: int = 100
    ) -> FederatedRewardSignal | None:
        """Perform secure aggregation of all collected contributions.

        Args:
            min_participants: Minimum number of participants required
            max_participants: Maximum number of participants allowed

        Returns:
            Aggregated federated reward signal or None if aggregation fails
        """
        if len(self.contributions) < min_participants:
            SECURE_AGG_FAILURES_TOTAL.inc()
            return None

        if len(self.contributions) > max_participants:
            SECURE_AGG_FAILURES_TOTAL.inc()
            return None

        # Verify all contributions are for the same round and cluster
        first_contrib = next(iter(self.contributions.values()))
        target_round = first_contrib.aggregation_round
        target_cluster = first_contrib.cluster_hash

        for contrib in self.contributions.values():
            if contrib.aggregation_round != target_round or contrib.cluster_hash != target_cluster:
                SECURE_AGG_FAILURES_TOTAL.inc()
                return None

        # Group encrypted values by model_task and field
        aggregated_encrypted: dict[str, dict[str, list[str]]] = {}

        for contribution in self.contributions.values():
            for model_task, fields in contribution.encrypted_signals.items():
                if model_task not in aggregated_encrypted:
                    aggregated_encrypted[model_task] = {}

                for field, encrypted_value in fields.items():
                    if field not in aggregated_encrypted[model_task]:
                        aggregated_encrypted[model_task][field] = []
                    aggregated_encrypted[model_task][field].append(encrypted_value)

        # Aggregate encrypted values
        # Note: In this POC, we handle multi-key encryption by decrypting each contribution
        # In production, this would use proper multi-key homomorphic encryption
        aggregated_signals = {}

        for model_task, fields in aggregated_encrypted.items():
            aggregated_signals[model_task] = {}

            for field, encrypted_values in fields.items():
                decrypted_values = []

                # Try to decrypt each value (some may fail due to different keys)
                for enc_val in encrypted_values:
                    try:
                        # For POC: attempt to decrypt with coordinator's key
                        # In practice, this would use homomorphic operations
                        decrypted_value = self.encryption.decrypt_int(enc_val)
                        decrypted_values.append(decrypted_value)
                    except ValueError:
                        # If decryption fails, we can't aggregate this value
                        # In production, homomorphic encryption would handle this
                        continue

                if decrypted_values:
                    # Average the decrypted values
                    total_sum = sum(decrypted_values)
                    avg_value = total_sum / len(decrypted_values)

                    # Convert back from integer representation if it was a float
                    if field in ["success_rate", "avg_latency", "quality_score", "cost_efficiency"]:
                        aggregated_signals[model_task][field] = avg_value / 1000.0
                    else:
                        aggregated_signals[model_task][field] = int(avg_value)
                else:
                    # No values could be decrypted - set to 0
                    aggregated_signals[model_task][field] = (
                        0.0 if field in ["success_rate", "avg_latency", "quality_score", "cost_efficiency"] else 0
                    )

        # Calculate total privacy budget used
        total_privacy_budget = sum(
            contrib.privacy_budget_used
            for contrib in self.contributions.values()
            if contrib.privacy_budget_used is not None
        )

        # Calculate average noise scale
        noise_scales = [
            contrib.noise_scale for contrib in self.contributions.values() if contrib.noise_scale is not None
        ]
        avg_noise_scale = sum(noise_scales) / len(noise_scales) if noise_scales else None

        # Create aggregated signal
        aggregated_signal = FederatedRewardSignal(
            aggregation_round=target_round,
            cluster_hash=target_cluster,
            reward_signals=aggregated_signals,
            participant_count=len(self.contributions),
            privacy_budget_used=total_privacy_budget if total_privacy_budget > 0 else None,
            noise_scale=avg_noise_scale,
        )

        # Increment federated rounds completed metric
        FEDERATED_ROUNDS_COMPLETED.inc()

        return aggregated_signal

    def reset(self):
        """Reset the coordinator for a new aggregation round."""
        self.contributions.clear()


def create_secure_aggregation_keys(num_routers: int) -> dict[str, dict[str, bytes]]:
    """Create signing and encryption keys for secure aggregation.

    Args:
        num_routers: Number of routers to create keys for

    Returns:
        Dictionary mapping router_id to {'signing_key': bytes, 'encryption_key': bytes}
    """
    keys = {}
    for i in range(num_routers):
        router_id = f"router_{i}"
        keys[router_id] = {"signing_key": secrets.token_bytes(32), "encryption_key": secrets.token_bytes(32)}
    return keys
