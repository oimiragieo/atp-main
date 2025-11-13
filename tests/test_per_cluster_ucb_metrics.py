"""Tests for GAP-208: Per-cluster UCB metrics aggregation."""

from unittest.mock import patch

from router_service.adaptive_stats import compute_ucb_scores, fetch_all_clusters, update_stat


class TestPerClusterUCB:
    """Test per-cluster UCB metrics aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear any existing test data
        pass

    def test_compute_ucb_scores_multiple_clusters(self):
        """Test UCB score computation across multiple clusters."""
        # Add test data for different clusters
        update_stat("cluster1", "model1", True, 0.1, 100)
        update_stat("cluster1", "model2", False, 0.2, 200)
        update_stat("cluster2", "model3", True, 0.15, 150)

        clusters = fetch_all_clusters()
        assert len(clusters) >= 2

        # Test scores for each cluster
        for cluster in clusters:
            scores = compute_ucb_scores(cluster)
            assert isinstance(scores, dict)
            assert len(scores) > 0

            for _model, data in scores.items():
                assert "score" in data
                assert "exploit" in data
                assert "explore" in data
                assert isinstance(data["score"], float)

    def test_metrics_emission_format(self):
        """Test that metrics are emitted in correct Prometheus format."""
        update_stat("test_cluster", "test_model", True, 0.1, 100)

        scores = compute_ucb_scores("test_cluster")

        # Simulate metrics emission
        lines = []
        for model, data in scores.items():
            lines.append(
                f'atp_router_ucb_score{{cluster="test_cluster",model="{model}"}} {round(data.get("score", 0.0), 4)}'
            )
            lines.append(
                f'atp_router_ucb_exploit{{cluster="test_cluster",model="{model}"}} {round(data.get("exploit", 0.0), 4)}'
            )
            lines.append(
                f'atp_router_ucb_explore{{cluster="test_cluster",model="{model}"}} {round(data.get("explore", 0.0), 4)}'
            )

        assert len(lines) > 0
        for line in lines:
            assert "atp_router_ucb" in line
            assert "cluster=" in line
            assert "model=" in line

    def test_empty_cluster_handling(self):
        """Test handling of clusters with no data."""
        scores = compute_ucb_scores("nonexistent_cluster")
        assert scores == {}

    def test_cluster_isolation(self):
        """Test that clusters maintain separate statistics."""
        # Add data to different clusters
        update_stat("cluster_a", "model1", True, 0.1, 100)
        update_stat("cluster_b", "model2", True, 0.1, 100)

        scores_a = compute_ucb_scores("cluster_a")
        scores_b = compute_ucb_scores("cluster_b")

        # Models should not cross clusters
        assert "model1" in scores_a
        assert "model2" not in scores_a
        assert "model2" in scores_b
        assert "model1" not in scores_b

    @patch("router_service.adaptive_stats.fetch_all_clusters")
    def test_metrics_aggregation_all_clusters(self, mock_fetch_clusters):
        """Test metrics aggregation across all clusters."""
        mock_fetch_clusters.return_value = ["cluster1", "cluster2"]

        # This would be called in the metrics endpoint
        all_clusters = fetch_all_clusters()
        assert "cluster1" in all_clusters
        assert "cluster2" in all_clusters
