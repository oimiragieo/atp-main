#!/usr/bin/env python3
"""GAP-303: Row-level encryption metrics integration.

Prometheus metrics for row-level encryption operations.
"""

import time
from typing import Optional

try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def row_encryption_metrics_callback(
    operation: str, duration_ms: float, success: bool, tenant_id: str, row_count: int = 1, error_type: str = ""
) -> None:
    """Prometheus metrics callback for row encryption operations.

    Args:
        operation: The operation performed (encrypt, decrypt, rotate_keys, etc.)
        duration_ms: Operation duration in milliseconds
        success: Whether the operation succeeded
        tenant_id: The tenant performing the operation
        row_count: Number of rows affected (for bulk operations)
        error_type: Type of error if operation failed
    """
    if not PROMETHEUS_AVAILABLE:
        return

    # Define metrics if not already defined
    row_encryption_duration = Histogram(
        "row_encryption_operation_duration_seconds", "Duration of row encryption operations", ["operation", "tenant_id"]
    )

    row_encryption_operations_total = Counter(
        "row_encryption_operations_total",
        "Total number of row encryption operations",
        ["operation", "tenant_id", "status", "error_type"],
    )

    row_encryption_rows_processed_total = Counter(
        "row_encryption_rows_processed_total",
        "Total number of rows processed by encryption operations",
        ["operation", "tenant_id"],
    )

    # Record metrics
    duration_seconds = duration_ms / 1000.0

    row_encryption_duration.labels(operation=operation, tenant_id=tenant_id).observe(duration_seconds)

    status = "success" if success else "failure"
    row_encryption_operations_total.labels(
        operation=operation, tenant_id=tenant_id, status=status, error_type=error_type
    ).inc()

    if success:
        row_encryption_rows_processed_total.labels(operation=operation, tenant_id=tenant_id).inc(row_count)


class RowEncryptionMetricsCollector:
    """Collector for row encryption metrics."""

    def __init__(self):
        self.operations: list[dict] = []

    def record_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool,
        tenant_id: str,
        row_count: int = 1,
        error_type: str = "",
    ) -> None:
        """Record an encryption operation for metrics."""
        self.operations.append(
            {
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
                "tenant_id": tenant_id,
                "row_count": row_count,
                "error_type": error_type,
                "timestamp": time.time(),
            }
        )

        # Send to Prometheus callback
        row_encryption_metrics_callback(operation, duration_ms, success, tenant_id, row_count, error_type)

    def get_operation_stats(self, tenant_id: Optional[str] = None) -> dict:
        """Get statistics for recorded operations."""
        operations = self.operations
        if tenant_id:
            operations = [op for op in operations if op["tenant_id"] == tenant_id]

        if not operations:
            return {"total_operations": 0}

        total_ops = len(operations)
        successful_ops = len([op for op in operations if op["success"]])
        failed_ops = total_ops - successful_ops

        avg_duration = sum(op["duration_ms"] for op in operations) / total_ops
        total_rows = sum(op["row_count"] for op in operations)

        return {
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "failed_operations": failed_ops,
            "success_rate": successful_ops / total_ops if total_ops > 0 else 0,
            "average_duration_ms": avg_duration,
            "total_rows_processed": total_rows,
        }


# Global metrics collector instance
_row_encryption_metrics_collector = RowEncryptionMetricsCollector()


def get_row_encryption_metrics_collector() -> RowEncryptionMetricsCollector:
    """Get the global row encryption metrics collector."""
    return _row_encryption_metrics_collector
