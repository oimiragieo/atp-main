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

"""Federated Reward Signal Schema (GAP-371).

Defines the schema for anonymous cluster statistics aggregation across routers
for privacy-preserving cross-tenant reinforcement signals.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from metrics import FEDERATED_REWARD_BATCHES_TOTAL

# Schema version for federated reward signals
FEDERATED_REWARD_SCHEMA_VERSION = 1

# JSON Schema for federated reward signal validation
FEDERATED_REWARD_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "FederatedRewardSignal",
    "type": "object",
    "required": [
        "schema_version",
        "aggregation_round",
        "cluster_hash",
        "reward_signals",
        "participant_count",
        "timestamp"
    ],
    "properties": {
        "schema_version": {
            "type": "integer",
            "const": FEDERATED_REWARD_SCHEMA_VERSION,
            "description": "Schema version for compatibility"
        },
        "aggregation_round": {
            "type": "integer",
            "minimum": 1,
            "description": "Federated learning round identifier"
        },
        "cluster_hash": {
            "type": "string",
            "minLength": 16,
            "maxLength": 64,
            "description": "Anonymous cluster identifier (SHA-256 hash)"
        },
        "reward_signals": {
            "type": "object",
            "description": "Aggregated reward signals by model/task combination",
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "required": ["success_rate", "avg_latency", "total_samples"],
                    "properties": {
                        "success_rate": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Fraction of successful requests"
                        },
                        "avg_latency": {
                            "type": "number",
                            "minimum": 0.0,
                            "description": "Average latency in seconds"
                        },
                        "total_samples": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Total number of samples aggregated"
                        },
                        "quality_score": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Average quality score (optional)"
                        },
                        "cost_efficiency": {
                            "type": "number",
                            "minimum": 0.0,
                            "description": "Cost per token efficiency metric"
                        }
                    }
                }
            },
            "additionalProperties": False
        },
        "participant_count": {
            "type": "integer",
            "minimum": 1,
            "description": "Number of routers contributing to this signal"
        },
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 timestamp of signal creation"
        },
        "privacy_budget_used": {
            "type": "number",
            "minimum": 0.0,
            "description": "Privacy budget consumed for this aggregation"
        },
        "noise_scale": {
            "type": "number",
            "minimum": 0.0,
            "description": "Differential privacy noise scale applied"
        }
    }
}


class FederatedRewardSignal:
    """Represents a federated reward signal for anonymous cluster statistics."""

    def __init__(
        self,
        aggregation_round: int,
        cluster_hash: str,
        reward_signals: dict[str, dict[str, Any]],
        participant_count: int,
        privacy_budget_used: float | None = None,
        noise_scale: float | None = None
    ):
        """Initialize a federated reward signal.

        Args:
            aggregation_round: Federated learning round identifier
            cluster_hash: Anonymous cluster identifier (SHA-256 hash)
            reward_signals: Aggregated reward signals by model/task combination
            participant_count: Number of routers contributing to this signal
            privacy_budget_used: Privacy budget consumed for this aggregation
            noise_scale: Differential privacy noise scale applied
        """
        self.schema_version = FEDERATED_REWARD_SCHEMA_VERSION
        self.aggregation_round = aggregation_round
        self.cluster_hash = cluster_hash
        self.reward_signals = reward_signals
        self.participant_count = participant_count
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.privacy_budget_used = privacy_budget_used
        self.noise_scale = noise_scale

    def to_dict(self) -> dict[str, Any]:
        """Convert the signal to a dictionary representation."""
        result = {
            "schema_version": self.schema_version,
            "aggregation_round": self.aggregation_round,
            "cluster_hash": self.cluster_hash,
            "reward_signals": self.reward_signals,
            "participant_count": self.participant_count,
            "timestamp": self.timestamp
        }

        if self.privacy_budget_used is not None:
            result["privacy_budget_used"] = self.privacy_budget_used
        if self.noise_scale is not None:
            result["noise_scale"] = self.noise_scale

        # Increment metric for federated reward batch creation
        FEDERATED_REWARD_BATCHES_TOTAL.inc()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'FederatedRewardSignal':
        """Create a FederatedRewardSignal from a dictionary."""
        # Validate input data before creating instance
        validation_errors = validate_federated_reward_signal(data)
        if validation_errors:
            raise ValueError(f"Invalid federated reward signal data: {validation_errors}")

        return cls(
            aggregation_round=data["aggregation_round"],
            cluster_hash=data["cluster_hash"],
            reward_signals=data["reward_signals"],
            participant_count=data["participant_count"],
            privacy_budget_used=data.get("privacy_budget_used"),
            noise_scale=data.get("noise_scale")
        )

    def to_json(self) -> str:
        """Convert the signal to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'FederatedRewardSignal':
        """Create a FederatedRewardSignal from JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON string: {e}") from e

        return cls.from_dict(data)


def create_cluster_hash(cluster_id: str, salt: str = "") -> str:
    """Create an anonymous cluster hash for privacy preservation.

    Args:
        cluster_id: Original cluster identifier
        salt: Optional salt for additional privacy

    Returns:
        SHA-256 hash of the cluster identifier
    """
    content = f"{cluster_id}:{salt}"
    return hashlib.sha256(content.encode()).hexdigest()


def validate_federated_reward_signal(data: dict[str, Any]) -> list[str]:
    """Validate a federated reward signal against the schema.

    Args:
        data: The data to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required fields
    required_fields = [
        "schema_version", "aggregation_round", "cluster_hash",
        "reward_signals", "participant_count", "timestamp"
    ]

    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Validate schema version
    if data["schema_version"] != FEDERATED_REWARD_SCHEMA_VERSION:
        errors.append(f"Invalid schema version: {data['schema_version']}, expected {FEDERATED_REWARD_SCHEMA_VERSION}")

    # Validate aggregation round
    if not isinstance(data["aggregation_round"], int) or data["aggregation_round"] < 1:
        errors.append("aggregation_round must be a positive integer")

    # Validate cluster hash
    if not isinstance(data["cluster_hash"], str) or len(data["cluster_hash"]) < 16:
        errors.append("cluster_hash must be a string of at least 16 characters")

    # Validate reward signals
    if not isinstance(data["reward_signals"], dict):
        errors.append("reward_signals must be an object")
    else:
        for key, signal in data["reward_signals"].items():
            if not isinstance(signal, dict):
                errors.append(f"reward_signals['{key}'] must be an object")
                continue

            required_signal_fields = ["success_rate", "avg_latency", "total_samples"]
            for field in required_signal_fields:
                if field not in signal:
                    errors.append(f"reward_signals['{key}'] missing required field: {field}")

            # Validate success_rate
            if "success_rate" in signal:
                rate = signal["success_rate"]
                if not isinstance(rate, (int, float)) or not (0.0 <= rate <= 1.0):
                    errors.append(f"reward_signals['{key}'].success_rate must be between 0.0 and 1.0")

            # Validate avg_latency
            if "avg_latency" in signal:
                latency = signal["avg_latency"]
                if not isinstance(latency, (int, float)) or latency < 0.0:
                    errors.append(f"reward_signals['{key}'].avg_latency must be non-negative")

            # Validate total_samples
            if "total_samples" in signal:
                samples = signal["total_samples"]
                if not isinstance(samples, int) or samples < 1:
                    errors.append(f"reward_signals['{key}'].total_samples must be a positive integer")

    # Validate participant count
    if not isinstance(data["participant_count"], int) or data["participant_count"] < 1:
        errors.append("participant_count must be a positive integer")

    # Validate optional fields
    if "privacy_budget_used" in data:
        budget = data["privacy_budget_used"]
        if not isinstance(budget, (int, float)) or budget < 0.0:
            errors.append("privacy_budget_used must be non-negative")

    if "noise_scale" in data:
        noise = data["noise_scale"]
        if not isinstance(noise, (int, float)) or noise < 0.0:
            errors.append("noise_scale must be non-negative")

    return errors


