"""Tests for Active Learning Task Enqueue System (GAP-203)
Tests sampling policies, fairness constraints, and task selection.
"""

import time

from router_service.active_learning_sampler import ActiveLearningSampler, ActiveLearningTask


class TestActiveLearningTask:
    """Test the ActiveLearningTask dataclass."""

    def test_task_creation(self):
        """Test creating an active learning task."""
        task = ActiveLearningTask(
            prompt_hash="abc123",
            cluster_hint="code",
            quality_score=0.75,
            uncertainty_score=0.8,
            timestamp=1000.0,
            model_used="gpt-4",
            sampling_method="uncertainty_sampling",
        )

        assert task.prompt_hash == "abc123"
        assert task.cluster_hint == "code"
        assert task.quality_score == 0.75
        assert task.uncertainty_score == 0.8
        assert task.timestamp == 1000.0
        assert task.model_used == "gpt-4"
        assert task.sampling_method == "uncertainty_sampling"


class TestActiveLearningSampler:
    """Test the ActiveLearningSampler class."""

    def test_initialization(self):
        """Test sampler initialization."""
        sampler = ActiveLearningSampler(
            max_queue_size=50, uncertainty_threshold=0.6, diversity_weight=0.4, fairness_window_hours=12
        )

        assert sampler.max_queue_size == 50
        assert sampler.uncertainty_threshold == 0.6
        assert sampler.diversity_weight == 0.4
        assert sampler.fairness_window_hours == 12
        assert len(sampler.task_queue) == 0
        assert len(sampler.cluster_counts) == 0

    def test_should_enqueue_high_uncertainty_task(self):
        """Test that high uncertainty tasks are enqueued."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.5)

        # High uncertainty task (quality far from expected)
        should_enqueue = sampler.should_enqueue_task(
            prompt_hash="test1",
            cluster_hint="code",
            quality_score=0.2,  # Far from expected 0.8
            model_used="gpt-4",
        )

        assert should_enqueue

    def test_should_not_enqueue_low_uncertainty_task(self):
        """Test that low uncertainty tasks are not enqueued."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.8)

        # Low uncertainty task (quality close to expected)
        should_enqueue = sampler.should_enqueue_task(
            prompt_hash="test1",
            cluster_hint="code",
            quality_score=0.75,  # Close to expected 0.8
            model_used="gpt-4",
        )

        assert not should_enqueue

    def test_enqueue_task_success(self):
        """Test successful task enqueue."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.5)

        success = sampler.enqueue_task(prompt_hash="test1", cluster_hint="code", quality_score=0.2, model_used="gpt-4")

        assert success
        assert len(sampler.task_queue) == 1
        assert sampler.cluster_counts["code"] == 1

    def test_enqueue_task_failure(self):
        """Test failed task enqueue."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.9)

        success = sampler.enqueue_task(
            prompt_hash="test1",
            cluster_hint="code",
            quality_score=0.8,  # Low uncertainty
            model_used="gpt-4",
        )

        assert not success
        assert len(sampler.task_queue) == 0

    def test_diversity_check(self):
        """Test diversity constraint enforcement."""
        sampler = ActiveLearningSampler(max_queue_size=10)

        # Fill queue with one cluster
        for i in range(5):
            sampler.task_queue.append(
                ActiveLearningTask(
                    prompt_hash=f"test{i}",
                    cluster_hint="code",
                    quality_score=0.5,
                    uncertainty_score=0.8,
                    timestamp=time.time(),
                    model_used="gpt-4",
                    sampling_method="uncertainty_sampling",
                )
            )
        sampler.cluster_counts["code"] = 5

        # Try to add another task from same cluster (should fail diversity check)
        should_enqueue = sampler.should_enqueue_task(
            prompt_hash="test6", cluster_hint="code", quality_score=0.5, model_used="gpt-4"
        )

        assert not should_enqueue  # 6/5 = 120% > 40% limit

    def test_fairness_check(self):
        """Test fairness constraint enforcement."""
        sampler = ActiveLearningSampler(max_queue_size=20, fairness_window_hours=1)

        # Simulate recent selections for a cluster
        sampler.recent_selections["code"] = [time.time()] * 3  # 3 recent selections

        # Try to add another task from same cluster (should fail fairness check)
        should_enqueue = sampler.should_enqueue_task(
            prompt_hash="test1", cluster_hint="code", quality_score=0.5, model_used="gpt-4"
        )

        assert not should_enqueue  # Too many recent selections

    def test_dequeue_task(self):
        """Test task dequeue."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.5)

        # Add a task
        sampler.enqueue_task(prompt_hash="test1", cluster_hint="code", quality_score=0.2, model_used="gpt-4")

        # Dequeue the task
        task = sampler.dequeue_task()

        assert task is not None
        assert task.prompt_hash == "test1"
        assert task.cluster_hint == "code"
        assert len(sampler.task_queue) == 0
        assert sampler.cluster_counts["code"] == 0

    def test_dequeue_empty_queue(self):
        """Test dequeue from empty queue."""
        sampler = ActiveLearningSampler()

        task = sampler.dequeue_task()
        assert task is None

    def test_get_queue_stats(self):
        """Test getting queue statistics."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.5)

        # Add some tasks
        sampler.enqueue_task("test1", "code", 0.2, "gpt-4")
        sampler.enqueue_task("test2", "summarize", 0.1, "gpt-4")
        sampler.enqueue_task("test3", "code", 0.15, "gpt-4")

        stats = sampler.get_queue_stats()

        assert stats["queue_size"] == 3
        assert stats["max_queue_size"] == 1000
        assert stats["clusters"]["code"] == 2
        assert stats["clusters"]["summarize"] == 1
        assert stats["oldest_task_age_seconds"] is not None

    def test_sampling_method_selection(self):
        """Test sampling method selection."""
        sampler = ActiveLearningSampler()

        # High uncertainty should use uncertainty sampling
        method = sampler._select_sampling_method(0.9, "code")
        assert method == "uncertainty_sampling"

        # Low count cluster should use diversity sampling
        sampler.cluster_counts["rare_cluster"] = 2
        method = sampler._select_sampling_method(0.6, "rare_cluster")
        assert method == "diversity_sampling"

        # Default should use random sampling
        sampler.cluster_counts["common_cluster"] = 10  # High count, should use random
        method = sampler._select_sampling_method(0.6, "common_cluster")
        assert method == "random_sampling"

    def test_metrics_integration(self):
        """Test that metrics are properly updated."""
        sampler = ActiveLearningSampler(uncertainty_threshold=0.5)

        # Get initial metric values
        initial_enqueued = sampler._tasks_enqueued.value
        _initial_queue_size = sampler._queue_size_gauge.value
        initial_sampling = sampler._sampling_method_counter.value

        # Enqueue a task
        result = sampler.enqueue_task("test1", "code", 0.2, "gpt-4")
        assert result  # Make sure it was enqueued

        # Check that metrics were updated
        assert sampler._tasks_enqueued.value == initial_enqueued + 1
        assert sampler._queue_size_gauge.value == 1
        assert sampler._sampling_method_counter.value == initial_sampling + 1


