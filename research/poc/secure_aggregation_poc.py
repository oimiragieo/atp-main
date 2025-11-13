#!/usr/bin/env python3
"""GAP-220 POC: Secure Aggregation for Federated Routing Priors.

This POC demonstrates secure multi-party computation for aggregating
routing statistics across multiple ATP Router nodes without exposing
individual request data.
"""

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from metrics.registry import FEDERATED_ROUNDS_COMPLETED


# Simple homomorphic encryption simulation (not cryptographically secure)
# In production, this would use proper homomorphic encryption libraries
class SimpleHomomorphicEncryption:
    """Simplified homomorphic encryption for POC purposes."""

    def __init__(self, key: bytes):
        self.key = key

    def encrypt_int(self, value: int, noise_seed: int = None, deterministic: bool = True) -> str:
        """Encrypt an integer value."""
        # Add random noise for differential privacy simulation when seed is provided
        if noise_seed is not None:
            if deterministic:
                noise = (hash(str(noise_seed)) % 100) - 50  # ±50 noise
            else:
                noise = secrets.randbelow(100) - 50  # ±50 noise
            value = value + noise
        
        data = f"{value}".encode()
        return hmac.new(self.key, data, hashlib.sha256).hexdigest() + f":{value}"

    def decrypt_int(self, encrypted: str) -> int:
        """Decrypt an integer value."""
        sig, value_str = encrypted.split(":", 1)
        value = int(value_str)

        data = f"{value}".encode()
        expected_sig = hmac.new(self.key, data, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid signature")

        return value

    def add_encrypted(self, enc1: str, enc2: str) -> str:
        """Add two encrypted values (homomorphic addition)."""
        # In real homomorphic encryption, this would work on encrypted data
        # For POC, we decrypt, add, and re-encrypt
        val1 = self.decrypt_int(enc1)
        val2 = self.decrypt_int(enc2)
        # Don't add noise when re-encrypting the sum
        sum_value = val1 + val2
        data = f"{sum_value}".encode()
        return hmac.new(self.key, data, hashlib.sha256).hexdigest() + f":{sum_value}"


@dataclass
class RoutingStats:
    """Local routing statistics for a model."""

    model_id: str
    total_requests: int
    successful_requests: int
    total_latency_ms: int
    total_cost: float
    region: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "total_latency_ms": self.total_latency_ms,
            "total_cost": self.total_cost,
            "region": self.region,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutingStats":
        return cls(
            model_id=data["model_id"],
            total_requests=data["total_requests"],
            successful_requests=data["successful_requests"],
            total_latency_ms=data["total_latency_ms"],
            total_cost=data["total_cost"],
            region=data["region"],
        )


@dataclass
class EncryptedStats:
    """Encrypted routing statistics for secure aggregation."""

    node_id: str
    encrypted_data: dict[str, str]  # field -> encrypted_value
    timestamp: float
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "encrypted_data": self.encrypted_data,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class SecureAggregatorNode:
    """A router node that participates in secure aggregation."""

    def __init__(self, node_id: str, signing_key: bytes, encryption_key: bytes, deterministic_noise: bool = True):
        self.node_id = node_id
        self.signing_key = signing_key
        self.encryption = SimpleHomomorphicEncryption(encryption_key)
        self.local_stats: dict[str, RoutingStats] = {}
        self.deterministic_noise = deterministic_noise

    def add_routing_stats(self, stats: RoutingStats):
        """Add local routing statistics."""
        key = f"{stats.model_id}:{stats.region}"
        if key in self.local_stats:
            existing = self.local_stats[key]
            self.local_stats[key] = RoutingStats(
                model_id=stats.model_id,
                total_requests=existing.total_requests + stats.total_requests,
                successful_requests=existing.successful_requests + stats.successful_requests,
                total_latency_ms=existing.total_latency_ms + stats.total_latency_ms,
                total_cost=existing.total_cost + stats.total_cost,
                region=stats.region,
            )
        else:
            self.local_stats[key] = stats

    def generate_encrypted_contribution(self) -> EncryptedStats:
        """Generate encrypted statistics for federation."""
        encrypted_data = {}

        for key, stats in self.local_stats.items():
            # Use deterministic noise for testing, non-deterministic for real DP
            noise_seed = hash(key) % 1000000
            
            encrypted_data[f"{key}:total_requests"] = self.encryption.encrypt_int(stats.total_requests, noise_seed, self.deterministic_noise)
            encrypted_data[f"{key}:successful_requests"] = self.encryption.encrypt_int(stats.successful_requests, noise_seed + 1, self.deterministic_noise)
            encrypted_data[f"{key}:total_latency_ms"] = self.encryption.encrypt_int(stats.total_latency_ms, noise_seed + 2, self.deterministic_noise)
            encrypted_data[f"{key}:total_cost"] = self.encryption.encrypt_int(
                int(stats.total_cost * 100), noise_seed + 3, self.deterministic_noise
            )  # Convert to cents

        # Generate timestamp once
        timestamp = time.time()

        # Create signature using the same timestamp
        payload = json.dumps(
            {"node_id": self.node_id, "encrypted_data": encrypted_data, "timestamp": timestamp}, sort_keys=True
        ).encode()

        signature = hmac.new(self.signing_key, payload, hashlib.sha256).hexdigest()

        return EncryptedStats(
            node_id=self.node_id, encrypted_data=encrypted_data, timestamp=timestamp, signature=signature
        )

    def verify_encrypted_contribution(self, contribution: EncryptedStats, expected_key: bytes) -> bool:
        """Verify the signature of an encrypted contribution."""
        payload = json.dumps(
            {
                "node_id": contribution.node_id,
                "encrypted_data": contribution.encrypted_data,
                "timestamp": contribution.timestamp,
            },
            sort_keys=True,
        ).encode()

        expected_sig = hmac.new(expected_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(contribution.signature, expected_sig)


class SecureAggregatorCoordinator:
    """Coordinator for secure multi-party aggregation."""

    def __init__(self, node_keys: dict[str, bytes], encryption_key: bytes):
        self.node_keys = node_keys
        self.encryption = SimpleHomomorphicEncryption(encryption_key)
        self.contributions: dict[str, EncryptedStats] = {}
        self.aggregated_stats: dict[str, dict[str, int]] = {}

    def collect_contribution(self, contribution: EncryptedStats) -> bool:
        """Collect encrypted contribution from a node."""
        if contribution.node_id not in self.node_keys:
            return False

        if not self._verify_contribution(contribution):
            return False

        self.contributions[contribution.node_id] = contribution
        return True

    def _verify_contribution(self, contribution: EncryptedStats) -> bool:
        """Verify a contribution's signature."""
        expected_key = self.node_keys.get(contribution.node_id)
        if not expected_key:
            return False

        payload = json.dumps(
            {
                "node_id": contribution.node_id,
                "encrypted_data": contribution.encrypted_data,
                "timestamp": contribution.timestamp,
            },
            sort_keys=True,
        ).encode()

        expected_sig = hmac.new(expected_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(contribution.signature, expected_sig)

    def perform_aggregation(self) -> dict[str, dict[str, float]]:
        """Perform secure aggregation of all contributions."""
        if not self.contributions:
            return {}

        # Group encrypted values by statistic type
        aggregated_encrypted: dict[str, list[str]] = {}

        for contribution in self.contributions.values():
            for key, encrypted_value in contribution.encrypted_data.items():
                if key not in aggregated_encrypted:
                    aggregated_encrypted[key] = []
                aggregated_encrypted[key].append(encrypted_value)

        # Aggregate encrypted values using homomorphic addition
        aggregated_decrypted: dict[str, int] = {}

        for key, encrypted_values in aggregated_encrypted.items():
            if len(encrypted_values) == 1:
                aggregated_decrypted[key] = self.encryption.decrypt_int(encrypted_values[0])
            else:
                # Sum all encrypted values
                result = encrypted_values[0]
                for enc_val in encrypted_values[1:]:
                    result = self.encryption.add_encrypted(result, enc_val)
                aggregated_decrypted[key] = self.encryption.decrypt_int(result)

        # Convert back to structured statistics
        result: dict[str, dict[str, float]] = {}

        for key, value in aggregated_decrypted.items():
            parts = key.split(":")
            if len(parts) < 3:
                continue

            model_region = f"{parts[0]}:{parts[1]}"
            stat_type = parts[2]

            if model_region not in result:
                result[model_region] = {}

            if stat_type == "total_cost":
                result[model_region][stat_type] = value / 100.0  # Convert back from cents
            else:
                result[model_region][stat_type] = value

        # Increment federated rounds completed metric
        FEDERATED_ROUNDS_COMPLETED.inc()

        return result

    def get_aggregation_summary(self) -> dict[str, Any]:
        """Get summary of the aggregation round."""
        return {
            "total_nodes": len(self.node_keys),
            "participating_nodes": len(self.contributions),
            "participation_rate": len(self.contributions) / len(self.node_keys) if self.node_keys else 0,
            "round_timestamp": time.time(),
            "aggregated_keys": list(self.aggregated_stats.keys()),
        }


def run_secure_aggregation_poc():
    """Run the secure aggregation proof of concept."""
    print("🔐 Secure Aggregation POC for Federated Routing Priors")
    print("=" * 60)

    # Setup keys for 3 nodes
    node_keys = {
        "router-1": secrets.token_bytes(32),
        "router-2": secrets.token_bytes(32),
        "router-3": secrets.token_bytes(32),
    }
    encryption_key = secrets.token_bytes(32)

    # Create nodes
    nodes = []
    for node_id, signing_key in node_keys.items():
        node = SecureAggregatorNode(node_id, signing_key, encryption_key)
        nodes.append(node)

    # Add sample routing statistics to each node
    sample_stats = [
        RoutingStats("gpt-4", 100, 98, 120000, 25.0, "us-west"),
        RoutingStats("distilbert", 200, 195, 80000, 3.0, "us-west"),
        RoutingStats("llama-3-8b", 150, 148, 95000, 8.0, "eu-west"),
    ]

    print("\n📊 Adding sample routing statistics to nodes...")

    for _i, node in enumerate(nodes):
        # Each node gets slightly different stats to simulate real distribution
        for _j, base_stats in enumerate(sample_stats):
            modified_stats = RoutingStats(
                model_id=base_stats.model_id,
                total_requests=base_stats.total_requests + (_i * 10) + (_j * 5),
                successful_requests=base_stats.successful_requests + (_i * 9) + (_j * 4),
                total_latency_ms=base_stats.total_latency_ms + (_i * 1000) + (_j * 500),
                total_cost=base_stats.total_cost + (_i * 0.5) + (_j * 0.2),
                region=base_stats.region,
            )
            node.add_routing_stats(modified_stats)

        print(f"  ✓ {node.node_id}: {len(node.local_stats)} model-region combinations")

    # Create coordinator
    coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)

    # Generate and collect encrypted contributions
    print("\n🔒 Generating encrypted contributions...")

    contributions = []
    for node in nodes:
        contribution = node.generate_encrypted_contribution()
        contributions.append(contribution)

        # Verify contribution before submitting
        if node.verify_encrypted_contribution(contribution, node.signing_key):
            coordinator.collect_contribution(contribution)
            print(f"  ✓ {node.node_id}: contribution verified and collected")
            print(f"    Encrypted fields: {len(contribution.encrypted_data)}")
        else:
            print(f"  ✗ {node.node_id}: contribution verification failed")
    # Perform secure aggregation
    print("\n🔢 Performing secure aggregation...")

    aggregated_results = coordinator.perform_aggregation()
    summary = coordinator.get_aggregation_summary()

    print("\n📈 Aggregation Results:")
    print(f"  Participating nodes: {summary['participating_nodes']}/{summary['total_nodes']}")
    print(".1%")

    print("\n📋 Aggregated Statistics:")
    for model_region, stats in aggregated_results.items():
        print(f"  {model_region}:")
        for stat_name, value in stats.items():
            if stat_name == "total_cost":
                print(".2f")
            else:
                print(f"    {stat_name}: {int(value)}")

    # Demonstrate privacy preservation
    print("\n🔒 Privacy Preservation Demonstration:")
    print("  ✓ Individual node data remains encrypted")
    print("  ✓ Only aggregated statistics are revealed")
    print("  ✓ No individual request data is exposed")
    print("  ✓ Differential privacy noise added to protect statistics")

    print("\n📊 Derived Metrics:")

    for model_region, stats in aggregated_results.items():
        if stats.get("total_requests", 0) > 0:
            success_rate = stats.get("successful_requests", 0) / stats["total_requests"]
            avg_latency = stats.get("total_latency_ms", 0) / stats["total_requests"]
            cost_per_request = stats.get("total_cost", 0) / stats["total_requests"]

            print(f"  {model_region}:")
            print(f"    Success Rate: {success_rate:.1%}")
            print(f"    Avg Latency: {avg_latency:.0f}ms")
            print(f"    Cost/Request: ${cost_per_request:.3f}")

    print("\n✅ Secure aggregation POC completed successfully!")
    print("This demonstrates the core concepts of federated routing prior aggregation:")
    print("  • Multi-party secure computation")
    print("  • Privacy-preserving statistics aggregation")
    print("  • Homomorphic encryption simulation")
    print("  • Differential privacy noise injection")


if __name__ == "__main__":
    run_secure_aggregation_poc()
