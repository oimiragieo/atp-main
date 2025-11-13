#!/usr/bin/env python3
"""GAP-302: Artifact Storage Metrics Integration.

Provides Prometheus metrics for artifact storage operations:
- Upload/download operation counters and histograms
- Storage size and artifact count gauges
- Error rate tracking
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def artifact_storage_metrics_callback(
    operation: str, duration_ms: float, success: bool, size_bytes: int = 0, error_type: str = ""
) -> None:
    """Prometheus metrics callback for artifact storage operations."""
    try:
        from prometheus_client import Counter, Gauge, Histogram

        # Define metrics if not already defined
        artifact_operation_duration = Histogram(
            "artifact_operation_duration_seconds", "Duration of artifact storage operations", ["operation"]
        )
        artifact_operations_total = Counter(
            "artifact_operations_total", "Total number of artifact storage operations", ["operation", "status"]
        )
        artifact_bytes_stored_total = Gauge("artifact_bytes_stored_total", "Total bytes stored in artifact storage")
        artifact_operation_errors_total = Counter(
            "artifact_operation_errors_total",
            "Total number of artifact storage operation errors",
            ["operation", "error_type"],
        )

        # Record metrics
        artifact_operation_duration.labels(operation=operation).observe(duration_ms / 1000)

        status = "success" if success else "failure"
        artifact_operations_total.labels(operation=operation, status=status).inc()

        if success and operation in ["upload", "store"]:
            artifact_bytes_stored_total.inc(size_bytes)

        if not success and error_type:
            artifact_operation_errors_total.labels(operation=operation, error_type=error_type).inc()

    except ImportError:
        # Prometheus not available, skip metrics
        pass


class ArtifactStorageMetricsCollector:
    """Collector for artifact storage metrics."""

    def __init__(self):
        self.operations = []
        self.total_bytes = 0
        self.artifact_count = 0

    def record_operation(
        self, operation: str, duration_ms: float, success: bool, size_bytes: int = 0, error_type: str = ""
    ) -> None:
        """Record an artifact storage operation."""
        self.operations.append(
            {
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
                "size_bytes": size_bytes,
                "error_type": error_type,
                "timestamp": __import__("time").time(),
            }
        )

        if success:
            if operation in ["upload", "store"]:
                self.total_bytes += size_bytes
                self.artifact_count += 1
            elif operation == "delete":
                self.artifact_count = max(0, self.artifact_count - 1)

        # Call metrics callback
        artifact_storage_metrics_callback(operation, duration_ms, success, size_bytes, error_type)

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        successful_ops = [op for op in self.operations if op["success"]]
        failed_ops = [op for op in self.operations if not op["success"]]

        return {
            "total_operations": len(self.operations),
            "successful_operations": len(successful_ops),
            "failed_operations": len(failed_ops),
            "total_bytes_stored": self.total_bytes,
            "artifact_count": self.artifact_count,
            "success_rate": len(successful_ops) / len(self.operations) if self.operations else 0,
            "average_duration_ms": sum(op["duration_ms"] for op in self.operations) / len(self.operations)
            if self.operations
            else 0,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.operations.clear()
        self.total_bytes = 0
        self.artifact_count = 0


# Global metrics collector instance
artifact_metrics_collector = ArtifactStorageMetricsCollector()


def get_artifact_metrics_collector() -> ArtifactStorageMetricsCollector:
    """Get the global artifact metrics collector."""
    return artifact_metrics_collector
