"""Tests for GAP-206: Embedding-based cluster classification."""

from unittest.mock import Mock

from router_service.embedding_cluster_classifier import (
    EMBEDDING_CLUSTER_CLASSIFIER,
    EmbeddingClusterClassifier,
    EmbeddingService,
    MockEmbeddingService,
)


class TestMockEmbeddingService:
    """Test MockEmbeddingService."""

    def test_embed_text_basic(self):
        """Test basic text embedding."""
        service = MockEmbeddingService(dim=64)
        embedding = service.embed_text("test text")

        assert isinstance(embedding, list)
        assert len(embedding) == 64
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_text_different_inputs(self):
        """Test that different inputs produce different embeddings."""
        service = MockEmbeddingService(dim=32)
        emb1 = service.embed_text("hello world")
        emb2 = service.embed_text("goodbye world")

        # Mock embeddings might be similar, just check they're not identical
        assert len(emb1) == len(emb2) == 32
        # At least some values should be different
        assert emb1 != emb2 or any(a != b for a, b in zip(emb1, emb2))

    def test_embed_batch(self):
        """Test batch embedding."""
        service = MockEmbeddingService(dim=16)
        texts = ["text 1", "text 2", "text 3"]
        embeddings = service.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(emb) == 16 for emb in embeddings)


class TestEmbeddingClusterClassifier:
    """Test EmbeddingClusterClassifier."""

    def setup_method(self):
        """Set up test fixtures."""
        self.classifier = EmbeddingClusterClassifier(n_clusters=3)
        # Mock the metrics to avoid registry issues in tests
        self.classifier._cluster_reassignments_total = Mock()
        self.classifier._embedding_requests_total = Mock()
        self.classifier._cluster_assignments_total = Mock()

    def test_initialization(self):
        """Test classifier initialization."""
        assert not self.classifier.is_trained
        assert self.classifier.kmeans is None
        assert self.classifier.n_clusters == 3

    def test_classify_task_untrained_fallback(self):
        """Test classification falls back to provided classifier when untrained."""

        def mock_fallback(prompt):
            return "test_cluster"

        self.classifier.fallback_classifier = mock_fallback

        result = self.classifier.classify_task("test prompt")

        assert result == "test_cluster"

    def test_train_clusters_basic(self):
        """Test basic cluster training."""
        training_prompts = ["prompt 1", "prompt 2", "prompt 3", "prompt 4", "prompt 5"]

        self.classifier.train_clusters(training_prompts)

        assert self.classifier.is_trained
        assert self.classifier.kmeans is not None
        assert len(self.classifier.training_embeddings) == 5

    def test_classify_task_trained(self):
        """Test classification when trained."""
        training_prompts = ["code prompt", "summary prompt", "extract prompt"]
        self.classifier.train_clusters(training_prompts)

        result = self.classifier.classify_task("new prompt")

        assert result is not None
        assert result.startswith("embedding_cluster_")

    def test_predict_cluster(self):
        """Test cluster prediction."""
        training_prompts = ["prompt 1", "prompt 2", "prompt 3"]
        self.classifier.train_clusters(training_prompts)

        # Use embedding with same dimension as training data (128)
        embedding = [0.1] * 128  # Mock embedding with correct dimension
        cluster_id = self.classifier._predict_cluster(embedding)

        assert isinstance(cluster_id, int)
        assert 0 <= cluster_id < self.classifier.n_clusters

    def test_reassign_clusters(self):
        """Test cluster reassignment."""
        training_prompts = ["prompt 1", "prompt 2", "prompt 3", "prompt 4", "prompt 5"]
        self.classifier.train_clusters(training_prompts)

        _original_clusters = self.classifier.n_clusters
        self.classifier.reassign_clusters(5)

        assert self.classifier.n_clusters == 5
        assert self.classifier._cluster_reassignments_total.inc.called

    def test_get_cluster_stats(self):
        """Test cluster statistics retrieval."""
        stats = self.classifier.get_cluster_stats()

        assert "is_trained" in stats
        assert "n_clusters" in stats
        assert "training_samples" in stats
        assert stats["n_clusters"] == 3

    def test_embedding_service_failure_fallback(self):
        """Test fallback when embedding service fails."""
        # Create classifier with failing embedding service
        failing_service = Mock(spec=EmbeddingService)
        failing_service.embed_text.side_effect = Exception("Service unavailable")

        def mock_fallback(prompt):
            return "fallback_cluster"

        classifier = EmbeddingClusterClassifier(embedding_service=failing_service, fallback_classifier=mock_fallback)
        classifier._embedding_requests_total = Mock()

        result = classifier.classify_task("test prompt")

        assert result == "fallback_cluster"

    def test_metrics_incremented(self):
        """Test that metrics are properly incremented."""
        training_prompts = ["prompt 1", "prompt 2"]
        self.classifier.train_clusters(training_prompts)

        self.classifier.classify_task("test prompt")

        self.classifier._embedding_requests_total.inc.assert_called_once()
        self.classifier._cluster_assignments_total.inc.assert_called_once()


class TestIntegration:
    """Integration tests for embedding cluster classification."""

    def test_global_instance_exists(self):
        """Test that global instance exists."""
        assert EMBEDDING_CLUSTER_CLASSIFIER is not None
        assert isinstance(EMBEDDING_CLUSTER_CLASSIFIER, EmbeddingClusterClassifier)

    def test_cluster_stability(self):
        """Test cluster assignment stability."""
        classifier = EmbeddingClusterClassifier(n_clusters=3, random_state=42)

        # Train with same data multiple times
        training_prompts = ["consistent prompt 1", "consistent prompt 2", "consistent prompt 3"]

        classifier.train_clusters(training_prompts)
        result1 = classifier.classify_task("test prompt")

        # Reset and retrain
        classifier.is_trained = False
        classifier.train_clusters(training_prompts)
        result2 = classifier.classify_task("test prompt")

        # Results should be stable with same random state
        assert result1 == result2

    def test_empty_training_data(self):
        """Test handling of empty training data."""
        classifier = EmbeddingClusterClassifier()

        classifier.train_clusters([])

        assert not classifier.is_trained
        assert classifier.kmeans is None
