# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Performance Analysis Tools
Advanced performance analysis and bottleneck detection using distributed traces.
"""

import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BottleneckType(Enum):
    """Types of performance bottlenecks."""

    CPU_BOUND = "cpu_bound"
    IO_BOUND = "io_bound"
    NETWORK_BOUND = "network_bound"
    DATABASE_BOUND = "database_bound"
    EXTERNAL_API = "external_api"
    MEMORY_BOUND = "memory_bound"
    CONCURRENCY_LIMIT = "concurrency_limit"


class PerformanceIssue(Enum):
    """Types of performance issues."""

    HIGH_LATENCY = "high_latency"
    HIGH_ERROR_RATE = "high_error_rate"
    RESOURCE_CONTENTION = "resource_contention"
    INEFFICIENT_QUERY = "inefficient_query"
    MEMORY_LEAK = "memory_leak"
    THREAD_POOL_EXHAUSTION = "thread_pool_exhaustion"


@dataclass
class PerformanceBottleneck:
    """Performance bottleneck information."""

    type: BottleneckType
    operation: str
    service: str
    severity: str  # "low", "medium", "high", "critical"
    impact_score: float  # 0-100
    avg_duration_ms: float
    p95_duration_ms: float
    frequency: int
    description: str
    recommendations: list[str]
    detected_at: float

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["type"] = self.type.value
        return result


@dataclass
class ServiceDependency:
    """Service dependency information."""

    from_service: str
    to_service: str
    operation: str
    call_count: int
    avg_latency_ms: float
    error_rate: float
    last_seen: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CriticalPath:
    """Critical path analysis result."""

    path_id: str
    operations: list[str]
    total_duration_ms: float
    critical_operations: list[str]
    bottleneck_operations: list[str]
    optimization_potential_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PerformanceAnalyzer:
    """Advanced performance analyzer for distributed systems."""

    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.trace_data: deque = deque(maxlen=10000)  # Recent traces
        self.operation_stats: dict[str, dict[str, Any]] = defaultdict(dict)
        self.service_dependencies: dict[str, ServiceDependency] = {}
        self.detected_bottlenecks: list[PerformanceBottleneck] = []
        self.performance_baselines: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

        # Analysis configuration
        self.latency_thresholds = {
            "low": 100,  # ms
            "medium": 500,  # ms
            "high": 2000,  # ms
            "critical": 10000,  # ms
        }

        self.error_rate_thresholds = {
            "low": 0.01,  # 1%
            "medium": 0.05,  # 5%
            "high": 0.1,  # 10%
            "critical": 0.2,  # 20%
        }

    def ingest_trace_data(self, trace_data: dict[str, Any]):
        """Ingest trace data for analysis."""
        with self._lock:
            # Add timestamp if not present
            if "timestamp" not in trace_data:
                trace_data["timestamp"] = time.time()

            self.trace_data.append(trace_data)

            # Update operation statistics
            self._update_operation_stats(trace_data)

            # Update service dependencies
            self._update_service_dependencies(trace_data)

    def _update_operation_stats(self, trace_data: dict[str, Any]):
        """Update operation statistics."""
        operation = trace_data.get("operation_name", "unknown")
        service = trace_data.get("service_name", "unknown")
        duration_ms = trace_data.get("duration_ms", 0)
        status = trace_data.get("status", "ok")

        key = f"{service}:{operation}"

        if key not in self.operation_stats:
            self.operation_stats[key] = {
                "service": service,
                "operation": operation,
                "call_count": 0,
                "total_duration_ms": 0,
                "durations": deque(maxlen=1000),
                "error_count": 0,
                "last_seen": 0,
            }

        stats = self.operation_stats[key]
        stats["call_count"] += 1
        stats["total_duration_ms"] += duration_ms
        stats["durations"].append(duration_ms)
        stats["last_seen"] = trace_data["timestamp"]

        if status == "error":
            stats["error_count"] += 1

    def _update_service_dependencies(self, trace_data: dict[str, Any]):
        """Update service dependency graph."""
        spans = trace_data.get("spans", [])

        for i, span in enumerate(spans):
            if i == 0:  # Skip root span
                continue

            parent_span = spans[i - 1]  # Simplified parent detection

            from_service = parent_span.get("service_name", "unknown")
            to_service = span.get("service_name", "unknown")
            operation = span.get("operation_name", "unknown")

            if from_service == to_service:
                continue  # Skip internal calls

            key = f"{from_service}->{to_service}:{operation}"

            if key not in self.service_dependencies:
                self.service_dependencies[key] = ServiceDependency(
                    from_service=from_service,
                    to_service=to_service,
                    operation=operation,
                    call_count=0,
                    avg_latency_ms=0,
                    error_rate=0,
                    last_seen=0,
                )

            dep = self.service_dependencies[key]
            dep.call_count += 1
            dep.last_seen = trace_data["timestamp"]

            # Update latency (simplified)
            duration_ms = span.get("duration_ms", 0)
            dep.avg_latency_ms = (dep.avg_latency_ms * (dep.call_count - 1) + duration_ms) / dep.call_count

    def detect_bottlenecks(self) -> list[PerformanceBottleneck]:
        """Detect performance bottlenecks."""
        bottlenecks = []
        current_time = time.time()

        with self._lock:
            for _key, stats in self.operation_stats.items():
                if not stats["durations"]:
                    continue

                service = stats["service"]
                operation = stats["operation"]
                durations = list(stats["durations"])

                # Calculate metrics
                avg_duration = statistics.mean(durations)
                p95_duration = self._percentile(durations, 95)
                error_rate = stats["error_count"] / stats["call_count"]

                # Detect high latency bottlenecks
                if avg_duration > self.latency_thresholds["high"]:
                    severity = self._get_latency_severity(avg_duration)
                    impact_score = min(100, (avg_duration / 1000) * stats["call_count"] / 100)

                    bottleneck = PerformanceBottleneck(
                        type=self._classify_bottleneck_type(operation, avg_duration),
                        operation=operation,
                        service=service,
                        severity=severity,
                        impact_score=impact_score,
                        avg_duration_ms=avg_duration,
                        p95_duration_ms=p95_duration,
                        frequency=stats["call_count"],
                        description=f"High latency detected in {operation} (avg: {avg_duration:.1f}ms)",
                        recommendations=self._get_latency_recommendations(operation, avg_duration),
                        detected_at=current_time,
                    )
                    bottlenecks.append(bottleneck)

                # Detect high error rate bottlenecks
                if error_rate > self.error_rate_thresholds["medium"]:
                    severity = self._get_error_rate_severity(error_rate)
                    impact_score = min(100, error_rate * 100 * stats["call_count"] / 1000)

                    bottleneck = PerformanceBottleneck(
                        type=BottleneckType.EXTERNAL_API,  # Simplified classification
                        operation=operation,
                        service=service,
                        severity=severity,
                        impact_score=impact_score,
                        avg_duration_ms=avg_duration,
                        p95_duration_ms=p95_duration,
                        frequency=stats["call_count"],
                        description=f"High error rate detected in {operation} ({error_rate:.1%})",
                        recommendations=self._get_error_rate_recommendations(operation, error_rate),
                        detected_at=current_time,
                    )
                    bottlenecks.append(bottleneck)

        # Update detected bottlenecks
        self.detected_bottlenecks = bottlenecks
        return bottlenecks

    def _percentile(self, data: list[float], percentile: int) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0

        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def _get_latency_severity(self, avg_duration: float) -> str:
        """Get severity level for latency."""
        if avg_duration > self.latency_thresholds["critical"]:
            return "critical"
        elif avg_duration > self.latency_thresholds["high"]:
            return "high"
        elif avg_duration > self.latency_thresholds["medium"]:
            return "medium"
        else:
            return "low"

    def _get_error_rate_severity(self, error_rate: float) -> str:
        """Get severity level for error rate."""
        if error_rate > self.error_rate_thresholds["critical"]:
            return "critical"
        elif error_rate > self.error_rate_thresholds["high"]:
            return "high"
        elif error_rate > self.error_rate_thresholds["medium"]:
            return "medium"
        else:
            return "low"

    def _classify_bottleneck_type(self, operation: str, duration: float) -> BottleneckType:
        """Classify bottleneck type based on operation and duration."""
        operation_lower = operation.lower()

        if "database" in operation_lower or "sql" in operation_lower or "query" in operation_lower:
            return BottleneckType.DATABASE_BOUND
        elif "http" in operation_lower or "api" in operation_lower or "request" in operation_lower:
            return BottleneckType.NETWORK_BOUND
        elif "file" in operation_lower or "disk" in operation_lower or "io" in operation_lower:
            return BottleneckType.IO_BOUND
        elif duration > 5000:  # Very high duration suggests external dependency
            return BottleneckType.EXTERNAL_API
        else:
            return BottleneckType.CPU_BOUND

    def _get_latency_recommendations(self, operation: str, duration: float) -> list[str]:
        """Get recommendations for latency issues."""
        recommendations = []

        if "database" in operation.lower():
            recommendations.extend(
                [
                    "Add database indexes for frequently queried columns",
                    "Consider query optimization or caching",
                    "Review database connection pool settings",
                    "Consider read replicas for read-heavy operations",
                ]
            )
        elif "http" in operation.lower() or "api" in operation.lower():
            recommendations.extend(
                [
                    "Implement request caching where appropriate",
                    "Consider connection pooling and keep-alive",
                    "Add circuit breakers for external dependencies",
                    "Implement request timeout and retry logic",
                ]
            )
        elif duration > 10000:
            recommendations.extend(
                [
                    "Consider breaking down the operation into smaller chunks",
                    "Implement asynchronous processing where possible",
                    "Add progress tracking for long-running operations",
                    "Consider background job processing",
                ]
            )
        else:
            recommendations.extend(
                [
                    "Profile the operation to identify CPU hotspots",
                    "Consider algorithmic optimizations",
                    "Review memory usage patterns",
                    "Consider parallel processing where applicable",
                ]
            )

        return recommendations

    def _get_error_rate_recommendations(self, operation: str, error_rate: float) -> list[str]:
        """Get recommendations for error rate issues."""
        recommendations = [
            "Review error logs to identify root causes",
            "Implement proper error handling and retries",
            "Add monitoring and alerting for error spikes",
            "Consider circuit breaker patterns for external dependencies",
        ]

        if error_rate > 0.1:  # Very high error rate
            recommendations.extend(
                [
                    "Consider rolling back recent changes",
                    "Implement graceful degradation",
                    "Add health checks and automatic failover",
                ]
            )

        return recommendations

    def analyze_critical_path(self, trace_id: str) -> CriticalPath | None:
        """Analyze critical path for a specific trace."""
        # Find trace data
        trace_data = None
        with self._lock:
            for trace in self.trace_data:
                if trace.get("trace_id") == trace_id:
                    trace_data = trace
                    break

        if not trace_data:
            return None

        spans = trace_data.get("spans", [])
        if not spans:
            return None

        # Build operation sequence
        operations = []
        total_duration = 0
        operation_durations = {}

        for span in spans:
            operation = span.get("operation_name", "unknown")
            duration = span.get("duration_ms", 0)

            operations.append(operation)
            operation_durations[operation] = duration
            total_duration += duration

        # Identify critical operations (top 20% by duration)
        sorted_ops = sorted(operation_durations.items(), key=lambda x: x[1], reverse=True)
        critical_count = max(1, len(sorted_ops) // 5)
        critical_operations = [op for op, _ in sorted_ops[:critical_count]]

        # Identify bottleneck operations (above threshold)
        bottleneck_operations = [
            op for op, duration in operation_durations.items() if duration > self.latency_thresholds["medium"]
        ]

        # Calculate optimization potential
        optimization_potential = sum(
            duration - self.latency_thresholds["low"]
            for duration in operation_durations.values()
            if duration > self.latency_thresholds["low"]
        )

        return CriticalPath(
            path_id=trace_id,
            operations=operations,
            total_duration_ms=total_duration,
            critical_operations=critical_operations,
            bottleneck_operations=bottleneck_operations,
            optimization_potential_ms=optimization_potential,
        )

    def get_service_dependency_graph(self) -> dict[str, Any]:
        """Get service dependency graph."""
        nodes = set()
        edges = []

        with self._lock:
            for dep in self.service_dependencies.values():
                nodes.add(dep.from_service)
                nodes.add(dep.to_service)

                edges.append(
                    {
                        "from": dep.from_service,
                        "to": dep.to_service,
                        "operation": dep.operation,
                        "call_count": dep.call_count,
                        "avg_latency_ms": dep.avg_latency_ms,
                        "error_rate": dep.error_rate,
                    }
                )

        return {"nodes": [{"id": node, "label": node} for node in nodes], "edges": edges}

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary."""
        current_time = time.time()

        # Calculate overall metrics
        with self._lock:
            total_operations = sum(stats["call_count"] for stats in self.operation_stats.values())
            total_errors = sum(stats["error_count"] for stats in self.operation_stats.values())

            if total_operations > 0:
                overall_error_rate = total_errors / total_operations
            else:
                overall_error_rate = 0

            # Get slowest operations
            slowest_operations = []
            for _key, stats in self.operation_stats.items():
                if stats["durations"]:
                    avg_duration = statistics.mean(stats["durations"])
                    slowest_operations.append(
                        {
                            "operation": stats["operation"],
                            "service": stats["service"],
                            "avg_duration_ms": avg_duration,
                            "call_count": stats["call_count"],
                        }
                    )

            slowest_operations.sort(key=lambda x: x["avg_duration_ms"], reverse=True)
            slowest_operations = slowest_operations[:10]

        # Get recent bottlenecks
        recent_bottlenecks = [
            b.to_dict()
            for b in self.detected_bottlenecks
            if current_time - b.detected_at < 3600  # Last hour
        ]

        return {
            "summary": {
                "total_operations": total_operations,
                "overall_error_rate": overall_error_rate,
                "active_services": len({stats["service"] for stats in self.operation_stats.values()}),
                "service_dependencies": len(self.service_dependencies),
                "detected_bottlenecks": len(recent_bottlenecks),
            },
            "slowest_operations": slowest_operations,
            "recent_bottlenecks": recent_bottlenecks,
            "service_dependency_graph": self.get_service_dependency_graph(),
            "analysis_timestamp": current_time,
        }

    def get_operation_insights(self, operation: str, service: str | None = None) -> dict[str, Any]:
        """Get detailed insights for a specific operation."""
        key_pattern = f"{service}:{operation}" if service else operation

        matching_stats = {}
        with self._lock:
            for key, stats in self.operation_stats.items():
                if key_pattern in key:
                    matching_stats[key] = stats

        if not matching_stats:
            return {"error": "Operation not found"}

        # Aggregate statistics
        total_calls = sum(stats["call_count"] for stats in matching_stats.values())
        total_errors = sum(stats["error_count"] for stats in matching_stats.values())
        all_durations = []

        for stats in matching_stats.values():
            all_durations.extend(stats["durations"])

        if not all_durations:
            return {"error": "No duration data available"}

        # Calculate percentiles
        percentiles = {}
        for p in [50, 75, 90, 95, 99]:
            percentiles[f"p{p}"] = self._percentile(all_durations, p)

        return {
            "operation": operation,
            "service": service,
            "total_calls": total_calls,
            "error_rate": total_errors / total_calls if total_calls > 0 else 0,
            "duration_stats": {
                "min_ms": min(all_durations),
                "max_ms": max(all_durations),
                "avg_ms": statistics.mean(all_durations),
                "median_ms": statistics.median(all_durations),
                **percentiles,
            },
            "recommendations": self._get_operation_recommendations(
                operation, all_durations, total_errors / total_calls if total_calls > 0 else 0
            ),
        }

    def _get_operation_recommendations(self, operation: str, durations: list[float], error_rate: float) -> list[str]:
        """Get recommendations for a specific operation."""
        recommendations = []
        avg_duration = statistics.mean(durations)

        if avg_duration > self.latency_thresholds["high"]:
            recommendations.extend(self._get_latency_recommendations(operation, avg_duration))

        if error_rate > self.error_rate_thresholds["medium"]:
            recommendations.extend(self._get_error_rate_recommendations(operation, error_rate))

        # Add general recommendations
        if not recommendations:
            recommendations.append("Performance is within acceptable thresholds")

        return recommendations

    def cleanup_old_data(self):
        """Clean up old data based on retention policy."""
        cutoff_time = time.time() - (self.retention_hours * 3600)

        with self._lock:
            # Clean up trace data (handled by deque maxlen)

            # Clean up operation stats
            keys_to_remove = []
            for key, stats in self.operation_stats.items():
                if stats["last_seen"] < cutoff_time:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self.operation_stats[key]

            # Clean up service dependencies
            deps_to_remove = []
            for key, dep in self.service_dependencies.items():
                if dep.last_seen < cutoff_time:
                    deps_to_remove.append(key)

            for key in deps_to_remove:
                del self.service_dependencies[key]

            # Clean up old bottlenecks
            self.detected_bottlenecks = [
                b
                for b in self.detected_bottlenecks
                if cutoff_time - b.detected_at < 86400  # Keep for 24 hours
            ]

        logger.info(f"Cleaned up old performance data (retention: {self.retention_hours}h)")


# Global performance analyzer
_performance_analyzer: PerformanceAnalyzer | None = None


def get_performance_analyzer() -> PerformanceAnalyzer:
    """Get global performance analyzer instance."""
    global _performance_analyzer
    if _performance_analyzer is None:
        _performance_analyzer = PerformanceAnalyzer()
    return _performance_analyzer