class TestIntegrationWithService:
    """Integration tests with service components."""

    def test_active_learning_workflow(self):
        """Test complete active learning workflow."""
        sampler = ActiveLearningSampler(max_queue_size=20, uncertainty_threshold=0.5)

        # Simulate various tasks
        tasks_to_enqueue = [
            ("hash1", "code", 0.2, "gpt-4"),  # High uncertainty - should enqueue
            ("hash2", "summarize", 0.75, "gpt-4"),  # Low uncertainty - should not enqueue
            ("hash3", "extract", 0.1, "gpt-4"),  # High uncertainty - should enqueue
            ("hash4", "code", 0.8, "gpt-4"),  # Low uncertainty - should not enqueue
        ]

        enqueued_count = 0
        for prompt_hash, cluster, quality, model in tasks_to_enqueue:
            if sampler.enqueue_task(prompt_hash, cluster, quality, model):
                enqueued_count += 1

        assert enqueued_count == 2  # Only high uncertainty tasks
        assert len(sampler.task_queue) == 2

        # Test dequeue
        task1 = sampler.dequeue_task()
        task2 = sampler.dequeue_task()
        task3 = sampler.dequeue_task()  # Should be None

        assert task1 is not None
        assert task2 is not None
        assert task3 is None
        assert len(sampler.task_queue) == 0

    def test_cluster_balance_over_time(self):
        """Test that cluster balancing works over multiple enqueues."""
        sampler = ActiveLearningSampler(max_queue_size=50, uncertainty_threshold=0.5)

        # Add many tasks from one cluster
        for i in range(10):
            sampler.enqueue_task(f"hash{i}", "code", 0.1, "gpt-4")

        # Try to add more from same cluster (should be rejected due to diversity)
        success = sampler.enqueue_task("hash_new", "code", 0.1, "gpt-4")
        assert not success

        # Add from different cluster (should succeed)
        success = sampler.enqueue_task("hash_diff", "summarize", 0.1, "gpt-4")
        assert success

        # Check cluster distribution
        stats = sampler.get_queue_stats()
        assert stats["clusters"]["code"] >= 5  # Should allow several from same cluster
        assert stats["clusters"]["summarize"] == 1
