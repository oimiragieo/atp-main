"""Tests for cluster coverage tracking."""

from unittest.mock import patch

import pytest

from router_service.cluster_coverage import ClusterCoverageTracker, tracker


class TestClusterCoverageTracker:
    """Test cluster coverage tracking functionality."""

    def test_initial_state(self):
        """Test initial state of coverage tracker."""
        tracker = ClusterCoverageTracker()
        assert tracker.known_clusters == set()
        assert tracker.covered_clusters == set()
        assert tracker.coverage_percentage == 0.0

    def test_update_coverage_new_cluster(self):
        """Test updating coverage with a new cluster."""
        tracker = ClusterCoverageTracker()
        tracker.record_cluster_usage("code")

        assert "code" in tracker.known_clusters
        assert tracker.coverage_percentage == 0.0  # No coverage recorded yet

    def test_update_coverage_existing_cluster(self):
        """Test updating coverage with existing cluster doesn't change known set."""
        tracker = ClusterCoverageTracker()
        tracker.record_cluster_usage("code")
        tracker.record_cluster_usage("code")  # Second call

        assert tracker.known_clusters == {"code"}
        assert tracker.coverage_percentage == 0.0

    def test_multiple_clusters(self):
        """Test coverage with multiple clusters."""
        tracker = ClusterCoverageTracker()

        # Add first cluster
        tracker.record_cluster_usage("code")
        assert tracker.coverage_percentage == 0.0

        # Add second cluster
        tracker.record_cluster_usage("summarize")
        assert tracker.known_clusters == {"code", "summarize"}
        assert tracker.coverage_percentage == 0.0

    def test_partial_coverage(self):
        """Test partial coverage calculation."""
        tracker = ClusterCoverageTracker()

        # Manually set known clusters (simulating discovery)
        tracker.known_clusters = {"code", "summarize", "extract"}

        # Cover only some
        tracker.record_cluster_coverage("code")
        tracker.record_cluster_coverage("summarize")

        assert tracker.covered_clusters == {"code", "summarize"}
        assert tracker.coverage_percentage == pytest.approx(66.67, abs=0.01)  # 2/3

    def test_metrics_update(self):
        """Test that metrics are updated when coverage changes."""
        with patch("router_service.cluster_coverage.REGISTRY") as mock_registry:
            mock_gauge = mock_registry.gauge.return_value
            tracker = ClusterCoverageTracker()
            initial_calls = len(mock_gauge.set.call_args_list)
            tracker.record_cluster_coverage("code")
            # Verify that set was called again (should be called with 100.0)
            assert len(mock_gauge.set.call_args_list) > initial_calls

    def test_zero_division_handling(self):
        """Test coverage percentage when no clusters are known."""
        tracker = ClusterCoverageTracker()
        # Should not crash, return 0.0
        assert tracker.coverage_percentage == 0.0


class TestGlobalTracker:
    """Test the global tracker instance."""

    def test_global_tracker_is_instance(self):
        """Test that the global tracker is properly instantiated."""
        assert isinstance(tracker, ClusterCoverageTracker)

    def test_global_tracker_functionality(self):
        """Test that the global tracker works as expected."""
        # Reset the global tracker
        tracker.known_clusters.clear()
        tracker.covered_clusters.clear()

        tracker.record_cluster_usage("test_cluster")
        assert "test_cluster" in tracker.known_clusters
        assert tracker.coverage_percentage == 0.0