def aggregate_reward_signals(signals: list[FederatedRewardSignal]) -> FederatedRewardSignal | None:
    """Aggregate multiple federated reward signals from the same cluster.

    Args:
        signals: List of signals to aggregate (must be from same cluster and round)

    Returns:
        Aggregated signal or None if signals are incompatible
    """
    if not signals:
        return None

    # Validate all signals are from same cluster and round
    first_signal = signals[0]
    cluster_hash = first_signal.cluster_hash
    aggregation_round = first_signal.aggregation_round

    for signal in signals[1:]:
        if signal.cluster_hash != cluster_hash or signal.aggregation_round != aggregation_round:
            return None  # Incompatible signals

    # Aggregate reward signals
    aggregated_rewards = {}
    total_participants = sum(signal.participant_count for signal in signals)

    # Collect all model/task keys
    all_keys = set()
    for signal in signals:
        all_keys.update(signal.reward_signals.keys())

    for key in all_keys:
        # Collect all signals for this key
        key_signals = []
        total_weight = 0

        for signal in signals:
            if key in signal.reward_signals:
                signal_data = signal.reward_signals[key]
                weight = signal_data["total_samples"]
                key_signals.append((signal_data, weight))
                total_weight += weight

        if not key_signals:
            continue

        # Weighted average aggregation
        success_rate_sum = sum(sig["success_rate"] * weight for sig, weight in key_signals)
        latency_sum = sum(sig["avg_latency"] * weight for sig, weight in key_signals)
        total_samples = total_weight

        quality_sum = 0.0
        quality_count = 0
        cost_sum = 0.0
        cost_count = 0

        for sig, weight in key_signals:
            if "quality_score" in sig:
                quality_sum += sig["quality_score"] * weight
                quality_count += weight
            if "cost_efficiency" in sig:
                cost_sum += sig["cost_efficiency"] * weight
                cost_count += weight

        aggregated_signal = {
            "success_rate": success_rate_sum / total_weight,
            "avg_latency": latency_sum / total_weight,
            "total_samples": total_samples
        }

        if quality_count > 0:
            aggregated_signal["quality_score"] = quality_sum / quality_count
        if cost_count > 0:
            aggregated_signal["cost_efficiency"] = cost_sum / cost_count

        aggregated_rewards[key] = aggregated_signal

    # Aggregate privacy metrics
    total_privacy_budget = sum(
        signal.privacy_budget_used for signal in signals
        if signal.privacy_budget_used is not None
    )
    avg_noise_scale = sum(
        signal.noise_scale for signal in signals
        if signal.noise_scale is not None
    ) / len([s for s in signals if s.noise_scale is not None]) if any(s.noise_scale is not None for s in signals) else None

    return FederatedRewardSignal(
        aggregation_round=aggregation_round,
        cluster_hash=cluster_hash,
        reward_signals=aggregated_rewards,
        participant_count=total_participants,
        privacy_budget_used=total_privacy_budget if total_privacy_budget > 0 else None,
        noise_scale=avg_noise_scale
    )
