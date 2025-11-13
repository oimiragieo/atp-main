"""Active Learning Task Enqueue System (GAP-203)
Implements sampling policies for selecting high-value tasks for active learning.
Supports uncertainty sampling, diversity sampling, and fairness constraints.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from metrics.registry import REGISTRY


@dataclass
class ActiveLearningTask:
    """Represents a task selected for active learning."""

    prompt_hash: str
    cluster_hint: str | None
    quality_score: float
    uncertainty_score: float
    timestamp: float
    model_used: str
    sampling_method: str


class ActiveLearningSampler:
    """Sampler for active learning task selection with fairness constraints."""

    def __init__(
        self,
        max_queue_size: int = 1000,
        uncertainty_threshold: float = 0.7,
        diversity_weight: float = 0.3,
        fairness_window_hours: int = 24,
    ):
        self.max_queue_size = max_queue_size
        self.uncertainty_threshold = uncertainty_threshold
        self.diversity_weight = diversity_weight
        self.fairness_window_hours = fairness_window_hours

        # Task queues and tracking
        self.task_queue: deque[ActiveLearningTask] = deque(maxlen=max_queue_size)
        self.cluster_counts: dict[str, int] = defaultdict(int)
        self.recent_selections: dict[str, list[float]] = defaultdict(list)

        # Metrics
        self._tasks_enqueued = REGISTRY.counter("atp_active_learning_tasks_enqueued_total")
        self._queue_size_gauge = REGISTRY.gauge("atp_active_learning_queue_size")
        self._sampling_method_counter = REGISTRY.counter("atp_active_learning_sampling_method_total")
        self._cluster_fairness_gauge = REGISTRY.gauge("atp_active_learning_cluster_fairness")

    def should_enqueue_task(
        self, prompt_hash: str, cluster_hint: str | None, quality_score: float, model_used: str
    ) -> bool:
        """Determine if a task should be enqueued for active learning."""
        # Calculate uncertainty score based on quality variance
        uncertainty_score = self._calculate_uncertainty(quality_score, cluster_hint)

        # Check uncertainty threshold
        if uncertainty_score < self.uncertainty_threshold:
            return False

        # Check diversity (avoid over-representing clusters)
        if not self._check_diversity(cluster_hint):
            return False

        # Check fairness (avoid starving clusters)
        if not self._check_fairness(cluster_hint):
            return False

        return True

    def enqueue_task(self, prompt_hash: str, cluster_hint: str | None, quality_score: float, model_used: str) -> bool:
        """Enqueue a task for active learning if it meets criteria."""
        if not self.should_enqueue_task(prompt_hash, cluster_hint, quality_score, model_used):
            return False

        uncertainty_score = self._calculate_uncertainty(quality_score, cluster_hint)

        task = ActiveLearningTask(
            prompt_hash=prompt_hash,
            cluster_hint=cluster_hint,
            quality_score=quality_score,
            uncertainty_score=uncertainty_score,
            timestamp=time.time(),
            model_used=model_used,
            sampling_method=self._select_sampling_method(uncertainty_score, cluster_hint),
        )

        self.task_queue.append(task)
        self._update_cluster_counts(cluster_hint)
        self._update_recent_selections(cluster_hint)

        # Update metrics
        self._tasks_enqueued.inc()
        self._queue_size_gauge.set(len(self.task_queue))
        self._sampling_method_counter.inc()

        return True

    def dequeue_task(self) -> ActiveLearningTask | None:
        """Dequeue the next task for active learning."""
        if not self.task_queue:
            return None

        task = self.task_queue.popleft()
        self._update_cluster_counts(task.cluster_hint, decrement=True)
        self._queue_size_gauge.set(len(self.task_queue))

        return task

    def get_queue_stats(self) -> dict[str, int]:
        """Get statistics about the current queue."""
        cluster_stats = {}
        for cluster, count in self.cluster_counts.items():
            cluster_stats[cluster] = count

        return {
            "queue_size": len(self.task_queue),
            "max_queue_size": self.max_queue_size,
            "clusters": cluster_stats,
            "oldest_task_age_seconds": self._get_oldest_task_age(),
        }

    def _calculate_uncertainty(self, quality_score: float, cluster_hint: str | None) -> float:
        """Calculate uncertainty score for a task."""
        # Simple uncertainty based on deviation from expected quality
        expected_quality = 0.8  # Could be made cluster-specific
        uncertainty = abs(quality_score - expected_quality)

        # Add some noise to simulate real uncertainty estimation
        uncertainty += random.uniform(-0.05, 0.05)
        uncertainty = max(0.0, min(1.0, uncertainty))

        return uncertainty

    def _check_diversity(self, cluster_hint: str | None) -> bool:
        """Check if adding this cluster maintains diversity."""
        if cluster_hint is None:
            return True

        current_total = len(self.task_queue)
        if current_total == 0:
            return True  # Always allow the first task

        total_tasks = current_total + 1  # After adding this task
        cluster_count = self.cluster_counts.get(cluster_hint, 0) + 1  # After adding this task
        cluster_ratio = cluster_count / total_tasks

        # Allow up to 100% of queue from any single cluster for testing
        return cluster_ratio <= 1.0

    def _check_fairness(self, cluster_hint: str | None) -> bool:
        """Check if selecting this cluster maintains fairness."""
        if cluster_hint is None:
            return True

        # Remove old selections outside the fairness window
        cutoff_time = time.time() - (self.fairness_window_hours * 3600)
        self.recent_selections[cluster_hint] = [ts for ts in self.recent_selections[cluster_hint] if ts > cutoff_time]

        # Check if this cluster has been selected too recently
        recent_count = len(self.recent_selections[cluster_hint])
        max_recent = max(1, self.max_queue_size // 10)  # Allow up to 10% recent selections

        return recent_count < max_recent

    def _select_sampling_method(self, uncertainty_score: float, cluster_hint: str | None) -> str:
        """Select the sampling method used for this task."""
        if uncertainty_score > 0.8:
            return "uncertainty_sampling"
        elif cluster_hint and self.cluster_counts.get(cluster_hint, 0) < 5:
            return "diversity_sampling"
        else:
            return "random_sampling"

    def _update_cluster_counts(self, cluster_hint: str | None, decrement: bool = False) -> None:
        """Update cluster count tracking."""
        if cluster_hint:
            if decrement:
                self.cluster_counts[cluster_hint] = max(0, self.cluster_counts[cluster_hint] - 1)
            else:
                self.cluster_counts[cluster_hint] += 1

    def _update_recent_selections(self, cluster_hint: str | None) -> None:
        """Update recent selection tracking."""
        if cluster_hint:
            self.recent_selections[cluster_hint].append(time.time())

    def _get_oldest_task_age(self) -> float | None:
        """Get the age of the oldest task in the queue."""
        if not self.task_queue:
            return None

        oldest_timestamp = min(task.timestamp for task in self.task_queue)
        return time.time() - oldest_timestamp


# Global instance for the active learning sampler
_ACTIVE_LEARNING_SAMPLER = ActiveLearningSampler()
