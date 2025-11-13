"""
GAP-309: Vector backfill & re-embedding pipeline.

This module provides job orchestration for re-embedding vectors when:
- Embedding model versions change
- Embedding dimensions change
- Data quality improvements require re-processing
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from metrics import (
    REEMBED_BATCHES_PROCESSED_TOTAL,
    REEMBED_ITEMS_REEMBEDDED_TOTAL,
    REEMBED_JOBS_ACTIVE,
    REEMBED_JOBS_COMPLETED_TOTAL,
    REEMBED_JOBS_FAILED_TOTAL,
    REEMBED_JOBS_QUEUED,
)

logger = logging.getLogger(__name__)


class ReembedJobStatus(Enum):
    """Status of a re-embedding job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReembedJobPriority(Enum):
    """Priority levels for re-embedding jobs."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ReembedJob:
    """A re-embedding job configuration."""

    job_id: str
    namespace: str
    source_model: str
    target_model: str
    priority: ReembedJobPriority
    status: ReembedJobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ReembedBatch:
    """A batch of items to be re-embedded."""

    batch_id: str
    job_id: str
    items: list[dict[str, Any]]
    status: str = "pending"


class ReembedJobOrchestrator:
    """Orchestrates re-embedding jobs across vector backends."""

    def __init__(self, vector_backend, embedding_service=None, max_concurrent_jobs: int = 3, batch_size: int = 100):
        self.vector_backend = vector_backend
        self.embedding_service = embedding_service
        self.max_concurrent_jobs = max_concurrent_jobs
        self.batch_size = batch_size
        self.jobs: dict[str, ReembedJob] = {}
        self.active_jobs: set[str] = set()
        self.job_queue: asyncio.Queue[ReembedJob] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the job orchestrator."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_jobs())
        logger.info("Re-embedding job orchestrator started")

    async def stop(self):
        """Stop the job orchestrator."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Re-embedding job orchestrator stopped")

    async def submit_job(
        self,
        namespace: str,
        source_model: str,
        target_model: str,
        priority: ReembedJobPriority = ReembedJobPriority.MEDIUM,
    ) -> str:
        """Submit a new re-embedding job."""
        job_id = str(uuid4())
        job = ReembedJob(
            job_id=job_id,
            namespace=namespace,
            source_model=source_model,
            target_model=target_model,
            priority=priority,
            status=ReembedJobStatus.PENDING,
            created_at=datetime.now(),
        )

        self.jobs[job_id] = job
        await self.job_queue.put(job)
        REEMBED_JOBS_QUEUED.inc(1)

        logger.info(f"Submitted re-embedding job {job_id} for namespace {namespace}: {source_model} -> {target_model}")
        return job_id

    def get_job_status(self, job_id: str) -> ReembedJob | None:
        """Get the status of a job."""
        return self.jobs.get(job_id)

    def list_jobs(self, status_filter: ReembedJobStatus | None = None) -> list[ReembedJob]:
        """List all jobs, optionally filtered by status."""
        jobs = list(self.jobs.values())
        if status_filter:
            jobs = [job for job in jobs if job.status == status_filter]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status in [ReembedJobStatus.PENDING, ReembedJobStatus.RUNNING]:
            job.status = ReembedJobStatus.CANCELLED
            job.completed_at = datetime.now()
            if job.status == ReembedJobStatus.PENDING:
                REEMBED_JOBS_QUEUED.dec(1)
            elif job.status == ReembedJobStatus.RUNNING:
                REEMBED_JOBS_ACTIVE.dec(1)
            logger.info(f"Cancelled re-embedding job {job_id}")
            return True

        return False

    async def _process_jobs(self):
        """Main job processing loop."""
        while self._running:
            try:
                # Wait for a job if we haven't reached the concurrency limit
                if len(self.active_jobs) < self.max_concurrent_jobs:
                    try:
                        job = self.job_queue.get_nowait()
                        self.active_jobs.add(job.job_id)
                        asyncio.create_task(self._execute_job(job))
                    except asyncio.QueueEmpty:
                        pass

                await asyncio.sleep(1)  # Prevent busy waiting

            except Exception as e:
                logger.error(f"Error in job processing loop: {e}")

    async def _execute_job(self, job: ReembedJob):
        """Execute a single re-embedding job."""
        try:
            job.status = ReembedJobStatus.RUNNING
            job.started_at = datetime.now()
            REEMBED_JOBS_ACTIVE.inc(1)
            REEMBED_JOBS_QUEUED.dec(1)
            logger.info(f"Starting re-embedding job {job.job_id}")

            # Get all items in the namespace
            await self._collect_namespace_items(job)

            # Process items in batches
            await self._process_batches(job)

            job.status = ReembedJobStatus.COMPLETED
            job.completed_at = datetime.now()
            REEMBED_JOBS_COMPLETED_TOTAL.inc(1)
            REEMBED_JOBS_ACTIVE.dec(1)
            REEMBED_ITEMS_REEMBEDDED_TOTAL.inc(job.processed_items)
            logger.info(f"Completed re-embedding job {job.job_id}: {job.processed_items}/{job.total_items} items")

        except Exception as e:
            job.status = ReembedJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now()
            REEMBED_JOBS_FAILED_TOTAL.inc(1)
            REEMBED_JOBS_ACTIVE.dec(1)
            logger.error(f"Failed re-embedding job {job.job_id}: {e}")

        finally:
            self.active_jobs.discard(job.job_id)

    async def _collect_namespace_items(self, job: ReembedJob):
        """Collect all items in the namespace that need re-embedding."""
        # This is a simplified implementation
        # In a real system, you'd query the vector backend for all items
        # For now, we'll simulate by setting total_items
        job.total_items = 1000  # Placeholder
        logger.info(f"Collected {job.total_items} items for re-embedding in namespace {job.namespace}")

    async def _process_batches(self, job: ReembedJob):
        """Process items in batches."""
        # Create batches
        batches = []
        for i in range(0, job.total_items, self.batch_size):
            batch = ReembedBatch(
                batch_id=f"{job.job_id}_batch_{i // self.batch_size}",
                job_id=job.job_id,
                items=[],  # In real implementation, populate with actual items
            )
            batches.append(batch)

        # Process batches concurrently
        semaphore = asyncio.Semaphore(5)  # Limit concurrent batches

        async def process_batch(batch: ReembedBatch):
            async with semaphore:
                await self._reembed_batch(job, batch)

        tasks = [process_batch(batch) for batch in batches]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _reembed_batch(self, job: ReembedJob, batch: ReembedBatch):
        """Re-embed a single batch of items."""
        try:
            batch.status = "running"

            # Simulate re-embedding work
            for _item in batch.items:
                # In real implementation:
                # 1. Get original text/data from item
                # 2. Generate new embedding using target_model
                # 3. Update vector in backend
                # 4. Update metadata with new model version
                await asyncio.sleep(0.01)  # Simulate work
                job.processed_items += 1

            batch.status = "completed"
            REEMBED_BATCHES_PROCESSED_TOTAL.inc(1)
            logger.debug(f"Completed batch {batch.batch_id}")

        except Exception as e:
            batch.status = "failed"
            job.failed_items += len(batch.items)
            logger.error(f"Failed batch {batch.batch_id}: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get orchestrator metrics."""
        total_jobs = len(self.jobs)
        completed_jobs = sum(1 for job in self.jobs.values() if job.status == ReembedJobStatus.COMPLETED)
        failed_jobs = sum(1 for job in self.jobs.values() if job.status == ReembedJobStatus.FAILED)
        running_jobs = sum(1 for job in self.jobs.values() if job.status == ReembedJobStatus.RUNNING)

        return {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "running_jobs": running_jobs,
            "active_jobs": len(self.active_jobs),
            "queue_size": self.job_queue.qsize(),
        }


# Global orchestrator instance
_orchestrator: ReembedJobOrchestrator | None = None


def get_reembed_orchestrator() -> ReembedJobOrchestrator | None:
    """Get the global re-embedding orchestrator instance."""
    return _orchestrator


def initialize_reembed_orchestrator(vector_backend, embedding_service=None, **kwargs):
    """Initialize the global re-embedding orchestrator."""
    global _orchestrator
    _orchestrator = ReembedJobOrchestrator(vector_backend, embedding_service, **kwargs)
    return _orchestrator
