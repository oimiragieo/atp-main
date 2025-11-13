#!/usr/bin/env python3
"""GPU Batch Scheduler for Router-side Request Batching."""

import asyncio
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Optional GPU dependencies
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not available. GPU batching disabled.")

from tools.adapter_metrics import get_metrics_collector


@dataclass
class BatchRequest:
    """Represents a single request in a batch."""

    request_id: str
    adapter_name: str
    prompt_tokens: list[int]
    max_tokens: int
    temperature: float
    timestamp: float
    callback: Callable[[dict[str, Any]], None]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    max_batch_size: int = 32
    max_sequence_length: int = 2048
    batch_timeout_ms: int = 50
    adaptive_batching: bool = True
    gpu_memory_threshold: float = 0.8
    latency_target_ms: int = 200


@dataclass
class BatchMetrics:
    """Metrics for batch processing."""

    batch_size: int
    processing_time_ms: float
    gpu_memory_used: float
    throughput_tokens_per_sec: float
    latency_p95_ms: float
    timestamp: float


class GPUBatchScheduler:
    """GPU-accelerated batch scheduler for adapter requests."""

    def __init__(self, config: BatchConfig = None):
        self.config = config or BatchConfig()
        self.metrics_collector = get_metrics_collector()

        # Request queues by adapter
        self.request_queues: dict[str, deque] = defaultdict(deque)
        self.batch_queues: dict[str, list[BatchRequest]] = defaultdict(list)

        # Processing state
        self.processing_batches: dict[str, bool] = defaultdict(bool)
        self.batch_metrics: list[BatchMetrics] = []

        # GPU state
        self.gpu_available = TORCH_AVAILABLE and torch.cuda.is_available()
        self.gpu_memory_total = 0
        self.gpu_memory_used = 0

        if self.gpu_available:
            self.gpu_memory_total = torch.cuda.get_device_properties(0).total_memory
            self._update_gpu_memory()

        # Control flags
        self.running = False
        self.scheduler_thread: threading.Thread | None = None
        self.scheduler_task: asyncio.Task | None = None

        # Adaptive batching state
        self.latency_history: list[float] = []
        self.throughput_history: list[float] = []
        self.optimal_batch_size = self.config.max_batch_size

        # Logging
        self.logger = logging.getLogger(__name__)

    def _update_gpu_memory(self):
        """Update GPU memory usage statistics."""
        if self.gpu_available:
            self.gpu_memory_used = torch.cuda.memory_allocated(0)

    def _get_gpu_memory_usage(self) -> float:
        """Get current GPU memory usage as fraction."""
        if not self.gpu_available:
            return 0.0
        return self.gpu_memory_used / self.gpu_memory_total

    def _should_process_batch(self, adapter_name: str) -> bool:
        """Determine if a batch should be processed."""
        queue = self.request_queues[adapter_name]

        # Check batch size
        if len(queue) >= self.optimal_batch_size:
            return True

        # Check timeout (if we have any requests)
        if queue:
            oldest_request = queue[0]
            age_ms = (time.time() - oldest_request.timestamp) * 1000
            if age_ms >= self.config.batch_timeout_ms:
                return True

        # Check GPU memory
        if self._get_gpu_memory_usage() > self.config.gpu_memory_threshold:
            return True

        return False

    def _create_batch(self, adapter_name: str) -> list[BatchRequest]:
        """Create a batch from pending requests."""
        queue = self.request_queues[adapter_name]
        batch = []

        # Adaptive batch size based on latency target
        target_batch_size = self._calculate_optimal_batch_size()

        for _ in range(min(target_batch_size, len(queue))):
            if queue:
                batch.append(queue.popleft())

        return batch

    def _calculate_optimal_batch_size(self) -> int:
        """Calculate optimal batch size based on latency history."""
        if not self.config.adaptive_batching or not self.latency_history:
            return self.config.max_batch_size

        # Simple adaptive algorithm: reduce batch size if latency is too high
        recent_latencies = self.latency_history[-10:]  # Last 10 batches
        if recent_latencies:
            avg_latency = statistics.mean(recent_latencies)
            if avg_latency > self.config.latency_target_ms:
                # Reduce batch size to improve latency
                self.optimal_batch_size = max(1, self.optimal_batch_size - 2)
            elif avg_latency < self.config.latency_target_ms * 0.8:
                # Increase batch size to improve throughput
                self.optimal_batch_size = min(self.config.max_batch_size, self.optimal_batch_size + 1)

        return self.optimal_batch_size

    async def _process_batch(self, adapter_name: str, batch: list[BatchRequest]):
        """Process a batch of requests."""
        if not batch:
            return

        start_time = time.time()
        batch_size = len(batch)

        try:
            # Simulate GPU processing (replace with actual adapter calls)
            if self.gpu_available:
                await self._process_batch_gpu(batch)
            else:
                await self._process_batch_cpu(batch)

            processing_time = (time.time() - start_time) * 1000

            # Calculate metrics
            total_tokens = sum(len(req.prompt_tokens) for req in batch)
            throughput = total_tokens / (processing_time / 1000) if processing_time > 0 else 0

            # Update latency history for adaptive batching
            self.latency_history.append(processing_time)
            self.throughput_history.append(throughput)

            # Keep history bounded
            if len(self.latency_history) > 100:
                self.latency_history = self.latency_history[-100:]
            if len(self.throughput_history) > 100:
                self.throughput_history = self.throughput_history[-100:]

            # Record metrics
            batch_metrics = BatchMetrics(
                batch_size=batch_size,
                processing_time_ms=processing_time,
                gpu_memory_used=self._get_gpu_memory_usage(),
                throughput_tokens_per_sec=throughput,
                latency_p95_ms=statistics.quantiles(self.latency_history, n=4)[-1]
                if len(self.latency_history) >= 4
                else (max(self.latency_history) if self.latency_history else 0),
                timestamp=time.time(),
            )

            self.batch_metrics.append(batch_metrics)

            # Update global metrics
            self.metrics_collector.record_request(adapter_name, "batch_estimate", processing_time / batch_size, True)

            # Update GPU memory
            self._update_gpu_memory()

            self.logger.info(f"Processed batch for {adapter_name}: size={batch_size}, .2f.2f")

        except Exception as e:
            self.logger.error(f"Batch processing failed for {adapter_name}: {e}")
            # Record failed requests
            for _ in batch:
                self.metrics_collector.record_request(adapter_name, "batch_estimate", 0, False)

    async def _process_batch_gpu(self, batch: list[BatchRequest]):
        """Process batch using GPU acceleration."""
        # Placeholder for actual GPU processing
        # This would integrate with actual adapter GPU processing

        # Simulate GPU processing time based on batch size
        processing_time = 10 + (len(batch) * 2)  # Base 10ms + 2ms per request
        await asyncio.sleep(processing_time / 1000)

        # Simulate GPU memory usage
        if self.gpu_available:
            # Allocate some GPU memory temporarily
            temp_tensor = torch.randn(100, 100).cuda()
            del temp_tensor
            torch.cuda.empty_cache()

    async def _process_batch_cpu(self, batch: list[BatchRequest]):
        """Process batch using CPU fallback."""
        # CPU processing simulation
        processing_time = 20 + (len(batch) * 5)  # Base 20ms + 5ms per request
        await asyncio.sleep(processing_time / 1000)

    def submit_request(self, adapter_name: str, request: BatchRequest):
        """Submit a request for batch processing."""
        self.request_queues[adapter_name].append(request)

        # Trigger batch processing if conditions met
        if self._should_process_batch(adapter_name) and not self.processing_batches[adapter_name]:
            self.processing_batches[adapter_name] = True
            # Only create async task if there's a running event loop
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._schedule_batch_processing(adapter_name))
            except RuntimeError:
                # No running event loop, process synchronously for testing
                pass

    async def _schedule_batch_processing(self, adapter_name: str):
        """Schedule batch processing for an adapter."""
        try:
            while self.request_queues[adapter_name]:
                if self._should_process_batch(adapter_name):
                    batch = self._create_batch(adapter_name)
                    if batch:
                        await self._process_batch(adapter_name, batch)
                else:
                    await asyncio.sleep(0.01)  # Small delay before checking again
        finally:
            self.processing_batches[adapter_name] = False

    def start_scheduler(self):
        """Start the batch scheduler."""
        if self.running:
            return

        self.running = True
        # Create async task instead of thread
        try:
            loop = asyncio.get_running_loop()
            self.scheduler_task = asyncio.create_task(self._scheduler_loop_async())
        except RuntimeError:
            # No running event loop, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.scheduler_task = loop.create_task(self._scheduler_loop_async())

        self.logger.info("GPU Batch Scheduler started")

    def stop_scheduler(self):
        """Stop the batch scheduler."""
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                # Wait for task to complete
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.scheduler_task)
            except (RuntimeError, asyncio.CancelledError):
                pass
        self.logger.info("GPU Batch Scheduler stopped")

    async def _scheduler_loop_async(self):
        """Main scheduler loop running as async task."""
        while self.running:
            try:
                # Check all adapters for batch processing
                for adapter_name in list(self.request_queues.keys()):
                    if self._should_process_batch(adapter_name) and not self.processing_batches[adapter_name]:
                        self.processing_batches[adapter_name] = True
                        # Schedule async processing directly
                        asyncio.create_task(self._schedule_batch_processing(adapter_name))

                await asyncio.sleep(0.01)  # 10ms polling interval

            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(1.0)  # Back off on errors

    def _scheduler_loop(self):
        """Legacy sync scheduler loop for backward compatibility."""
        import time

        while self.running:
            try:
                # Check all adapters for batch processing
                for adapter_name in list(self.request_queues.keys()):
                    if self._should_process_batch(adapter_name) and not self.processing_batches[adapter_name]:
                        self.processing_batches[adapter_name] = True
                        # Schedule async processing
                        asyncio.run(self._schedule_batch_processing(adapter_name))

                time.sleep(0.01)  # 10ms polling interval

            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                time.sleep(1.0)  # Back off on errors

    def get_batch_stats(self) -> dict[str, Any]:
        """Get current batch processing statistics."""
        total_batches = len(self.batch_metrics)
        if not total_batches:
            return {
                "total_batches": 0,
                "avg_batch_size": 0,
                "avg_processing_time_ms": 0,
                "avg_throughput_tokens_per_sec": 0,
                "gpu_available": self.gpu_available,
                "current_optimal_batch_size": self.optimal_batch_size,
            }

        recent_metrics = self.batch_metrics[-min(10, total_batches) :]

        return {
            "total_batches": total_batches,
            "avg_batch_size": statistics.mean(m.batch_size for m in recent_metrics),
            "avg_processing_time_ms": statistics.mean(m.processing_time_ms for m in recent_metrics),
            "avg_throughput_tokens_per_sec": statistics.mean(m.throughput_tokens_per_sec for m in recent_metrics),
            "gpu_available": self.gpu_available,
            "gpu_memory_usage": self._get_gpu_memory_usage(),
            "current_optimal_batch_size": self.optimal_batch_size,
            "latency_p95_ms": statistics.quantiles(self.latency_history, n=20)[18] if self.latency_history else 0,
        }

    def get_queue_depth(self, adapter_name: str) -> int:
        """Get current queue depth for an adapter."""
        return len(self.request_queues[adapter_name])


