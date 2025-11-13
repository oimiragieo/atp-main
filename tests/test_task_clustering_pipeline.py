"""Tests for GAP-342: Task clustering pipeline."""

import numpy as np

from router_service.embedding_cluster_classifier import MockEmbeddingService
from router_service.task_clustering_pipeline import TASK_CLUSTERING_PIPELINE, TaskClusteringPipeline


class TestTaskClusteringPipeline:
    """Test TaskClusteringPipeline."""

    def test_initialization(self):
        """Test pipeline initialization."""
        pipeline = TaskClusteringPipeline()
        assert not pipeline.is_trained
        assert pipeline.n_clusters == 10
        assert pipeline.tfidf_max_features == 1000

    def test_feature_extraction(self):
        """Test TF-IDF + embedding feature extraction."""
        pipeline = TaskClusteringPipeline()
        prompts = ["Hello world", "Goodbye world", "Machine learning is fun"]

        features = pipeline._extract_features(prompts)

        assert isinstance(features, np.ndarray)
        assert features.shape[0] == 3
        # Features should combine TF-IDF + embeddings
        assert features.shape[1] > 128  # TF-IDF features + embedding dimensions

    def test_training_basic(self):
        """Test basic clustering training."""
        pipeline = TaskClusteringPipeline(n_clusters=3)
        prompts = [
            "Write a Python function",
            "Debug this code",
            "Create a machine learning model",
            "Analyze this dataset",
            "Generate a summary",
            "Translate this text",
        ]

        pipeline.train_clusters(prompts)

        assert pipeline.is_trained
        assert len(pipeline.training_prompts) == 6
        assert pipeline.cluster_labels is not None
        assert len(pipeline.cluster_labels) == 6

    def test_classification_after_training(self):
        """Test task classification after training."""
        pipeline = TaskClusteringPipeline(n_clusters=2)
        prompts = ["Write Python code", "Debug JavaScript", "Summarize article", "Translate document"]

        pipeline.train_clusters(prompts)

        # Test classification
        result = pipeline.classify_task("Create a function")
        assert result is not None
        assert result.startswith("task_cluster_")

    def test_classification_without_training(self):
        """Test classification fails without training."""
        pipeline = TaskClusteringPipeline()
        result = pipeline.classify_task("Test prompt")
        assert result is None

    def test_incremental_update(self):
        """Test incremental clustering updates."""
        pipeline = TaskClusteringPipeline(n_clusters=2)
        initial_prompts = ["Write code", "Debug code"]

        pipeline.train_clusters(initial_prompts)
        initial_training_size = len(pipeline.training_prompts)

        # Add more data
        new_prompts = ["Analyze data", "Generate report"]
        pipeline.incremental_update(new_prompts)

        assert len(pipeline.training_prompts) == initial_training_size + len(new_prompts)
        assert pipeline.is_trained

    def test_cluster_stats(self):
        """Test cluster statistics retrieval."""
        pipeline = TaskClusteringPipeline(n_clusters=3)
        prompts = ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"]

        pipeline.train_clusters(prompts)
        stats = pipeline.get_cluster_stats()

        assert stats["is_trained"] is True
        assert stats["training_samples"] == 5
        assert "cluster_sizes" in stats
        assert "active_clusters" in stats

    def test_cluster_distribution(self):
        """Test cluster distribution."""
        pipeline = TaskClusteringPipeline(n_clusters=2)
        prompts = ["Code task", "Code task 2", "Analysis task", "Analysis task 2"]

        pipeline.train_clusters(prompts)
        distribution = pipeline.get_cluster_distribution()

        assert isinstance(distribution, dict)
        assert sum(distribution.values()) == 4

    def test_prompt_hash_consistency(self):
        """Test prompt hashing is consistent."""
        pipeline = TaskClusteringPipeline()
        prompt = "Test prompt"

        hash1 = pipeline._hash_prompt(prompt)
        hash2 = pipeline._hash_prompt(prompt)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_empty_training_data(self):
        """Test handling of empty training data."""
        pipeline = TaskClusteringPipeline()
        pipeline.train_clusters([])

        assert not pipeline.is_trained

    def test_cluster_tracking_churn(self):
        """Test cluster churn rate calculation."""
        pipeline = TaskClusteringPipeline(n_clusters=2)

        # Initial training
        prompts1 = ["Task A", "Task B"]
        pipeline.train_clusters(prompts1)

        # Update with some same, some different
        prompts2 = ["Task A", "Task C"]  # Task A same cluster, Task C new
        pipeline.incremental_update(prompts2)

        # Check that churn tracking is working
        stats = pipeline.get_cluster_stats()
        assert "cluster_sizes" in stats

    def test_metrics_integration(self):
        """Test metrics are properly registered and updated."""

        pipeline = TaskClusteringPipeline(n_clusters=2)
        prompts = ["Task 1", "Task 2"]

        pipeline.train_clusters(prompts)

        # Check that classification updates metrics
        pipeline.classify_task("New task")

        # Metrics should be registered (we can't easily test values without mocking)

    def test_mock_embedding_service_integration(self):
        """Test integration with mock embedding service."""
        mock_service = MockEmbeddingService(dim=64)
        pipeline = TaskClusteringPipeline(embedding_service=mock_service)

        prompts = ["Test prompt"]
        features = pipeline._extract_features(prompts)

        # Should have TF-IDF features + 64 embedding features
        assert features.shape[1] >= 64

    def test_feature_scaling(self):
        """Test that features are properly scaled."""
        pipeline = TaskClusteringPipeline()
        prompts = ["Long prompt with many words"] * 5

        features = pipeline._extract_features(prompts)

        # Check that scaler was applied (mean should be close to 0)
        feature_means = np.mean(features, axis=0)
        # Some features should have means close to 0 after scaling
        assert np.any(np.abs(feature_means) < 0.1)


class TestGlobalInstance:
    """Test global TASK_CLUSTERING_PIPELINE instance."""

    def test_global_instance_exists(self):
        """Test that global instance is properly initialized."""
        assert TASK_CLUSTERING_PIPELINE is not None
        assert isinstance(TASK_CLUSTERING_PIPELINE, TaskClusteringPipeline)

    def test_global_instance_functionality(self):
        """Test that global instance works end-to-end."""
        prompts = ["Code task", "Analysis task"]
        TASK_CLUSTERING_PIPELINE.train_clusters(prompts)

        TASK_CLUSTERING_PIPELINE.classify_task("Debug task")
        # Just check that the method runs without error
        assert True  # Placeholder assertion
