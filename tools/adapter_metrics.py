#!/usr/bin/env python3
"""Adapter Certification Metrics and Monitoring."""

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

# Optional prometheus import
try:
    import prometheus_client as prom
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    print("Warning: prometheus_client not available. Prometheus metrics disabled.")


@dataclass
class AdapterMetrics:
    """Metrics for a single adapter."""

    name: str
    certification_level: int
    last_certification_time: float
    certification_score: float
    total_requests: int
    error_requests: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    uptime_seconds: float
    last_health_check: float
    health_status: bool


class CertificationMetricsCollector:
    """Collects and exposes adapter certification metrics."""

    def __init__(self):
        # Prometheus metrics (if available)
        if PROMETHEUS_AVAILABLE:
            self.certified_adapters_total = Gauge(
                "certified_adapters_total", "Total number of certified adapters by level", ["level"]
            )

            self.adapter_certification_score = Gauge(
                "adapter_certification_score", "Current certification score for adapter", ["adapter_name"]
            )

            self.adapter_health_status = Gauge(
                "adapter_health_status", "Current health status of adapter (1=healthy, 0=unhealthy)", ["adapter_name"]
            )

            self.adapter_response_time = Histogram(
                "adapter_response_time_seconds",
                "Response time for adapter requests",
                ["adapter_name", "method"],
                buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            )

            self.adapter_requests_total = Counter(
                "adapter_requests_total", "Total number of requests to adapter", ["adapter_name", "method", "status"]
            )

            self.adapter_uptime_seconds = Gauge("adapter_uptime_seconds", "Adapter uptime in seconds", ["adapter_name"])

            self.certification_tests_total = Counter(
                "certification_tests_total", "Total number of certification tests run", ["adapter_name", "result"]
            )
        else:
            # Initialize as None if Prometheus not available
            self.certified_adapters_total = None
            self.adapter_certification_score = None
            self.adapter_health_status = None
            self.adapter_response_time = None
            self.adapter_requests_total = None
            self.adapter_uptime_seconds = None
            self.certification_tests_total = None

        # In-memory storage
        self.adapters: dict[str, AdapterMetrics] = {}
        self.certification_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # Use a simple lock that works in async contexts
        self._lock = None  # threading.Lock() - disabled for async compatibility

    def register_adapter(self, adapter_name: str):
        """Register a new adapter for monitoring."""
        if self._lock:
            with self._lock:
                self._register_adapter_impl(adapter_name)
        else:
            self._register_adapter_impl(adapter_name)

    def _register_adapter_impl(self, adapter_name: str):
        """Internal implementation of adapter registration."""
        if adapter_name not in self.adapters:
            self.adapters[adapter_name] = AdapterMetrics(
                name=adapter_name,
                certification_level=0,
                last_certification_time=0,
                certification_score=0.0,
                total_requests=0,
                error_requests=0,
                avg_response_time_ms=0.0,
                p95_response_time_ms=0.0,
                uptime_seconds=0.0,
                last_health_check=0,
                health_status=False,
            )

    def update_certification_result(self, adapter_name: str, level: int, score: float):
        """Update adapter certification status."""
        if self._lock:
            with self._lock:
                self._update_certification_result_impl(adapter_name, level, score)
        else:
            self._update_certification_result_impl(adapter_name, level, score)

    def _update_certification_result_impl(self, adapter_name: str, level: int, score: float):
        """Internal implementation of certification result update."""
        if adapter_name not in self.adapters:
            self.register_adapter(adapter_name)

        adapter = self.adapters[adapter_name]
        adapter.certification_level = level
        adapter.certification_score = score
        adapter.last_certification_time = time.time()

        # Update Prometheus metrics
        if PROMETHEUS_AVAILABLE and self.adapter_certification_score:
            self.adapter_certification_score.labels(adapter_name=adapter_name).set(score)

        # Record certification test
        if PROMETHEUS_AVAILABLE and self.certification_tests_total:
            self.certification_tests_total.labels(
                adapter_name=adapter_name, result="passed" if level > 0 else "failed"
            ).inc()

        # Store history
        self.certification_history[adapter_name].append(
            {"timestamp": adapter.last_certification_time, "level": level, "score": score}
        )

        # Keep only last 10 certification results
        if len(self.certification_history[adapter_name]) > 10:
            self.certification_history[adapter_name] = self.certification_history[adapter_name][-10:]

    def update_health_status(self, adapter_name: str, healthy: bool):
        """Update adapter health status."""
        if self._lock:
            with self._lock:
                self._update_health_status_impl(adapter_name, healthy)
        else:
            self._update_health_status_impl(adapter_name, healthy)

    def _update_health_status_impl(self, adapter_name: str, healthy: bool):
        """Internal implementation of health status update."""
        if adapter_name not in self.adapters:
            self.register_adapter(adapter_name)

        adapter = self.adapters[adapter_name]
        adapter.health_status = healthy
        adapter.last_health_check = time.time()

        if PROMETHEUS_AVAILABLE and self.adapter_health_status:
            self.adapter_health_status.labels(adapter_name=adapter_name).set(1 if healthy else 0)

    def record_request(self, adapter_name: str, method: str, response_time: float, success: bool):
        """Record a request to an adapter."""
        if self._lock:
            with self._lock:
                self._record_request_impl(adapter_name, method, response_time, success)
        else:
            self._record_request_impl(adapter_name, method, response_time, success)

    def _record_request_impl(self, adapter_name: str, method: str, response_time: float, success: bool):
        """Internal implementation of request recording."""
        if adapter_name not in self.adapters:
            self.register_adapter(adapter_name)

        adapter = self.adapters[adapter_name]
        adapter.total_requests += 1
        if not success:
            adapter.error_requests += 1

        # Update response time metrics
        if PROMETHEUS_AVAILABLE and self.adapter_response_time:
            self.adapter_response_time.labels(adapter_name=adapter_name, method=method).observe(response_time)

        if PROMETHEUS_AVAILABLE and self.adapter_requests_total:
            self.adapter_requests_total.labels(
                adapter_name=adapter_name, method=method, status="success" if success else "error"
            ).inc()

    def update_uptime(self, adapter_name: str, uptime_seconds: float):
        """Update adapter uptime."""
        if self._lock:
            with self._lock:
                self._update_uptime_impl(adapter_name, uptime_seconds)
        else:
            self._update_uptime_impl(adapter_name, uptime_seconds)

    def _update_uptime_impl(self, adapter_name: str, uptime_seconds: float):
        """Internal implementation of uptime update."""
        if adapter_name not in self.adapters:
            self.register_adapter(adapter_name)

        self.adapters[adapter_name].uptime_seconds = uptime_seconds
        if PROMETHEUS_AVAILABLE and self.adapter_uptime_seconds:
            self.adapter_uptime_seconds.labels(adapter_name=adapter_name).set(uptime_seconds)

    def get_adapter_status(self, adapter_name: str) -> AdapterMetrics | None:
        """Get current status of an adapter."""
        if self._lock:
            with self._lock:
                return self.adapters.get(adapter_name)
        else:
            return self.adapters.get(adapter_name)

    def get_all_adapters_status(self) -> dict[str, AdapterMetrics]:
        """Get status of all adapters."""
        if self._lock:
            with self._lock:
                return self.adapters.copy()
        else:
            return self.adapters.copy()

    def get_certification_history(self, adapter_name: str) -> list[dict[str, Any]]:
        """Get certification history for an adapter."""
        if self._lock:
            with self._lock:
                return self.certification_history[adapter_name].copy()
        else:
            return self.certification_history[adapter_name].copy()

    def update_prometheus_metrics(self):
        """Update Prometheus metrics based on current adapter states."""
        if self._lock:
            with self._lock:
                self._update_prometheus_metrics_impl()
        else:
            self._update_prometheus_metrics_impl()

    def _update_prometheus_metrics_impl(self):
        """Internal implementation of Prometheus metrics update."""
        # Count certified adapters by level
        level_counts = defaultdict(int)
        for adapter in self.adapters.values():
            level_counts[adapter.certification_level] += 1

        if PROMETHEUS_AVAILABLE and self.certified_adapters_total:
            for level in range(4):  # Levels 0-3
                self.certified_adapters_total.labels(level=str(level)).set(level_counts[level])

    def export_metrics_json(self) -> str:
        """Export all metrics as JSON for external monitoring."""
        if self._lock:
            with self._lock:
                return self._export_metrics_json_impl()
        else:
            return self._export_metrics_json_impl()

    def _export_metrics_json_impl(self) -> str:
        """Internal implementation of metrics JSON export."""
        data = {
            "adapters": {name: asdict(metrics) for name, metrics in self.adapters.items()},
            "certification_history": dict(self.certification_history),
            "timestamp": time.time(),
        }
        return json.dumps(data, indent=2)

    def save_metrics_to_file(self, filepath: str):
        """Save current metrics to a JSON file."""
        with open(filepath, "w") as f:
            f.write(self.export_metrics_json())


