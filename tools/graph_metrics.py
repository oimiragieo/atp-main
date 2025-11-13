#!/usr/bin/env python3
"""Graph metrics collection and Prometheus integration for GAP-301."""

import logging
from typing import Any

from tools.graph_backend import GraphQueryMetrics

logger = logging.getLogger(__name__)


class GraphMetricsCollector:
    """Collects and manages graph operation metrics."""

    def __init__(self):
        self.metrics_enabled = False
        self._initialize_prometheus()

    def _initialize_prometheus(self):
        """Initialize Prometheus metrics if available."""
        try:
            from prometheus_client import Counter, Gauge, Histogram

            self.graph_operation_duration = Histogram(
                "graph_operation_duration_seconds",
                "Duration of graph operations in seconds",
                ["operation", "backend_type"],
            )

            self.graph_nodes_total = Gauge("graph_nodes_total", "Total number of nodes in graph", ["backend_type"])

            self.graph_relationships_total = Gauge(
                "graph_relationships_total", "Total number of relationships in graph", ["backend_type"]
            )

            self.graph_paths_found_total = Counter(
                "graph_paths_found_total", "Total number of paths found in graph queries", ["backend_type"]
            )

            self.graph_operation_errors_total = Counter(
                "graph_operation_errors_total",
                "Total number of graph operation errors",
                ["operation", "backend_type", "error_type"],
            )

            self.graph_edges_total = Gauge(
                "graph_edges_total",
                "Total number of edges (relationships) in graph",
                ["backend_type", "relationship_type"],
            )

            self.metrics_enabled = True
            logger.info("Graph Prometheus metrics initialized")

        except ImportError:
            logger.warning("Prometheus client not available, metrics disabled")
            self.metrics_enabled = False

    def record_metrics(self, metrics: GraphQueryMetrics, backend_type: str = "memory"):
        """Record graph operation metrics."""
        if not self.metrics_enabled:
            return

        try:
            # Record operation duration
            self.graph_operation_duration.labels(operation=metrics.operation, backend_type=backend_type).observe(
                metrics.duration_ms / 1000
            )

            # Record counts
            if metrics.node_count > 0:
                self.graph_nodes_total.labels(backend_type=backend_type).set(metrics.node_count)

            if metrics.relationship_count > 0:
                self.graph_relationships_total.labels(backend_type=backend_type).set(metrics.relationship_count)
                # Also record as edges
                self.graph_edges_total.labels(backend_type=backend_type, relationship_type="total").set(
                    metrics.relationship_count
                )

            if metrics.path_count > 0:
                self.graph_paths_found_total.labels(backend_type=backend_type).inc(metrics.path_count)

            # Record errors
            if metrics.error:
                error_type = self._classify_error(metrics.error)
                self.graph_operation_errors_total.labels(
                    operation=metrics.operation, backend_type=backend_type, error_type=error_type
                ).inc()

        except Exception as e:
            logger.warning(f"Failed to record graph metrics: {e}")

    def _classify_error(self, error_msg: str) -> str:
        """Classify error type from error message."""
        error_lower = error_msg.lower()

        if "not found" in error_lower:
            return "not_found"
        elif "already exists" in error_lower:
            return "already_exists"
        elif "connection" in error_lower:
            return "connection"
        elif "timeout" in error_lower:
            return "timeout"
        elif "permission" in error_lower or "unauthorized" in error_lower:
            return "permission"
        else:
            return "unknown"

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get a summary of current metrics."""
        if not self.metrics_enabled:
            return {"status": "disabled", "reason": "prometheus_not_available"}

        try:
            return {
                "status": "enabled",
                "nodes_total": self.graph_nodes_total._value if hasattr(self.graph_nodes_total, "_value") else 0,
                "relationships_total": self.graph_relationships_total._value
                if hasattr(self.graph_relationships_total, "_value")
                else 0,
                "edges_total": self.graph_edges_total._value if hasattr(self.graph_edges_total, "_value") else 0,
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}


# Global metrics collector instance
_graph_metrics_collector = None


def get_graph_metrics_collector() -> GraphMetricsCollector:
    """Get the global graph metrics collector instance."""
    global _graph_metrics_collector
    if _graph_metrics_collector is None:
        _graph_metrics_collector = GraphMetricsCollector()
    return _graph_metrics_collector


def prometheus_graph_metrics_callback(metrics: GraphQueryMetrics) -> None:
    """Prometheus metrics callback for graph operations."""
    collector = get_graph_metrics_collector()
    collector.record_metrics(metrics)
