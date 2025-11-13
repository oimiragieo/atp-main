"""GAP-200: Cluster coverage metric computation."""

from metrics.registry import REGISTRY


class ClusterCoverageTracker:
    """Tracks cluster coverage metrics for SLM specialists."""

    def __init__(self) -> None:
        # Initialize metrics for GAP-200
        self._cluster_coverage_pct = REGISTRY.gauge("cluster_coverage_pct")

        # Track known clusters and covered clusters
        self.known_clusters: set[str] = set()
        self.covered_clusters: set[str] = set()

    def record_cluster_usage(self, cluster_id: str) -> None:
        """Record that a cluster has been used/observed."""
        if cluster_id:
            self.known_clusters.add(cluster_id)
            self._update_coverage()

    def record_cluster_coverage(self, cluster_id: str) -> None:
        """Record that a cluster has an SLM specialist assigned."""
        if cluster_id:
            self.covered_clusters.add(cluster_id)
            self._update_coverage()

    def remove_cluster_coverage(self, cluster_id: str) -> None:
        """Remove coverage for a cluster (e.g., when specialist is deprecated)."""
        if cluster_id:
            self.covered_clusters.discard(cluster_id)
            self._update_coverage()

    def _update_coverage(self) -> None:
        """Update the coverage percentage metric."""
        if not self.known_clusters:
            self._cluster_coverage_pct.set(0.0)
            return

        coverage_pct = (len(self.covered_clusters) / len(self.known_clusters)) * 100.0
        self._cluster_coverage_pct.set(coverage_pct)

    def get_coverage_stats(self) -> dict[str, float]:
        """Get current coverage statistics."""
        total_clusters = len(self.known_clusters)
        covered_clusters = len(self.covered_clusters)
        coverage_pct = (covered_clusters / total_clusters * 100.0) if total_clusters > 0 else 0.0

        return {
            "total_clusters": total_clusters,
            "covered_clusters": covered_clusters,
            "coverage_percentage": coverage_pct,
        }

    @property
    def coverage_percentage(self) -> float:
        """Get current coverage percentage."""
        return self.get_coverage_stats()["coverage_percentage"]

    def reset(self) -> None:
        """Reset all tracking data (for testing)."""
        self.known_clusters.clear()
        self.covered_clusters.clear()
        self._update_coverage()


# Global instance for the application
tracker = ClusterCoverageTracker()
