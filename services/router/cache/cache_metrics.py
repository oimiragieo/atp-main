"""Cache metrics collection and reporting."""

from typing import Any

from metrics.registry import REGISTRY


class CacheMetrics:
    """Metrics collection for the caching system."""

    def __init__(self, namespace: str = "cache"):
        self.namespace = namespace

        # L1 Cache Metrics
        self.l1_hits = REGISTRY.counter(f"{namespace}_l1_hits_total")
        self.l1_misses = REGISTRY.counter(f"{namespace}_l1_misses_total")
        self.l1_sets = REGISTRY.counter(f"{namespace}_l1_sets_total")
        self.l1_deletes = REGISTRY.counter(f"{namespace}_l1_deletes_total")
        self.l1_evictions = REGISTRY.counter(f"{namespace}_l1_evictions_total")
        self.l1_size = REGISTRY.gauge(f"{namespace}_l1_size")
        self.l1_memory_bytes = REGISTRY.gauge(f"{namespace}_l1_memory_bytes")

        # L2 Cache Metrics
        self.l2_hits = REGISTRY.counter(f"{namespace}_l2_hits_total")
        self.l2_misses = REGISTRY.counter(f"{namespace}_l2_misses_total")
        self.l2_sets = REGISTRY.counter(f"{namespace}_l2_sets_total")
        self.l2_deletes = REGISTRY.counter(f"{namespace}_l2_deletes_total")
        self.l2_errors = REGISTRY.counter(f"{namespace}_l2_errors_total")
        self.l2_timeouts = REGISTRY.counter(f"{namespace}_l2_timeouts_total")

        # Combined Cache Metrics
        self.total_hits = REGISTRY.counter(f"{namespace}_hits_total")
        self.total_misses = REGISTRY.counter(f"{namespace}_misses_total")
        self.hit_ratio = REGISTRY.gauge(f"{namespace}_hit_ratio")

        # Performance Metrics
        self.operation_duration = REGISTRY.histogram(
            f"{namespace}_operation_duration_seconds", [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        )

        # Redis Connection Metrics
        self.redis_connections_active = REGISTRY.gauge(f"{namespace}_redis_connections_active")
        self.redis_connections_created = REGISTRY.counter(f"{namespace}_redis_connections_created_total")
        self.redis_connection_errors = REGISTRY.counter(f"{namespace}_redis_connection_errors_total")

        # Invalidation Metrics
        self.invalidations_sent = REGISTRY.counter(f"{namespace}_invalidations_sent_total")
        self.invalidations_received = REGISTRY.counter(f"{namespace}_invalidations_received_total")
        self.invalidation_errors = REGISTRY.counter(f"{namespace}_invalidation_errors_total")

        # Internal tracking for hit ratio calculation
        self._total_requests = 0
        self._total_hits = 0

    def record_l1_hit(self, key: str | None = None) -> None:
        """Record an L1 cache hit."""
        self.l1_hits.inc()
        self.total_hits.inc()
        self._update_hit_ratio(hit=True)

    def record_l1_miss(self, key: str | None = None) -> None:
        """Record an L1 cache miss."""
        self.l1_misses.inc()

    def record_l2_hit(self, key: str | None = None) -> None:
        """Record an L2 cache hit."""
        self.l2_hits.inc()
        self.total_hits.inc()
        self._update_hit_ratio(hit=True)

    def record_l2_miss(self, key: str | None = None) -> None:
        """Record an L2 cache miss."""
        self.l2_misses.inc()
        self.total_misses.inc()
        self._update_hit_ratio(hit=False)

    def record_l1_set(self, key: str | None = None) -> None:
        """Record an L1 cache set operation."""
        self.l1_sets.inc()

    def record_l2_set(self, key: str | None = None) -> None:
        """Record an L2 cache set operation."""
        self.l2_sets.inc()

    def record_l1_delete(self, key: str | None = None) -> None:
        """Record an L1 cache delete operation."""
        self.l1_deletes.inc()

    def record_l2_delete(self, key: str | None = None) -> None:
        """Record an L2 cache delete operation."""
        self.l2_deletes.inc()

    def record_l1_eviction(self, key: str | None = None) -> None:
        """Record an L1 cache eviction."""
        self.l1_evictions.inc()

    def record_l2_error(self, error_type: str = "unknown") -> None:
        """Record an L2 cache error."""
        self.l2_errors.inc()

    def record_l2_timeout(self) -> None:
        """Record an L2 cache timeout."""
        self.l2_timeouts.inc()

    def record_operation_duration(self, duration_seconds: float, operation: str = "unknown") -> None:
        """Record the duration of a cache operation."""
        self.operation_duration.observe(duration_seconds)

    def update_l1_size(self, size: int) -> None:
        """Update the L1 cache size gauge."""
        self.l1_size.set(size)

    def update_l1_memory_usage(self, bytes_used: int) -> None:
        """Update the L1 cache memory usage gauge."""
        self.l1_memory_bytes.set(bytes_used)

    def update_redis_connections(self, active: int) -> None:
        """Update the active Redis connections gauge."""
        self.redis_connections_active.set(active)

    def record_redis_connection_created(self) -> None:
        """Record a new Redis connection creation."""
        self.redis_connections_created.inc()

    def record_redis_connection_error(self) -> None:
        """Record a Redis connection error."""
        self.redis_connection_errors.inc()

    def record_invalidation_sent(self, count: int = 1) -> None:
        """Record cache invalidations sent."""
        self.invalidations_sent.inc(count)

    def record_invalidation_received(self, count: int = 1) -> None:
        """Record cache invalidations received."""
        self.invalidations_received.inc(count)

    def record_invalidation_error(self) -> None:
        """Record a cache invalidation error."""
        self.invalidation_errors.inc()

    def _update_hit_ratio(self, hit: bool) -> None:
        """Update the hit ratio calculation."""
        self._total_requests += 1
        if hit:
            self._total_hits += 1

        # Update hit ratio (avoid division by zero)
        if self._total_requests > 0:
            ratio = self._total_hits / self._total_requests
            self.hit_ratio.set(ratio)

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            "l1_cache": {
                "hits": self.l1_hits.value,
                "misses": self.l1_misses.value,
                "sets": self.l1_sets.value,
                "deletes": self.l1_deletes.value,
                "evictions": self.l1_evictions.value,
                "size": self.l1_size.value,
                "memory_bytes": self.l1_memory_bytes.value,
            },
            "l2_cache": {
                "hits": self.l2_hits.value,
                "misses": self.l2_misses.value,
                "sets": self.l2_sets.value,
                "deletes": self.l2_deletes.value,
                "errors": self.l2_errors.value,
                "timeouts": self.l2_timeouts.value,
            },
            "combined": {
                "total_hits": self.total_hits.value,
                "total_misses": self.total_misses.value,
                "hit_ratio": self.hit_ratio.value,
            },
            "redis": {
                "connections_active": self.redis_connections_active.value,
                "connections_created": self.redis_connections_created.value,
                "connection_errors": self.redis_connection_errors.value,
            },
            "invalidation": {
                "sent": self.invalidations_sent.value,
                "received": self.invalidations_received.value,
                "errors": self.invalidation_errors.value,
            },
        }


# Global cache metrics instance
_cache_metrics: CacheMetrics | None = None


def get_cache_metrics() -> CacheMetrics:
    """Get the global cache metrics instance."""
    global _cache_metrics
    if _cache_metrics is None:
        _cache_metrics = CacheMetrics()
    return _cache_metrics