# Global metrics collector instance
metrics_collector = CertificationMetricsCollector()


def get_metrics_collector() -> CertificationMetricsCollector:
    """Get the global metrics collector instance."""
    return metrics_collector


def start_metrics_server(port: int = 8000):
    """Start Prometheus metrics HTTP server."""
    if PROMETHEUS_AVAILABLE:
        prom.start_http_server(port)
        print(f"Metrics server started on port {port}")
    else:
        print("Prometheus not available, metrics server not started")


if __name__ == "__main__":
    # Example usage
    collector = get_metrics_collector()

    # Register some adapters
    collector.register_adapter("ollama_adapter")
    collector.register_adapter("persona_adapter")

    # Simulate certification results
    collector.update_certification_result("ollama_adapter", 1, 85.5)
    collector.update_certification_result("persona_adapter", 2, 92.3)

    # Update health status
    collector.update_health_status("ollama_adapter", True)
    collector.update_health_status("persona_adapter", True)

    # Record some requests
    collector.record_request("ollama_adapter", "estimate", 0.15, True)
    collector.record_request("ollama_adapter", "stream", 2.3, True)
    collector.record_request("persona_adapter", "estimate", 0.12, True)

    # Update uptime
    collector.update_uptime("ollama_adapter", 3600)
    collector.update_uptime("persona_adapter", 7200)

    # Update Prometheus metrics
    collector.update_prometheus_metrics()

    # Export metrics
    print("Current Metrics:")
    print(collector.export_metrics_json())

    # Save to file
    collector.save_metrics_to_file("adapter_metrics.json")
    print("Metrics saved to adapter_metrics.json")
