#!/usr/bin/env python3
"""
Pod Distribution Testing Script for ATP Router

This script tests the pod distribution across zones and nodes to ensure
anti-affinity and topology spread constraints are working correctly.
"""

import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class PodInfo:
    """Information about a pod's location."""

    name: str
    node: str
    zone: str
    status: str


@dataclass
class DistributionMetrics:
    """Metrics for pod distribution analysis."""

    total_pods: int
    nodes_used: int
    zones_used: int
    pods_per_node: dict[str, int]
    pods_per_zone: dict[str, int]
    zone_spread_score: float
    node_spread_score: float


class PodDistributionTester:
    """Test pod distribution across Kubernetes cluster."""

    def __init__(self, namespace: str = "default", deployment_name: str = "atp-router"):
        self.namespace = namespace
        self.deployment_name = deployment_name

    def run_kubectl_command(self, command: list[str]) -> str:
        """Run a kubectl command and return the output."""
        try:
            result = subprocess.run(["kubectl"] + command, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error running kubectl command: {e}")
            print(f"stderr: {e.stderr}")
            return ""

    def get_pod_distribution(self) -> list[PodInfo]:
        """Get current pod distribution information."""
        # Get pods with their node and zone information
        command = ["get", "pods", "-n", self.namespace, "-l", f"app={self.deployment_name}", "-o", "json"]

        output = self.run_kubectl_command(command)
        if not output:
            return []

        try:
            pods_data = json.loads(output)
            pod_infos = []

            for pod in pods_data.get("items", []):
                pod_name = pod["metadata"]["name"]
                status = pod["status"]["phase"]
                node_name = pod["spec"].get("nodeName", "unknown")

                # Get zone information from node
                zone = self.get_node_zone(node_name)

                pod_infos.append(PodInfo(name=pod_name, node=node_name, zone=zone, status=status))

            return pod_infos

        except json.JSONDecodeError as e:
            print(f"Error parsing kubectl output: {e}")
            return []

    def get_node_zone(self, node_name: str) -> str:
        """Get the zone for a given node."""
        command = ["get", "node", node_name, "-o", "jsonpath={.metadata.labels.topology\\.kubernetes\\.io/zone}"]

        output = self.run_kubectl_command(command)
        return output.strip() if output else "unknown"

    def calculate_distribution_metrics(self, pods: list[PodInfo]) -> DistributionMetrics:
        """Calculate distribution metrics from pod information."""
        if not pods:
            return DistributionMetrics(0, 0, 0, {}, {}, 0.0, 0.0)

        # Count pods per node and zone
        pods_per_node = {}
        pods_per_zone = {}

        for pod in pods:
            pods_per_node[pod.node] = pods_per_node.get(pod.node, 0) + 1
            pods_per_zone[pod.zone] = pods_per_zone.get(pod.zone, 0) + 1

        total_pods = len(pods)
        nodes_used = len(pods_per_node)
        zones_used = len(pods_per_zone)

        # Calculate spread scores (lower is better, 0 = perfect spread)
        zone_spread_score = self._calculate_spread_score(list(pods_per_zone.values()))
        node_spread_score = self._calculate_spread_score(list(pods_per_node.values()))

        return DistributionMetrics(
            total_pods=total_pods,
            nodes_used=nodes_used,
            zones_used=zones_used,
            pods_per_node=pods_per_node,
            pods_per_zone=pods_per_zone,
            zone_spread_score=zone_spread_score,
            node_spread_score=node_spread_score,
        )

    def _calculate_spread_score(self, counts: list[int]) -> float:
        """Calculate spread score (0 = perfect, higher = worse)."""
        if not counts:
            return 0.0

        total = sum(counts)
        ideal_per_group = total / len(counts)
        variance = sum((count - ideal_per_group) ** 2 for count in counts) / len(counts)
        return variance**0.5  # RMS deviation

    def print_distribution_report(self, pods: list[PodInfo], metrics: DistributionMetrics):
        """Print a detailed distribution report."""
        print("=== ATP Router Pod Distribution Report ===")
        print(f"Total Pods: {metrics.total_pods}")
        print(f"Nodes Used: {metrics.nodes_used}")
        print(f"Zones Used: {metrics.zones_used}")
        print(f"Zone Spread Score: {metrics.zone_spread_score:.2f} (lower is better)")
        print(f"Node Spread Score: {metrics.node_spread_score:.2f} (lower is better)")
        print()

        print("Pods per Node:")
        for node, count in sorted(metrics.pods_per_node.items()):
            print(f"  {node}: {count} pods")
        print()

        print("Pods per Zone:")
        for zone, count in sorted(metrics.pods_per_zone.items()):
            print(f"  {zone}: {count} pods")
        print()

        print("Pod Details:")
        for pod in sorted(pods, key=lambda p: p.name):
            print(f"  {pod.name}: {pod.status} on {pod.node} ({pod.zone})")

    def test_distribution_constraints(self, metrics: DistributionMetrics) -> bool:
        """Test if distribution meets constraints."""
        print("=== Distribution Constraint Tests ===")

        # Test 1: Multiple zones used
        zones_ok = metrics.zones_used > 1
        print(f"✓ Multiple zones used: {'PASS' if zones_ok else 'FAIL'} ({metrics.zones_used} zones)")

        # Test 2: Multiple nodes used
        nodes_ok = metrics.nodes_used > 1
        print(f"✓ Multiple nodes used: {'PASS' if nodes_ok else 'FAIL'} ({metrics.nodes_used} nodes)")

        # Test 3: Reasonable spread (score < 2.0 is good)
        spread_ok = metrics.zone_spread_score < 2.0 and metrics.node_spread_score < 2.0
        print(
            f"✓ Reasonable spread: {'PASS' if spread_ok else 'FAIL'} "
            f"(zone: {metrics.zone_spread_score:.2f}, node: {metrics.node_spread_score:.2f})"
        )

        # Test 4: No single point of failure
        max_per_zone = max(metrics.pods_per_zone.values()) if metrics.pods_per_zone else 0
        max_per_node = max(metrics.pods_per_node.values()) if metrics.pods_per_node else 0
        zone_balance_ok = max_per_zone <= metrics.total_pods - 1  # At least 2 pods not in same zone
        node_balance_ok = max_per_node <= metrics.total_pods - 1  # At least 2 pods not on same node

        print(f"✓ Zone balance: {'PASS' if zone_balance_ok else 'FAIL'} (max {max_per_zone} per zone)")
        print(f"✓ Node balance: {'PASS' if node_balance_ok else 'FAIL'} (max {max_per_node} per node)")

        overall_pass = zones_ok and nodes_ok and spread_ok and zone_balance_ok and node_balance_ok
        print(f"\nOverall: {'PASS' if overall_pass else 'FAIL'}")

        return overall_pass


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test ATP Router pod distribution")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--deployment", default="atp-router", help="Deployment name")
    parser.add_argument("--test-only", action="store_true", help="Only run tests, don't print full report")

    args = parser.parse_args()

    tester = PodDistributionTester(args.namespace, args.deployment)

    # Get pod distribution
    pods = tester.get_pod_distribution()

    if not pods:
        print("No pods found. Make sure the deployment is running.")
        sys.exit(1)

    metrics = tester.calculate_distribution_metrics(pods)

    if not args.test_only:
        tester.print_distribution_report(pods, metrics)
        print()

    # Run constraint tests
    success = tester.test_distribution_constraints(metrics)

    # Output metrics for monitoring
    print("\n=== Metrics for Monitoring ===")
    print(f"atp_pods_total {metrics.total_pods}")
    print(f"atp_nodes_used {metrics.nodes_used}")
    print(f"atp_zones_used {metrics.zones_used}")
    print(f"atp_zone_spread_score {metrics.zone_spread_score}")
    print(f"atp_node_spread_score {metrics.node_spread_score}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
