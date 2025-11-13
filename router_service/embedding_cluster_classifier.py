"""GAP-206: Embedding-based cluster classification.

Provides embedding service abstraction and k-means clustering for task classification.
Fallback to heuristic classification when embedding service is unavailable.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)


class EmbeddingService(ABC):
    """Abstract base class for embedding services."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass


class MockEmbeddingService(EmbeddingService):
    """Mock embedding service using hash-based features."""

    def __init__(self, dim: int = 128):
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        """Generate mock embedding using hash of text."""
        # Use hash of text to create deterministic but varied embeddings
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()

        # Extend hash to desired dimension
        embedding = []
        for i in range(self.dim):
            # Use hash bytes cyclically
            byte_val = hash_bytes[i % len(hash_bytes)]
            # Normalize to [-1, 1] range
            val = (byte_val / 255.0) * 2 - 1
            embedding.append(val)

        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed_text(text) for text in texts]


class EmbeddingClusterClassifier:
    """Embedding-based cluster classifier with k-means and ANN fallback."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        n_clusters: int = 10,
        random_state: int = 42,
        fallback_classifier: callable | None = None,
    ):
        self.embedding_service = embedding_service or MockEmbeddingService()
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.fallback_classifier = fallback_classifier

        # Initialize metrics for GAP-206
        self._cluster_reassignments_total = REGISTRY.counter("atp_cluster_reassignments_total")
        self._embedding_requests_total = REGISTRY.counter("atp_embedding_requests_total")
        self._cluster_assignments_total = REGISTRY.counter("atp_cluster_assignments_total")

        # Clustering state
        self.kmeans: KMeans | None = None
        self.cluster_centers: np.ndarray | None = None
        self.is_trained = False

        # Training data
        self.training_embeddings: list[list[float]] = []
        self.training_labels: list[str] = []

    def classify_task(self, prompt: str) -> str | None:
        """Classify task using embedding-based clustering with fallback."""
        self._embedding_requests_total.inc()

        try:
            # Generate embedding
            embedding = self.embedding_service.embed_text(prompt)
            self._cluster_assignments_total.inc()

            # Use k-means if trained, otherwise fallback
            if self.is_trained and self.kmeans is not None:
                cluster_id = self._predict_cluster(embedding)
                return f"embedding_cluster_{cluster_id}"
            else:
                # Fallback to provided classifier or heuristic
                if self.fallback_classifier:
                    return self.fallback_classifier(prompt)
                else:
                    return None

        except Exception as e:
            # Log error and use fallback
            logger.error(f"Embedding classification failed: {e}")
            if self.fallback_classifier:
                return self.fallback_classifier(prompt)
            return None

    def train_clusters(self, training_prompts: list[str], training_labels: list[str] | None = None) -> None:
        """Train k-means clustering on training data."""
        if not training_prompts:
            return

        try:
            # Generate embeddings for training data
            embeddings = self.embedding_service.embed_batch(training_prompts)

            # Fit k-means
            self.kmeans = KMeans(
                n_clusters=min(self.n_clusters, len(embeddings)), random_state=self.random_state, n_init=10
            )

            x = np.array(embeddings)
            cluster_labels = self.kmeans.fit_predict(x)

            # Store cluster centers for ANN-like prediction
            self.cluster_centers = self.kmeans.cluster_centers_
            self.is_trained = True

            # Store training data for reference
            self.training_embeddings = embeddings
            self.training_labels = training_labels or [f"cluster_{i}" for i in cluster_labels]

        except Exception as e:
            logger.error(f"Cluster training failed: {e}")
            self.is_trained = False

    def _predict_cluster(self, embedding: list[float]) -> int:
        """Predict cluster for embedding using ANN-like nearest neighbor."""
        if not self.is_trained or self.cluster_centers is None:
            return 0

        # Find nearest cluster center
        embedding_array = np.array(embedding).reshape(1, -1)
        similarities = cosine_similarity(embedding_array, self.cluster_centers)
        cluster_id = np.argmax(similarities[0])

        return int(cluster_id)

    def reassign_clusters(self, new_n_clusters: int) -> None:
        """Reassign clusters with new number of clusters."""
        if not self.is_trained or not self.training_embeddings:
            return

        old_n_clusters = self.n_clusters
        self.n_clusters = new_n_clusters
        self._cluster_reassignments_total.inc()

        # Retrain with new cluster count
        self.train_clusters(
            training_prompts=[""] * len(self.training_embeddings),  # Dummy prompts
            training_labels=self.training_labels,
        )

        logger.info(f"Reassigned clusters from {old_n_clusters} to {new_n_clusters}")

    def get_cluster_stats(self) -> dict[str, Any]:
        """Get clustering statistics."""
        return {
            "is_trained": self.is_trained,
            "n_clusters": self.n_clusters,
            "training_samples": len(self.training_embeddings),
            "cluster_centers_shape": self.cluster_centers.shape if self.cluster_centers is not None else None,
        }


# Global instance for GAP-206
EMBEDDING_CLUSTER_CLASSIFIER = EmbeddingClusterClassifier()
