"""
Tests for GAP-309: Vector backfill & re-embedding pipeline.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.reembed_orchestrator import (
    ReembedJobOrchestrator,
    ReembedJobPriority,
    ReembedJobStatus,
    get_reembed_orchestrator,
    initialize_reembed_orchestrator,
)


class TestReembedJobOrchestrator:
    """Test cases for the re-embedding job orchestrator."""

    @pytest.fixture
    def mock_vector_backend(self):
        """Mock vector backend for testing."""
        backend = MagicMock()
        backend.health_check = AsyncMock(return_value=True)
        return backend

    @pytest.fixture
    def mock_embedding_service(self):
        """Mock embedding service for testing."""
        service = MagicMock()
        service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return service

    @pytest.fixture
    def orchestrator(self, mock_vector_backend, mock_embedding_service):
        """Create a test orchestrator instance."""
        orch = ReembedJobOrchestrator(
            vector_backend=mock_vector_backend,
            embedding_service=mock_embedding_service,
            max_concurrent_jobs=2,
            batch_size=10,
        )
        return orch

    @pytest.mark.asyncio
    async def test_submit_job(self, orchestrator):
        """Test submitting a new re-embedding job."""
        await orchestrator.start()
        try:
            job_id = await orchestrator.submit_job(
                namespace="test_namespace",
                source_model="old-model-v1",
                target_model="new-model-v2",
                priority=ReembedJobPriority.HIGH,
            )

            assert job_id in orchestrator.jobs
            job = orchestrator.jobs[job_id]
            assert job.namespace == "test_namespace"
            assert job.source_model == "old-model-v1"
            assert job.target_model == "new-model-v2"
            assert job.priority == ReembedJobPriority.HIGH
            assert job.status == ReembedJobStatus.PENDING
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_get_job_status(self, orchestrator):
        """Test getting job status."""
        await orchestrator.start()
        try:
            job_id = await orchestrator.submit_job(
                namespace="test_namespace", source_model="old-model", target_model="new-model"
            )

            job = orchestrator.get_job_status(job_id)
            assert job is not None
            assert job.job_id == job_id

            # Test non-existent job
            assert orchestrator.get_job_status("non-existent") is None
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_list_jobs(self, orchestrator):
        """Test listing jobs with optional status filter."""
        await orchestrator.start()
        try:
            # Submit multiple jobs
            await orchestrator.submit_job("ns1", "old", "new")
            await orchestrator.submit_job("ns2", "old", "new")

            all_jobs = orchestrator.list_jobs()
            assert len(all_jobs) == 2

            # Filter by status
            pending_jobs = orchestrator.list_jobs(ReembedJobStatus.PENDING)
            assert len(pending_jobs) == 2
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_cancel_job(self, orchestrator):
        """Test cancelling a job."""
        await orchestrator.start()
        try:
            job_id = await orchestrator.submit_job("test_ns", "old", "new")

            # Cancel pending job
            success = await orchestrator.cancel_job(job_id)
            assert success

            job = orchestrator.get_job_status(job_id)
            assert job.status == ReembedJobStatus.CANCELLED
            assert job.completed_at is not None

            # Try to cancel non-existent job
            success = await orchestrator.cancel_job("non-existent")
            assert not success
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_job_execution_simulation(self, orchestrator, monkeypatch):
        """Test job execution with mocked components."""
        await orchestrator.start()
        try:
            # Mock the internal methods to simulate processing
            async def mock_collect_items(job):
                await asyncio.sleep(0.2)  # Simulate some work
                job.total_items = 3
                return ["item1", "item2", "item3"]

            async def mock_process_batches(job):
                await asyncio.sleep(0.3)  # Simulate processing time
                job.processed_items = 3
                job.failed_items = 0

            monkeypatch.setattr(orchestrator, "_collect_namespace_items", mock_collect_items)
            monkeypatch.setattr(orchestrator, "_process_batches", mock_process_batches)

            job_id = await orchestrator.submit_job("test_ns", "old", "new")

            # Wait a bit for job to be picked up
            await asyncio.sleep(0.1)

            job = orchestrator.get_job_status(job_id)
            assert job.status == ReembedJobStatus.RUNNING

            # Wait for job to complete
            await asyncio.sleep(0.5)

            job = orchestrator.get_job_status(job_id)
            assert job.status == ReembedJobStatus.COMPLETED
            assert job.processed_items == 3
            assert job.failed_items == 0
        finally:
            await orchestrator.stop()

    def test_get_metrics(self, orchestrator):
        """Test getting orchestrator metrics."""
        metrics = orchestrator.get_metrics()

        assert "total_jobs" in metrics
        assert "completed_jobs" in metrics
        assert "failed_jobs" in metrics
        assert "running_jobs" in metrics
        assert "active_jobs" in metrics
        assert "queue_size" in metrics

        # Initially should be all zeros
        assert metrics["total_jobs"] == 0
        assert metrics["active_jobs"] == 0

    @pytest.mark.asyncio
    async def test_orchestrator_lifecycle(self, mock_vector_backend, mock_embedding_service):
        """Test starting and stopping the orchestrator."""
        orch = ReembedJobOrchestrator(mock_vector_backend, mock_embedding_service)

        # Should not be running initially
        assert not orch._running

        # Start orchestrator
        await orch.start()
        assert orch._running
        assert orch._task is not None

        # Stop orchestrator
        await orch.stop()
        assert not orch._running

    def test_global_orchestrator(self, mock_vector_backend, mock_embedding_service):
        """Test global orchestrator management."""
        # Initially should be None
        assert get_reembed_orchestrator() is None

        # Initialize
        orch = initialize_reembed_orchestrator(mock_vector_backend, mock_embedding_service)
        assert get_reembed_orchestrator() is orch

    def test_job_priority_enum(self):
        """Test job priority enum values."""
        assert ReembedJobPriority.LOW.value == "low"
        assert ReembedJobPriority.MEDIUM.value == "medium"
        assert ReembedJobPriority.HIGH.value == "high"
        assert ReembedJobPriority.CRITICAL.value == "critical"

    def test_job_status_enum(self):
        """Test job status enum values."""
        assert ReembedJobStatus.PENDING.value == "pending"
        assert ReembedJobStatus.RUNNING.value == "running"
        assert ReembedJobStatus.COMPLETED.value == "completed"
        assert ReembedJobStatus.FAILED.value == "failed"
        assert ReembedJobStatus.CANCELLED.value == "cancelled"

    @pytest.mark.asyncio
    async def test_concurrent_job_limit(self, orchestrator):
        """Test that concurrent job limit is respected."""
        await orchestrator.start()
        try:
            # Submit more jobs than the limit
            job_ids = []
            for i in range(5):  # More than max_concurrent_jobs (2)
                job_id = await orchestrator.submit_job(f"ns{i}", "old", "new")
                job_ids.append(job_id)

            # Wait for jobs to be processed
            await asyncio.sleep(0.2)

            # Check that not more than max_concurrent_jobs are active
            active_count = sum(1 for job in orchestrator.jobs.values() if job.status == ReembedJobStatus.RUNNING)
            assert active_count <= orchestrator.max_concurrent_jobs
        finally:
            await orchestrator.stop()
