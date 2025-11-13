"""L1 (in-memory) cache implementation with TTL and LRU eviction."""

import asyncio
import builtins
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from .cache_metrics import get_cache_metrics


@dataclass
class CacheEntry:
    """Cache entry with TTL and access tracking."""

    value: Any
    expires_at: float
    created_at: float
    access_count: int = 0
    last_accessed: float = 0.0

    def __post_init__(self):
        self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        """Check if the entry has expired."""
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Update access tracking."""
        self.access_count += 1
        self.last_accessed = time.time()


class L1Cache:
    """Thread-safe L1 cache with TTL and LRU eviction."""

    def __init__(
        self, max_size: int = 1000, default_ttl: int = 300, cleanup_interval: int = 60, enable_metrics: bool = True
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        self.enable_metrics = enable_metrics

        # Thread-safe storage using OrderedDict for LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

        # Metrics
        self._metrics = get_cache_metrics() if enable_metrics else None

        # Background cleanup
        self._cleanup_task: asyncio.Task | None = None
        self._shutdown_event = threading.Event()

        # Memory tracking
        self._estimated_memory = 0

        # Start background cleanup
        self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._cleanup_task = loop.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running, cleanup will be manual
            pass

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.cleanup_interval)
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue cleanup loop
                print(f"L1 cache cleanup error: {e}", file=sys.stderr)

    def _cleanup_expired(self) -> int:
        """Remove expired entries and return count removed."""
        removed_count = 0
        current_time = time.time()

        with self._lock:
            # Collect expired keys
            expired_keys = []
            for key, entry in self._cache.items():
                if current_time > entry.expires_at:
                    expired_keys.append(key)

            # Remove expired entries
            for key in expired_keys:
                entry = self._cache.pop(key, None)
                if entry:
                    removed_count += 1
                    self._update_memory_estimate(entry, removed=True)

            # Update metrics
            if self._metrics:
                self._metrics.update_l1_size(len(self._cache))
                self._metrics.update_l1_memory_usage(self._estimated_memory)

        return removed_count

    def _evict_lru(self, count: int = 1) -> int:
        """Evict least recently used entries."""
        evicted_count = 0

        with self._lock:
            for _ in range(min(count, len(self._cache))):
                if not self._cache:
                    break

                # Remove oldest entry (LRU)
                key, entry = self._cache.popitem(last=False)
                evicted_count += 1
                self._update_memory_estimate(entry, removed=True)

                if self._metrics:
                    self._metrics.record_l1_eviction(key)

        return evicted_count

    def _update_memory_estimate(self, entry: CacheEntry, removed: bool = False) -> None:
        """Update estimated memory usage."""
        # Simple estimation based on object size
        try:
            entry_size = sys.getsizeof(entry.value) + sys.getsizeof(entry) + 100  # overhead
            if removed:
                self._estimated_memory = max(0, self._estimated_memory - entry_size)
            else:
                self._estimated_memory += entry_size
        except Exception:
            # Fallback to fixed size estimation
            if removed:
                self._estimated_memory = max(0, self._estimated_memory - 1024)
            else:
                self._estimated_memory += 1024

    def get(self, key: str) -> Any | None:
        """Get value from cache."""
        start_time = time.time()

        try:
            with self._lock:
                entry = self._cache.get(key)

                if entry is None:
                    if self._metrics:
                        self._metrics.record_l1_miss(key)
                    return None

                # Check expiration
                if entry.is_expired():
                    self._cache.pop(key, None)
                    self._update_memory_estimate(entry, removed=True)
                    if self._metrics:
                        self._metrics.record_l1_miss(key)
                    return None

                # Update access tracking and move to end (most recently used)
                entry.touch()
                self._cache.move_to_end(key)

                if self._metrics:
                    self._metrics.record_l1_hit(key)

                return entry.value

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l1_get")

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache."""
        start_time = time.time()

        try:
            ttl = ttl or self.default_ttl
            expires_at = time.time() + ttl
            entry = CacheEntry(value=value, expires_at=expires_at, created_at=time.time())

            with self._lock:
                # Remove existing entry if present
                old_entry = self._cache.pop(key, None)
                if old_entry:
                    self._update_memory_estimate(old_entry, removed=True)

                # Check if we need to evict entries
                if len(self._cache) >= self.max_size:
                    self._evict_lru(1)

                # Add new entry
                self._cache[key] = entry
                self._update_memory_estimate(entry)

                if self._metrics:
                    self._metrics.record_l1_set(key)
                    self._metrics.update_l1_size(len(self._cache))
                    self._metrics.update_l1_memory_usage(self._estimated_memory)

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l1_set")

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        start_time = time.time()

        try:
            with self._lock:
                entry = self._cache.pop(key, None)
                if entry:
                    self._update_memory_estimate(entry, removed=True)
                    if self._metrics:
                        self._metrics.record_l1_delete(key)
                        self._metrics.update_l1_size(len(self._cache))
                        self._metrics.update_l1_memory_usage(self._estimated_memory)
                    return True
                return False

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l1_delete")

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
            self._estimated_memory = 0

            if self._metrics:
                self._metrics.update_l1_size(0)
                self._metrics.update_l1_memory_usage(0)

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry and not entry.is_expired():
                return True
            elif entry:
                # Remove expired entry
                self._cache.pop(key, None)
                self._update_memory_estimate(entry, removed=True)
            return False

    def keys(self) -> builtins.set[str]:
        """Get all non-expired keys."""
        current_time = time.time()
        valid_keys = set()

        with self._lock:
            for key, entry in self._cache.items():
                if current_time <= entry.expires_at:
                    valid_keys.add(key)

        return valid_keys

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)

    def memory_usage(self) -> int:
        """Get estimated memory usage in bytes."""
        return self._estimated_memory

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_entries = len(self._cache)
            expired_count = 0
            total_access_count = 0
            time.time()

            for entry in self._cache.values():
                if entry.is_expired():
                    expired_count += 1
                total_access_count += entry.access_count

            return {
                "total_entries": total_entries,
                "expired_entries": expired_count,
                "valid_entries": total_entries - expired_count,
                "memory_usage_bytes": self._estimated_memory,
                "max_size": self.max_size,
                "total_access_count": total_access_count,
                "avg_access_count": total_access_count / max(1, total_entries),
            }

    def cleanup(self) -> int:
        """Manually trigger cleanup of expired entries."""
        return self._cleanup_expired()

    def shutdown(self) -> None:
        """Shutdown the cache and cleanup resources."""
        self._shutdown_event.set()

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        self.clear()
