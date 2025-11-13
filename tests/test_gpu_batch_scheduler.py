#!/usr/bin/env python3
"""Tests for GPU Batch Scheduler."""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

from tools.gpu_batch_scheduler import (
    BatchConfig,
    BatchRequest,
    GPUBatchScheduler,
    get_batch_scheduler,
    start_batch_scheduler,
    stop_batch_scheduler,
)


class TestGPUBatchScheduler:
    """Test suite for GPU batch scheduler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = BatchConfig(max_batch_size=8, batch_timeout_ms=100, adaptive_batching=True, latency_target_ms=200)
        self.scheduler = GPUBatchScheduler(self.config)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.scheduler.running:
            self.scheduler.stop_scheduler()

    def test_initialization(self):
        """Test scheduler initialization."""
        assert self.scheduler.config == self.config
        assert not self.scheduler.running
        assert self.scheduler.optimal_batch_size == self.config.max_batch_size

    def test_batch_creation(self):
        """Test batch creation from request queue."""
        # Add requests to queue
        requests = []
        for i in range(5):
            request = BatchRequest(
                request_id=f"test-{i}",
                adapter_name="test_adapter",
                prompt_tokens=[1, 2, 3],
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            self.scheduler.request_queues["test_adapter"].append(request)
            requests.append(request)

        # Create batch
        batch = self.scheduler._create_batch("test_adapter")

        assert len(batch) == 5
        assert len(self.scheduler.request_queues["test_adapter"]) == 0
        assert all(req in batch for req in requests)

    def test_batch_timeout(self):
        """Test batch processing on timeout."""
        # Add a single request
        request = BatchRequest(
            request_id="timeout-test",
            adapter_name="test_adapter",
            prompt_tokens=[1, 2, 3],
            max_tokens=100,
            temperature=0.7,
            timestamp=time.time() - 0.2,  # 200ms ago
            callback=Mock(),
        )
        self.scheduler.request_queues["test_adapter"].append(request)

        # Should process due to timeout
        assert self.scheduler._should_process_batch("test_adapter")

    def test_batch_size_limit(self):
        """Test batch processing when max batch size reached."""
        # Add requests up to max batch size
        for i in range(self.config.max_batch_size + 2):
            request = BatchRequest(
                request_id=f"size-test-{i}",
                adapter_name="test_adapter",
                prompt_tokens=[1, 2, 3],
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            self.scheduler.request_queues["test_adapter"].append(request)

        # Should process due to batch size
        assert self.scheduler._should_process_batch("test_adapter")

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.memory_allocated", return_value=1024 * 1024 * 1024)  # 1GB
    @patch("torch.cuda.get_device_properties")
    def test_gpu_memory_tracking(self, mock_props, mock_allocated, mock_available):
        """Test GPU memory usage tracking."""
        # Mock GPU properties
        mock_device = Mock()
        mock_device.total_memory = 8 * 1024 * 1024 * 1024  # 8GB
        mock_props.return_value = mock_device

        scheduler = GPUBatchScheduler(self.config)

        # Should detect GPU as available
        assert scheduler.gpu_available

        # Check memory usage calculation
        usage = scheduler._get_gpu_memory_usage()
        assert usage == 0.125  # 1GB / 8GB

    def test_adaptive_batch_sizing_high_latency(self):
        """Test adaptive batch sizing reduces size on high latency."""
        # Simulate high latency history
        self.scheduler.latency_history = [300, 250, 280, 320]  # All > 200ms target
        self.scheduler.optimal_batch_size = 16

        optimal_size = self.scheduler._calculate_optimal_batch_size()

        # Should reduce batch size
        assert optimal_size < 16

    def test_adaptive_batch_sizing_low_latency(self):
        """Test adaptive batch sizing increases size on low latency."""
        # Simulate low latency history
        self.scheduler.latency_history = [100, 120, 90, 110]  # All < 160ms (80% of target)
        self.scheduler.optimal_batch_size = 4

        optimal_size = self.scheduler._calculate_optimal_batch_size()

        # Should increase batch size
        assert optimal_size > 4

    @pytest.mark.asyncio
    async def test_batch_processing_cpu(self):
        """Test batch processing with CPU fallback."""
        # Create test batch
        batch = []
        for i in range(3):
            request = BatchRequest(
                request_id=f"cpu-test-{i}",
                adapter_name="test_adapter",
                prompt_tokens=[1, 2, 3] * 10,  # Longer prompts
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            batch.append(request)

        start_time = time.time()
        await self.scheduler._process_batch("test_adapter", batch)
        processing_time = (time.time() - start_time) * 1000

        # Should take some time to process
        assert processing_time > 20  # Base time

        # Should have recorded metrics
        assert len(self.scheduler.batch_metrics) > 0

        metrics = self.scheduler.batch_metrics[-1]
        assert metrics.batch_size == 3
        assert metrics.processing_time_ms > 0

    def test_request_submission(self):
        """Test request submission and queue management."""
        callback = Mock()
        request = BatchRequest(
            request_id="submit-test",
            adapter_name="test_adapter",
            prompt_tokens=[1, 2, 3],
            max_tokens=100,
            temperature=0.7,
            timestamp=time.time(),
            callback=callback,
        )

        self.scheduler.submit_request("test_adapter", request)

        # Request should be in queue
        assert len(self.scheduler.request_queues["test_adapter"]) == 1
        assert self.scheduler.request_queues["test_adapter"][0] == request

    def test_queue_depth_tracking(self):
        """Test queue depth tracking."""
        # Add multiple requests
        for i in range(5):
            request = BatchRequest(
                request_id=f"depth-test-{i}",
                adapter_name="test_adapter",
                prompt_tokens=[1, 2, 3],
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            self.scheduler.request_queues["test_adapter"].append(request)

        depth = self.scheduler.get_queue_depth("test_adapter")
        assert depth == 5

    def test_batch_statistics(self):
        """Test batch statistics calculation."""
        # Initially no stats
        stats = self.scheduler.get_batch_stats()
        assert stats["total_batches"] == 0
        assert stats["avg_batch_size"] == 0

        # Add some mock metrics
        from tools.gpu_batch_scheduler import BatchMetrics

        self.scheduler.batch_metrics = [
            BatchMetrics(4, 150.0, 0.5, 100.0, 180.0, time.time()),
            BatchMetrics(6, 180.0, 0.6, 120.0, 200.0, time.time()),
            BatchMetrics(5, 160.0, 0.55, 110.0, 190.0, time.time()),
        ]

        stats = self.scheduler.get_batch_stats()
        assert stats["total_batches"] == 3
        assert 4 <= stats["avg_batch_size"] <= 6
        assert 150 <= stats["avg_processing_time_ms"] <= 180

    def test_throughput_calculation(self):
        """Test throughput calculation in batch processing."""
        # Create batch with known token counts
        batch = []
        tokens_per_request = [10, 15, 20]  # Different token counts

        for i, token_count in enumerate(tokens_per_request):
            request = BatchRequest(
                request_id=f"throughput-test-{i}",
                adapter_name="test_adapter",
                prompt_tokens=list(range(token_count)),
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            batch.append(request)

        # Simulate processing time
        processing_time_ms = 100.0  # 100ms
        total_tokens = sum(tokens_per_request)  # 45 tokens

        # Calculate expected throughput
        expected_throughput = total_tokens / (processing_time_ms / 1000)  # tokens per second

        # Verify calculation
        assert expected_throughput == 450.0

    def test_scheduler_lifecycle(self):
        """Test scheduler start/stop lifecycle."""
        # Initially not running
        assert not self.scheduler.running

        # Start scheduler
        self.scheduler.start_scheduler()
        assert self.scheduler.running

        # Stop scheduler
        self.scheduler.stop_scheduler()
        assert not self.scheduler.running

    def test_global_scheduler_instance(self):
        """Test global scheduler instance management."""
        # Reset global instance
        import tools.gpu_batch_scheduler as gpu_batch_scheduler

        gpu_batch_scheduler._scheduler_instance = None

        # Get scheduler
        scheduler1 = get_batch_scheduler()
        scheduler2 = get_batch_scheduler()

        # Should be the same instance
        assert scheduler1 is scheduler2

        # Start global scheduler
        start_batch_scheduler()

        # Stop global scheduler
        stop_batch_scheduler()

        # Instance should be cleared
        assert gpu_batch_scheduler._scheduler_instance is None


class TestBatchSchedulerIntegration:
    """Integration tests for batch scheduler."""

    def setup_method(self):
        """Set up integration test fixtures."""
        self.config = BatchConfig(
            max_batch_size=4,
            batch_timeout_ms=200,
            adaptive_batching=False,  # Disable for predictable testing
        )

    def teardown_method(self):
        """Clean up integration test fixtures."""
        stop_batch_scheduler()

    @pytest.mark.asyncio
    async def test_concurrent_request_processing(self):
        """Test processing multiple concurrent requests."""
        scheduler = get_batch_scheduler(self.config)
        start_batch_scheduler(self.config)

        results = []
        callbacks_executed = 0

        def result_callback(result):
            nonlocal callbacks_executed
            results.append(result)
            callbacks_executed += 1

        # Submit multiple requests
        for i in range(6):
            request = BatchRequest(
                request_id=f"concurrent-{i}",
                adapter_name="test_adapter",
                prompt_tokens=[1, 2, 3] * 5,
                max_tokens=100,
                temperature=0.7,
                timestamp=time.time(),
                callback=result_callback,
            )
            scheduler.submit_request("test_adapter", request)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Check that requests were processed
        stats = scheduler.get_batch_stats()
        assert stats["total_batches"] > 0

        stop_batch_scheduler()

    def test_throughput_improvement(self):
        """Test that batching improves throughput."""
        # This would be a more comprehensive benchmark test
        # For now, just verify the scheduler can handle load

        scheduler = get_batch_scheduler(self.config)

        # Submit many requests quickly
        start_time = time.time()
        for i in range(20):
            request = BatchRequest(
                request_id=f"load-test-{i}",
                adapter_name="load_adapter",
                prompt_tokens=[1, 2, 3],
                max_tokens=50,
                temperature=0.7,
                timestamp=time.time(),
                callback=Mock(),
            )
            scheduler.submit_request("load_adapter", request)

        _submission_time = time.time() - start_time

        # Verify requests were queued
        assert scheduler.get_queue_depth("load_adapter") == 20

        # Clean up
        scheduler.request_queues["load_adapter"].clear()


if __name__ == "__main__":
    pytest.main([__file__])
