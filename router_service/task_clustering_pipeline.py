"""GAP-342: Task clustering pipeline with TF-IDF + embedding features and incremental clustering.

Implements feature extraction using TF-IDF combined with embeddings, and incremental
AgglomerativeClustering for stable task clustering. Provides metrics for cluster tracking
and churn rate analysis.
"""

import hashlib
import time
from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

from metrics.registry import REGISTRY

from .embedding_cluster_classifier import EmbeddingService, MockEmbeddingService


class TaskClusteringPipeline:
    """Incremental task clustering pipeline with TF-IDF + embedding features."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        n_clusters: int = 10,
        tfidf_max_features: int = 1000,
        random_state: int = 42,
    ):
        self.embedding_service = embedding_service or MockEmbeddingService()
        self.n_clusters = n_clusters
        self.tfidf_max_features = tfidf_max_features
        self.random_state = random_state

        # Feature extraction components
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=tfidf_max_features, stop_words="english", ngram_range=(1, 2)
        )
        self.scaler = StandardScaler()

        # Clustering components
        self.clusterer: AgglomerativeClustering | None = None
        self.is_trained = False

        # Training data storage
        self.training_prompts: list[str] = []
        self.training_features: np.ndarray | None = None
        self.cluster_labels: np.ndarray | None = None
        self.cluster_centers: np.ndarray | None = None

        # Cluster tracking for churn analysis
        self.previous_cluster_assignments: dict[str, int] = {}
        self.cluster_sizes: dict[int, int] = defaultdict(int)
        self.last_update_time = time.time()

        # Metrics
        self._task_clusters_active = REGISTRY.gauge("atp_task_clusters_active")
        self._cluster_churn_rate = REGISTRY.gauge("atp_cluster_churn_rate")
        self._clustering_requests_total = REGISTRY.counter("atp_clustering_requests_total")
        self._cluster_assignments_total = REGISTRY.counter("atp_cluster_assignments_total")

    def _extract_features(self, prompts: list[str], fit: bool = True) -> np.ndarray:
        """Extract combined TF-IDF + embedding features."""
        if not prompts:
            return np.array([])

        # Get TF-IDF features
        if fit:
            tfidf_features = self.tfidf_vectorizer.fit_transform(prompts).toarray()
        else:
            tfidf_features = self.tfidf_vectorizer.transform(prompts).toarray()

        # Get embedding features
        embeddings = self.embedding_service.embed_batch(prompts)
        embedding_features = np.array(embeddings)

        # Combine features
        combined_features = np.concatenate([tfidf_features, embedding_features], axis=1)

        # Scale features
        if fit:
            scaled_features = self.scaler.fit_transform(combined_features)
        else:
            scaled_features = self.scaler.transform(combined_features)

        return scaled_features

    def _update_cluster_tracking(self, prompt_hashes: list[str], new_labels: np.ndarray) -> None:
        """Update cluster tracking for churn analysis."""
        current_assignments = dict(zip(prompt_hashes, new_labels, strict=False))

        # Calculate churn
        total_changes = 0
        total_samples = len(current_assignments)

        for prompt_hash, new_cluster in current_assignments.items():
            old_cluster = self.previous_cluster_assignments.get(prompt_hash)
            if old_cluster is not None and old_cluster != new_cluster:
                total_changes += 1

        # Update metrics
        if total_samples > 0:
            churn_rate = total_changes / total_samples
            self._cluster_churn_rate.set(churn_rate)

        # Update cluster sizes
        self.cluster_sizes.clear()
        for cluster_id in new_labels:
            self.cluster_sizes[cluster_id] += 1

        # Update active clusters metric
        active_clusters = len(self.cluster_sizes)
        self._task_clusters_active.set(active_clusters)

        # Store current assignments for next comparison
        self.previous_cluster_assignments = current_assignments.copy()

    def train_clusters(self, training_prompts: list[str]) -> None:
        """Train clustering model on training data."""
        if not training_prompts:
            return

        self._clustering_requests_total.inc()

        try:
            # Store training prompts
            self.training_prompts = training_prompts.copy()

            # Extract features
            features = self._extract_features(training_prompts, fit=True)
            self.training_features = features

            # Perform clustering
            self.clusterer = AgglomerativeClustering(n_clusters=min(self.n_clusters, len(features)), linkage="ward")

            labels = self.clusterer.fit_predict(features)
            self.cluster_labels = labels
            self.is_trained = True

            # Calculate cluster centers (centroids)
            unique_labels = np.unique(labels)
            centers = []
            for label in unique_labels:
                mask = labels == label
                center = features[mask].mean(axis=0)
                centers.append(center)
            self.cluster_centers = np.array(centers)

            # Update cluster tracking
            prompt_hashes = [self._hash_prompt(p) for p in training_prompts]
            self._update_cluster_tracking(prompt_hashes, labels)

        except Exception as e:
            print(f"Task clustering training failed: {e}")
            self.is_trained = False

    def classify_task(self, prompt: str) -> str | None:
        """Classify task using trained clustering model."""
        if not self.is_trained or self.cluster_centers is None:
            return None

        self._cluster_assignments_total.inc()

        try:
            # Extract features for the prompt
            features = self._extract_features([prompt], fit=False)

            # Find nearest cluster center
            similarities = cosine_similarity(features, self.cluster_centers)
            cluster_id = np.argmax(similarities[0])

            return f"task_cluster_{cluster_id}"

        except Exception as e:
            print(f"Task clustering classification failed: {e}")
            return None

    def incremental_update(self, new_prompts: list[str]) -> None:
        """Incrementally update clustering with new data."""
        if not self.is_trained:
            # If not trained, do full training
            self.train_clusters(new_prompts)
            return

        # Combine existing and new data
        all_prompts = self.training_prompts + new_prompts

        # Retrain on combined dataset
        self.train_clusters(all_prompts)

    def _hash_prompt(self, prompt: str) -> str:
        """Generate hash for prompt tracking."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    def get_cluster_stats(self) -> dict[str, Any]:
        """Get clustering statistics."""
        return {
            "is_trained": self.is_trained,
            "n_clusters": self.n_clusters,
            "training_samples": len(self.training_prompts),
            "cluster_sizes": dict(self.cluster_sizes),
            "active_clusters": len(self.cluster_sizes),
            "last_update_time": self.last_update_time,
            "feature_dimensions": self.training_features.shape[1] if self.training_features is not None else 0,
        }

    def get_cluster_distribution(self) -> dict[str, int]:
        """Get distribution of samples across clusters."""
        return dict(self.cluster_sizes)


# Global instance for GAP-342
TASK_CLUSTERING_PIPELINE = TaskClusteringPipeline()