# Global scheduler instance
_scheduler_instance: GPUBatchScheduler | None = None


def get_batch_scheduler(config: BatchConfig = None) -> GPUBatchScheduler:
    """Get the global batch scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = GPUBatchScheduler(config)
    return _scheduler_instance


def start_batch_scheduler(config: BatchConfig = None):
    """Start the global batch scheduler."""
    scheduler = get_batch_scheduler(config)
    scheduler.start_scheduler()


def stop_batch_scheduler():
    """Stop the global batch scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop_scheduler()
        _scheduler_instance = None


if __name__ == "__main__":
    # Example usage
    config = BatchConfig(max_batch_size=16, batch_timeout_ms=100, adaptive_batching=True, latency_target_ms=150)

    scheduler = get_batch_scheduler(config)
    start_batch_scheduler(config)

    print("GPU Batch Scheduler initialized")
    print(f"GPU Available: {scheduler.gpu_available}")
    print(f"Optimal Batch Size: {scheduler.optimal_batch_size}")

    # Example request submission
    def example_callback(result):
        print(f"Request completed: {result}")

    request = BatchRequest(
        request_id="test-1",
        adapter_name="test_adapter",
        prompt_tokens=[1, 2, 3, 4, 5],
        max_tokens=100,
        temperature=0.7,
        timestamp=time.time(),
        callback=example_callback,
    )

    scheduler.submit_request("test_adapter", request)

    # Let it process
    time.sleep(2)

    # Get stats
    stats = scheduler.get_batch_stats()
    print("Batch Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    stop_batch_scheduler()
