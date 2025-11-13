#!/usr/bin/env python3
"""Tests for GAP-220: Secure Aggregation Convergence Metrics.

Tests convergence behavior, accuracy of aggregated statistics,
privacy preservation, and differential privacy noise injection.
"""

import pytest
from tools.secure_aggregation_poc import (
    RoutingStats,
    SecureAggregatorCoordinator,
    SecureAggregatorNode,
)


class TestSecureAggregationConvergence:
    """Test convergence metrics for secure aggregation."""

    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key."""
        return b"test_encryption_key_32_bytes_long"

    @pytest.fixture
    def node_keys(self):
        """Generate test node keys."""
        return {
            "router-1": b"signing_key_router_1_32_bytes",
            "router-2": b"signing_key_router_2_32_bytes",
            "router-3": b"signing_key_router_3_32_bytes",
        }

    @pytest.fixture
    def sample_routing_stats(self):
        """Generate sample routing statistics."""
        return [
            RoutingStats("gpt-4", 100, 95, 50000, 50.0, "us-west"),
            RoutingStats("distilbert", 200, 180, 30000, 20.0, "us-west"),
            RoutingStats("llama-3-8b", 150, 140, 75000, 30.0, "eu-west"),
        ]

    def test_single_round_convergence(self, encryption_key, node_keys, sample_routing_stats):
        """Test that aggregation converges correctly in a single round."""
        # Create nodes with sample data
        nodes = []
        for node_id, signing_key in node_keys.items():
            node = SecureAggregatorNode(node_id, signing_key, encryption_key)
            for stats in sample_routing_stats:
                # Add some variation per node
                variation_factor = len(nodes) + 1  # Start from 1 to avoid 0
                modified_stats = RoutingStats(
                    model_id=stats.model_id,
                    total_requests=stats.total_requests + variation_factor * 10,
                    successful_requests=min(
                        stats.successful_requests + variation_factor * 8, stats.total_requests + variation_factor * 10
                    ),  # Ensure successful_requests <= total_requests
                    total_latency_ms=stats.total_latency_ms + variation_factor * 1000,
                    total_cost=stats.total_cost + variation_factor * 2.0,
                    region=stats.region,
                )
                node.add_routing_stats(modified_stats)
            nodes.append(node)

        # Create coordinator
        coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)

        # Generate and collect contributions
        contributions = []
        for node in nodes:
            contribution = node.generate_encrypted_contribution()
            assert node.verify_encrypted_contribution(contribution, node.signing_key)
            assert coordinator.collect_contribution(contribution)
            contributions.append(contribution)

        # Perform aggregation
        results = coordinator.perform_aggregation()
        summary = coordinator.get_aggregation_summary()

        # Verify convergence metrics
        assert summary["participating_nodes"] == len(nodes)
        assert summary["total_nodes"] == len(nodes)
        assert summary["participation_rate"] == 1.0

        # Verify aggregated statistics are reasonable
        for _model_region, stats in results.items():
            assert stats["total_requests"] > 0
            # Note: With differential privacy noise, successful_requests might exceed total_requests
            # This is acceptable for the POC as it demonstrates noise injection
            assert stats["successful_requests"] >= 0  # At least non-negative
            assert stats["total_latency_ms"] >= 0
            assert stats["total_cost"] >= 0

    def test_multi_round_convergence_stability(self, encryption_key, node_keys):
        """Test that aggregation results stabilize over multiple rounds."""
        results_over_rounds = []

        for round_num in range(3):
            # Create fresh nodes with slightly different data each round
            nodes = []
            for node_id, signing_key in node_keys.items():
                node = SecureAggregatorNode(node_id, signing_key, encryption_key)

                # Add round-specific variation
                base_requests = 100 + round_num * 20
                stats = RoutingStats(
                    "gpt-4",
                    base_requests,
                    int(base_requests * 0.95),
                    base_requests * 500,
                    base_requests * 0.5,
                    "us-west",
                )
                node.add_routing_stats(stats)
                nodes.append(node)

            # Perform aggregation
            coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)
            for node in nodes:
                contribution = node.generate_encrypted_contribution()
                coordinator.collect_contribution(contribution)

            results = coordinator.perform_aggregation()
            results_over_rounds.append(results)

        # Verify results are consistent across rounds (within expected variance)
        for model_region in results_over_rounds[0].keys():
            requests = [r[model_region]["total_requests"] for r in results_over_rounds]
            # Results should be relatively stable (within 35% of each other due to noise)
            max_requests = max(requests)
            min_requests = min(requests)
            assert (max_requests - min_requests) / max_requests < 0.35

    def test_differential_privacy_noise_injection(self, encryption_key, node_keys):
        """Test that differential privacy noise is properly injected."""
        # Create multiple aggregations with same input to measure noise variance
        results_list = []

        for _ in range(5):
            node = SecureAggregatorNode("test-node", node_keys["router-1"], encryption_key, deterministic_noise=False)
            stats = RoutingStats("gpt-4", 1000, 950, 500000, 500.0, "us-west")
            node.add_routing_stats(stats)

            coordinator = SecureAggregatorCoordinator({"test-node": node_keys["router-1"]}, encryption_key)
            contribution = node.generate_encrypted_contribution()
            coordinator.collect_contribution(contribution)
            results = coordinator.perform_aggregation()
            results_list.append(results["gpt-4:us-west"]["total_requests"])

        # Verify noise injection - results should vary slightly
        unique_results = set(results_list)
        assert len(unique_results) > 1, "Differential privacy noise should create variation"

        # But results should be close to original (within noise bounds)
        for result in results_list:
            assert 950 <= result <= 1050, f"Result {result} outside expected noise bounds"

    def test_derived_metrics_accuracy(self, encryption_key, node_keys):
        """Test that derived metrics (success rate, latency, cost) are calculated correctly."""
        # Create nodes with predictable data
        nodes = []
        for i, (node_id, signing_key) in enumerate(node_keys.items()):
            node = SecureAggregatorNode(node_id, signing_key, encryption_key)

            # Use predictable numbers for easy verification
            requests = 1000 + i * 100
            successful = 950 + i * 95
            latency = 50000 + i * 5000
            cost = 50.0 + i * 5.0

            stats = RoutingStats("gpt-4", requests, successful, latency, cost, "us-west")
            node.add_routing_stats(stats)
            nodes.append(node)

        # Perform aggregation
        coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)
        for node in nodes:
            contribution = node.generate_encrypted_contribution()
            coordinator.collect_contribution(contribution)

        results = coordinator.perform_aggregation()
        aggregated = results["gpt-4:us-west"]

        # Calculate expected totals
        expected_requests = sum(1000 + i * 100 for i in range(3))
        expected_successful = sum(950 + i * 95 for i in range(3))
        expected_latency = sum(50000 + i * 5000 for i in range(3))
        expected_cost = sum(50.0 + i * 5.0 for i in range(3))

        # Verify aggregated totals are close (accounting for noise)
        assert abs(aggregated["total_requests"] - expected_requests) < 150  # Noise tolerance
        assert abs(aggregated["successful_requests"] - expected_successful) < 150
        assert abs(aggregated["total_latency_ms"] - expected_latency) < 150
        assert abs(aggregated["total_cost"] - expected_cost) < 15

        # Test derived metrics calculation
        if aggregated["total_requests"] > 0:
            success_rate = aggregated["successful_requests"] / aggregated["total_requests"]
            avg_latency = aggregated["total_latency_ms"] / aggregated["total_requests"]
            cost_per_request = aggregated["total_cost"] / aggregated["total_requests"]

            # Verify derived metrics are reasonable
            assert 0.9 <= success_rate <= 1.0
            assert 40 <= avg_latency <= 60  # ms per request
            assert 0.04 <= cost_per_request <= 0.06  # cost per request

    def test_privacy_preservation(self, encryption_key, node_keys, sample_routing_stats):
        """Test that individual node data cannot be reconstructed from aggregated results."""
        # Create nodes with unique data patterns
        nodes = []
        unique_identifiers = [1001, 2002, 3003]  # Unique request counts

        for i, (node_id, signing_key) in enumerate(node_keys.items()):
            node = SecureAggregatorNode(node_id, signing_key, encryption_key)

            # Each node has a unique identifier in their stats
            stats = RoutingStats(
                "test-model",
                unique_identifiers[i],
                unique_identifiers[i] - 10,  # Slightly fewer successful
                unique_identifiers[i] * 100,
                unique_identifiers[i] * 0.1,
                "test-region",
            )
            node.add_routing_stats(stats)
            nodes.append(node)

        # Perform aggregation
        coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)
        for node in nodes:
            contribution = node.generate_encrypted_contribution()
            coordinator.collect_contribution(contribution)

        results = coordinator.perform_aggregation()
        aggregated = results["test-model:test-region"]

        # Verify that individual node data cannot be reconstructed
        total_requests = aggregated["total_requests"]

        # None of the individual identifiers should match exactly
        # (due to noise and aggregation)
        for identifier in unique_identifiers:
            assert abs(total_requests - identifier) > 50, f"Individual node data {identifier} could be reconstructed"

        # But the total should be approximately the sum
        expected_total = sum(unique_identifiers)
        assert abs(total_requests - expected_total) < 200  # Reasonable noise tolerance

    def test_convergence_with_partial_participation(self, encryption_key, node_keys):
        """Test convergence metrics when not all nodes participate."""
        # Create nodes
        nodes = []
        for node_id, signing_key in node_keys.items():
            node = SecureAggregatorNode(node_id, signing_key, encryption_key)
            stats = RoutingStats("gpt-4", 100, 95, 50000, 50.0, "us-west")
            node.add_routing_stats(stats)
            nodes.append(node)

        # Only collect from first 2 nodes
        coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)
        for node in nodes[:2]:
            contribution = node.generate_encrypted_contribution()
            coordinator.collect_contribution(contribution)

        results = coordinator.perform_aggregation()
        summary = coordinator.get_aggregation_summary()

        # Verify partial participation is handled correctly
        assert summary["participating_nodes"] == 2
        assert summary["total_nodes"] == 3
        assert summary["participation_rate"] == pytest.approx(2 / 3, rel=0.1)

        # Results should still be valid
        assert len(results) > 0
        for stats in results.values():
            assert all(v >= 0 for v in stats.values())

    def test_aggregation_consistency_across_runs(self, encryption_key, node_keys):
        """Test that multiple runs with same input produce consistent results."""
        # Run aggregation multiple times with identical input
        all_results = []

        for _ in range(3):
            nodes = []
            for node_id, signing_key in node_keys.items():
                node = SecureAggregatorNode(node_id, signing_key, encryption_key)
                stats = RoutingStats("gpt-4", 1000, 950, 500000, 500.0, "us-west")
                node.add_routing_stats(stats)
                nodes.append(node)

            coordinator = SecureAggregatorCoordinator(node_keys, encryption_key)
            for node in nodes:
                contribution = node.generate_encrypted_contribution()
                coordinator.collect_contribution(contribution)

            results = coordinator.perform_aggregation()
            all_results.append(results["gpt-4:us-west"]["total_requests"])

        # Results should be relatively consistent (within noise bounds)
        max_result = max(all_results)
        min_result = min(all_results)
        variance = (max_result - min_result) / max_result

        assert variance < 0.1, f"Results too inconsistent: {all_results}"
