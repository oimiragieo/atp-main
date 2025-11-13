"""Tests for task classification with cluster coverage integration."""

from unittest.mock import patch

from router_service.task_classify import classify


class TestTaskClassifyWithCoverage:
    """Test task classification with coverage tracking."""

    def setup_method(self):
        """Reset tracker before each test."""
        from router_service.cluster_coverage import tracker

        tracker.known_clusters.clear()
        tracker.covered_clusters.clear()

    def test_classify_code_cluster(self):
        """Test classification of code-related prompts."""
        result = classify("def hello(): print('world')")
        assert result == "code"

        # Check coverage was updated
        from router_service.cluster_coverage import tracker

        assert "code" in tracker.known_clusters
        assert "code" not in tracker.covered_clusters  # Usage doesn't imply coverage

    def test_classify_summarize_cluster(self):
        """Test classification of summarization prompts."""
        result = classify("Please summarize this document")
        assert result == "summarize"

        from router_service.cluster_coverage import tracker

        assert "summarize" in tracker.known_clusters

    def test_classify_json_struct(self):
        """Test classification of JSON structure prompts."""
        result = classify('Create a JSON with {name: "value"}')
        assert result == "json_struct"

        from router_service.cluster_coverage import tracker

        assert "json_struct" in tracker.known_clusters

    def test_classify_bucket_fallback(self):
        """Test hashed bucket fallback with coverage tracking."""
        with patch.dict("os.environ", {"CLUSTER_HASH_BUCKETS": "3"}):
            result = classify("some unknown prompt")
            assert result.startswith("bucket_")
            assert result in ["bucket_0", "bucket_1", "bucket_2"]

            from router_service.cluster_coverage import tracker

            assert result in tracker.known_clusters

    def test_classify_no_match(self):
        """Test classification with no matches."""
        result = classify("random text with no keywords")
        assert result is None

        # Coverage should not be updated for None
        from router_service.cluster_coverage import tracker

        assert len(tracker.known_clusters) == 0

    def test_multiple_classifications(self):
        """Test multiple classifications update coverage correctly."""
        from router_service.cluster_coverage import tracker

        classify("def function(): pass")  # code
        classify("summarize this")  # summarize
        classify("def another(): pass")  # code again

        assert tracker.known_clusters == {"code", "summarize"}
        assert tracker.covered_clusters == set()  # Only usage tracked, not coverage
        assert tracker.coverage_percentage == 0.0  # Only usage tracked, no actual coverage

    def test_metrics_integration(self):
        """Test that metrics are updated during classification."""
        from router_service.cluster_coverage import tracker

        initial_known = tracker.known_clusters.copy()
        classify("def test(): pass")
        assert len(tracker.known_clusters) > len(initial_known)
