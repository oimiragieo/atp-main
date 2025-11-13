"""Metrics integration for GAP-300: Vector Tier Production Backend."""

from typing import Optional

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes for when prometheus is not available
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass

    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def set(self, *args, **kwargs): pass

    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, *args, **kwargs): pass

from tools.vector_backend import VectorQueryMetrics


class VectorMetricsCollector:
    """Collects and exposes vector backend metrics."""

    def __init__(self, registry: Optional["CollectorRegistry"] = None):
        if PROMETHEUS_AVAILABLE:
            # Use a dedicated registry to avoid global duplicates across tests
            self._registry = registry or CollectorRegistry(auto_describe=True)
            # Query latency histogram
            self.vector_query_duration = Histogram(
                "vector_query_duration_seconds",
                "Duration of vector queries in seconds",
                ["operation", "namespace", "backend_type"],
                registry=self._registry,
            )

            # Query count counter
            self.vector_query_total = Counter(
                "vector_query_total", "Total number of vector queries", ["operation", "namespace", "backend_type"]
                , registry=self._registry
            )

            # Query errors counter
            self.vector_query_errors_total = Counter(
                "vector_query_errors_total",
                "Total number of vector query errors",
                ["operation", "namespace", "backend_type"],
                registry=self._registry,
            )

            # Active connections gauge
            self.vector_backend_connections_active = Gauge(
                "vector_backend_connections_active", "Number of active connections to vector backend", ["backend_type"]
                , registry=self._registry
            )

            # Namespace count gauge
            self.vector_namespaces_total = Gauge(
                "vector_namespaces_total", "Total number of namespaces in vector backend", ["backend_type"]
                , registry=self._registry
            )

            # Vectors per namespace gauge
            self.vector_count_per_namespace = Gauge(
                "vector_count_per_namespace", "Number of vectors in a namespace", ["namespace", "backend_type"]
                , registry=self._registry
            )
        else:
            # Create dummy attributes when prometheus is not available
            self.vector_query_duration = None
            self.vector_query_total = None
            self.vector_query_errors_total = None
            self.vector_backend_connections_active = None
            self.vector_namespaces_total = None
            self.vector_count_per_namespace = None

    def get_registry(self):
        """Return the underlying CollectorRegistry if available."""
        if not PROMETHEUS_AVAILABLE:
            return None
        return self._registry

    def record_metrics(self, metrics: VectorQueryMetrics, backend_type: str = "unknown") -> None:
        """Record metrics from a VectorQueryMetrics object."""
        if not PROMETHEUS_AVAILABLE:
            return

        labels = {"operation": metrics.operation, "namespace": metrics.namespace, "backend_type": backend_type}

        # Record duration
        self.vector_query_duration.labels(**labels).observe(metrics.duration_ms / 1000.0)

        # Record count
        self.vector_query_total.labels(**labels).inc()

        # Record errors if present
        if metrics.error:
            self.vector_query_errors_total.labels(**labels).inc()

    def update_connection_count(self, backend_type: str, count: int) -> None:
        """Update active connection count."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.vector_backend_connections_active.labels(backend_type=backend_type).set(count)

    def update_namespace_count(self, backend_type: str, count: int) -> None:
        """Update total namespace count."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.vector_namespaces_total.labels(backend_type=backend_type).set(count)

    def update_vector_count(self, namespace: str, backend_type: str, count: int) -> None:
        """Update vector count for a namespace."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.vector_count_per_namespace.labels(namespace=namespace, backend_type=backend_type).set(count)


# Global metrics collector instance
_metrics_collector: Optional[VectorMetricsCollector] = None


def get_metrics_collector(*, fresh: bool = False) -> VectorMetricsCollector:
    """Get or create the global metrics collector.

    Set fresh=True to create a new collector with a fresh registry (useful in tests).
    """
    global _metrics_collector
    if fresh or _metrics_collector is None:
        _metrics_collector = VectorMetricsCollector()
    return _metrics_collector


def create_prometheus_metrics_callback(backend_type: str = "unknown"):
    """Create a metrics callback function for vector backends."""
    collector = get_metrics_collector()

    def metrics_callback(metrics: VectorQueryMetrics) -> None:
        """Callback to record metrics with Prometheus."""
        collector.record_metrics(metrics, backend_type)

    return metrics_callback


def update_backend_stats(
    backend_type: str,
    active_connections: int = 0,
    namespace_count: int = 0,
    namespace_stats: Optional[dict[str, int]] = None,
) -> None:
    """Update backend statistics."""
    collector = get_metrics_collector()

    collector.update_connection_count(backend_type, active_connections)
    collector.update_namespace_count(backend_type, namespace_count)

    if namespace_stats:
        for namespace, count in namespace_stats.items():
            collector.update_vector_count(namespace, backend_type, count)


# Legacy alias for backward compatibility
prometheus_metrics_callback = create_prometheus_metrics_callback()


if __name__ == "__main__":
    # Demo metrics collection
    import asyncio

    from tools.vector_backend import VectorQueryMetrics

    async def demo_metrics():
        print("Vector Metrics Integration Demo")
        print("=" * 40)

        callback = create_prometheus_metrics_callback("memory")

        # Simulate some metrics
        metrics = [
            VectorQueryMetrics(operation="upsert", duration_ms=45.2, namespace="documents", result_count=1),
            VectorQueryMetrics(operation="query", duration_ms=12.8, namespace="documents", result_count=5),
            VectorQueryMetrics(operation="get", duration_ms=3.1, namespace="documents", result_count=1),
            VectorQueryMetrics(
                operation="query", duration_ms=25.6, namespace="embeddings", result_count=0, error="timeout"
            ),
        ]

        print("Recording sample metrics...")
        for metric in metrics:
            callback(metric)
            dur = metric.duration_ms
            err_suffix = f" (error: {metric.error})" if metric.error else ""
            print(f"  Recorded: {metric.operation} in {metric.namespace} {dur:.1f}ms{err_suffix}")

        # Update backend stats
        print("\nUpdating backend statistics...")
        update_backend_stats(
            backend_type="memory",
            active_connections=1,
            namespace_count=2,
            namespace_stats={"documents": 150, "embeddings": 75},
        )

        print("Metrics demo completed!")
        print("\nPrometheus metrics are now available at /metrics endpoint")

    asyncio.run(demo_metrics())
