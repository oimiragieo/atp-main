"""Persona Federation Cluster POC
Simulates multiple routers exchanging signed persona statistics via federation.
Implements conflict resolution and reputation score aggregation.
"""

import hashlib
import random
import time
from typing import Any

from router_service.persona_federation import PersonaFederationNode, SignedPersonaStats
from router_service.reputation_model import ReputationModel


class PersonaFederationReflector:
    """Route reflector for persona statistics federation."""

    def __init__(self):
        self.subscribers: list[PersonaFederationNode] = []

    def subscribe(self, node: PersonaFederationNode):
        """Subscribe a node to federation updates."""
        self.subscribers.append(node)

    def propagate(self, signed_stats: SignedPersonaStats, key_lookup: dict[str, bytes]):
        """Propagate signed persona statistics to all subscribers."""
        for node in self.subscribers:
            if node.router_name == signed_stats.origin_router:
                continue  # Don't send back to origin
            node.ingest_federated_stats(signed_stats, key_lookup[signed_stats.origin_router])


class PersonaFederationCluster:
    """Federation cluster for persona statistics sharing."""

    def __init__(self, router_names: list[str]):
        self.router_names = router_names
        self.keys = {name: hashlib.sha256(f"key-{name}".encode()).digest() for name in router_names}
        self.nodes = {name: PersonaFederationNode(name, self.keys[name]) for name in router_names}
        self.reflector = PersonaFederationReflector()

        # Subscribe all nodes to federation
        for node in self.nodes.values():
            self.reflector.subscribe(node)

        # Initialize reputation models for each router
        self.reputation_models = {name: ReputationModel() for name in router_names}

    def simulate_persona_updates(self, persona_id: str, num_updates: int = 3):
        """Simulate persona statistics updates across the federation."""
        updates_propagated = 0

        for _i in range(num_updates):
            # Each router generates slightly different stats for the persona
            for _router_name, model in self.reputation_models.items():
                # Add some performance data with variation
                accuracy = 0.7 + random.uniform(-0.2, 0.3)  # 0.5 to 1.0
                latency = 100 + random.uniform(-50, 150)  # 50 to 250 ms
                quality = 0.8 + random.uniform(-0.2, 0.2)  # 0.6 to 1.0

                model.record_performance(
                    persona_id,
                    accuracy,
                    latency,
                    quality,
                    time.time() - random.uniform(0, 86400),  # Within last 24h
                )

            # Each router creates and propagates signed stats
            for router_name in self.router_names:
                node = self.nodes[router_name]
                model = self.reputation_models[router_name]

                signed_stats = node.create_signed_stats(persona_id, model)
                if signed_stats:
                    self.reflector.propagate(signed_stats, self.keys)
                    updates_propagated += 1

            # Small delay between rounds
            time.sleep(0.01)

        return updates_propagated

    def get_federation_stats(self, persona_id: str) -> dict[str, Any]:
        """Get comprehensive federation statistics."""
        total_federated = 0
        total_local = 0
        reputation_scores = []
        sample_counts = []

        for _router_name, node in self.nodes.items():
            # Count federated stats received
            if persona_id in node.federated_stats:
                total_federated += len(node.federated_stats[persona_id])

            # Count local stats
            if persona_id in node.local_stats:
                total_local += 1

            # Get consolidated stats
            consolidated = node.get_consolidated_stats(persona_id)
            if consolidated:
                reputation_scores.append(consolidated.reputation_score)
                sample_counts.append(consolidated.sample_count)

        return {
            "persona_id": persona_id,
            "routers_count": len(self.router_names),
            "total_federated_updates": total_federated,
            "total_local_updates": total_local,
            "avg_reputation_score": sum(reputation_scores) / len(reputation_scores) if reputation_scores else None,
            "total_samples": sum(sample_counts),
            "reputation_std_dev": self._calculate_std_dev(reputation_scores) if len(reputation_scores) > 1 else 0.0,
            "federation_coverage": total_federated / (len(self.router_names) * 3) if total_federated > 0 else 0.0,
        }

    def _calculate_std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation of values."""
        if len(values) <= 1:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance**0.5

    def demonstrate_conflict_resolution(self, persona_id: str):
        """Demonstrate conflict resolution with divergent persona stats."""
        # Create divergent reputation models
        for i, (_router_name, model) in enumerate(self.reputation_models.items()):
            # Create very different performance profiles
            base_accuracy = 0.6 + (i * 0.2)  # 0.6, 0.8, 1.0 for 3 routers

            for _ in range(20):  # More samples for stability
                accuracy = base_accuracy + random.uniform(-0.1, 0.1)
                latency = 200 - (i * 50) + random.uniform(-20, 20)  # Different latencies
                quality = 0.7 + (i * 0.15) + random.uniform(-0.1, 0.1)

                model.record_performance(
                    persona_id,
                    accuracy,
                    latency,
                    quality,
                    time.time() - random.uniform(0, 3600),  # Within last hour
                )

        # Propagate updates
        propagated = 0
        for router_name in self.router_names:
            node = self.nodes[router_name]
            model = self.reputation_models[router_name]

            signed_stats = node.create_signed_stats(persona_id, model)
            if signed_stats:
                self.reflector.propagate(signed_stats, self.keys)
                propagated += 1

        return propagated


def run_persona_federation_demo():
    """Run a demonstration of persona federation."""
    print("=== Persona Federation Cluster POC ===")

    # Create federation cluster
    cluster = PersonaFederationCluster(["router-alpha", "router-beta", "router-gamma"])

    # Simulate normal persona updates
    persona_id = "medical-consultant-001"
    print(f"\n1. Simulating normal updates for {persona_id}...")
    updates = cluster.simulate_persona_updates(persona_id, num_updates=2)
    print(f"   Propagated {updates} updates")

    # Get federation stats
    stats = cluster.get_federation_stats(persona_id)
    print("   Federation stats:")
    print(f"   - Average reputation: {stats['avg_reputation_score']:.3f}")
    print(f"   - Total samples: {stats['total_samples']}")
    print(f"   - Federation coverage: {stats['federation_coverage']:.2f}")

    # Demonstrate conflict resolution
    print("\n2. Demonstrating conflict resolution...")
    conflict_persona = "ai-assistant-002"
    conflict_updates = cluster.demonstrate_conflict_resolution(conflict_persona)
    print(f"   Propagated {conflict_updates} conflicting updates")

    conflict_stats = cluster.get_federation_stats(conflict_persona)
    print("   Conflict resolution stats:")
    print(f"   - Average reputation: {conflict_stats['avg_reputation_score']:.3f}")
    print(f"   - Reputation std dev: {conflict_stats['reputation_std_dev']:.3f}")
    print(f"   - Total samples: {conflict_stats['total_samples']}")

    # Verify consolidation works
    print("\n3. Verifying consolidation across routers...")
    for router_name, node in cluster.nodes.items():
        consolidated = node.get_consolidated_stats(conflict_persona)
        if consolidated:
            print(
                f"   {router_name}: reputation={consolidated.reputation_score:.3f}, samples={consolidated.sample_count}"
            )

    print("\n=== POC Complete ===")
    return stats, conflict_stats


if __name__ == "__main__":
    results = run_persona_federation_demo()

    # Basic validation
    normal_stats, conflict_stats = results
    success = (
        normal_stats["avg_reputation_score"] is not None
        and conflict_stats["avg_reputation_score"] is not None
        and normal_stats["federation_coverage"] > 0
        and conflict_stats["federation_coverage"] > 0
    )

    if success:
        print("SUCCESS: Persona federation POC passed")
    else:
        print("FAIL: Persona federation POC failed")
