"""
Adaptive TTL Cache with LFU (Least Frequently Used) hot key detection.

This module provides a write-through cache that adapts TTL based on access patterns,
automatically detecting hot keys using frequency counting.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(order=True)
class CacheEntry:
    """Cache entry with frequency and access time tracking."""
    key: str
    value: Any
    ttl_s: float
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    size_bytes: int = 0

    def expired(self, now: float = None) -> bool:
        now = now or time.time()
        return (now - self.created_at) > self.ttl_s

    def access(self, now: float = None) -> None:
        """Record an access to this entry."""
        now = now or time.time()
        self.last_accessed = now
        self.access_count += 1

    def calculate_adaptive_ttl(self, base_ttl: float, hot_multiplier: float = 3.0,
                              frequency_threshold: int = 10) -> float:
        """Calculate adaptive TTL based on access frequency."""
        if self.access_count >= frequency_threshold:
            # Hot key - extend TTL
            return base_ttl * hot_multiplier
        else:
            # Cold key - use base TTL
            return base_ttl


class LFUCache:
    """LFU Cache with adaptive TTL for hot key detection."""

    def __init__(self, max_size: int = 1000, base_ttl_s: float = 300.0,
                 hot_multiplier: float = 3.0, frequency_threshold: int = 10,
                 cleanup_interval_s: float = 60.0):
        self.max_size = max_size
        self.base_ttl_s = base_ttl_s
        self.hot_multiplier = hot_multiplier
        self.frequency_threshold = frequency_threshold

        # Storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

        # Frequency tracking for LFU eviction
        self._frequency_heap: list[tuple[int, str]] = []
        self._entry_frequencies: dict[str, int] = {}

        # Background cleanup
        self._cleanup_interval = cleanup_interval_s
        self._cleanup_timer: Optional[threading.Timer] = None
        self._start_cleanup_timer()

    def _start_cleanup_timer(self) -> None:
        """Start background cleanup timer."""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()

        self._cleanup_timer = threading.Timer(self._cleanup_interval, self._cleanup_expired)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _cleanup_expired(self) -> None:
        """Clean up expired entries."""
        with self._lock:
            now = time.time()
            expired_keys = []

            for key, entry in self._cache.items():
                if entry.expired(now):
                    expired_keys.append(key)

            for key in expired_keys:
                self._remove_entry(key)

            # Restart timer
            self._start_cleanup_timer()

    def _remove_entry(self, key: str) -> None:
        """Remove an entry from cache."""
        if key in self._cache:
            del self._cache[key]
        if key in self._entry_frequencies:
            del self._entry_frequencies[key]

    def _evict_lfu(self) -> None:
        """Evict least frequently used entry."""
        if not self._cache:
            return

        # Find entry with lowest frequency
        lfu_key = min(self._cache.keys(),
                     key=lambda k: self._cache[k].access_count)

        self._remove_entry(lfu_key)

    def _ensure_capacity(self) -> None:
        """Ensure cache doesn't exceed max size."""
        while len(self._cache) >= self.max_size:
            self._evict_lfu()

    def get(self, key: str, now: float = None) -> Optional[Any]:
        """Get value from cache, updating access patterns."""
        with self._lock:
            now = now or time.time()

            if key not in self._cache:
                return None

            entry = self._cache[key]

            if entry.expired(now):
                self._remove_entry(key)
                return None

            # Record access
            entry.access(now)

            # Check if this access makes it a hot key and extend TTL if needed
            if entry.access_count >= self.frequency_threshold:
                # Calculate new TTL for hot key
                new_ttl = self.base_ttl_s * self.hot_multiplier
                if new_ttl > entry.ttl_s:
                    entry.ttl_s = new_ttl
                    entry.created_at = now  # Reset expiration timer

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            return entry.value

    def put(self, key: str, value: Any, ttl_s: Optional[float] = None,
            size_bytes: int = 0, now: float = None) -> None:
        """Put value in cache with adaptive TTL."""
        with self._lock:
            now = now or time.time()

            # Check if this is an existing hot key
            existing_entry = self._cache.get(key)
            if existing_entry and existing_entry.access_count >= self.frequency_threshold:
                # Hot key - extend TTL
                if ttl_s is None:
                    ttl_s = self.base_ttl_s * self.hot_multiplier
                else:
                    ttl_s = max(ttl_s, self.base_ttl_s * self.hot_multiplier)
            elif ttl_s is None:
                ttl_s = self.base_ttl_s

            entry = CacheEntry(
                key=key,
                value=value,
                ttl_s=ttl_s,
                size_bytes=size_bytes,
                created_at=now
            )

            # Preserve access count from existing entry
            if existing_entry:
                entry.access_count = existing_entry.access_count

            # Remove existing entry if present
            self._remove_entry(key)

            # Ensure capacity
            self._ensure_capacity()

            # Add new entry
            self._cache[key] = entry
            self._cache.move_to_end(key)

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
            self._entry_frequencies.clear()
            self._frequency_heap.clear()

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_accesses = sum(entry.access_count for entry in self._cache.values())
            hot_keys = sum(1 for entry in self._cache.values()
                          if entry.access_count >= self.frequency_threshold)

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "total_accesses": total_accesses,
                "hot_keys": hot_keys,
                "hit_rate": total_accesses / max(1, len(self._cache)),
                "avg_ttl": sum(entry.ttl_s for entry in self._cache.values()) / max(1, len(self._cache))
            }

    def __del__(self) -> None:
        """Cleanup on destruction."""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()


class WriteThroughCache:
    """Write-through cache with backend storage."""

    def __init__(self, backend_get: Callable[[str], Any],
                 backend_put: Callable[[str, Any], None],
                 cache: Optional[LFUCache] = None):
        self.backend_get = backend_get
        self.backend_put = backend_put
        self.cache = cache or LFUCache()

    def get(self, key: str) -> Optional[Any]:
        """Get from cache, fallback to backend."""
        # Try cache first
        value = self.cache.get(key)
        if value is not None:
            return value

        # Fallback to backend
        value = self.backend_get(key)
        if value is not None:
            # Cache the backend result
            self.cache.put(key, value)

        return value

    def put(self, key: str, value: Any, ttl_s: Optional[float] = None) -> None:
        """Write through to backend and cache."""
        # Write to backend first
        self.backend_put(key, value)

        # Cache the result
        self.cache.put(key, value, ttl_s)

    def invalidate(self, key: str) -> None:
        """Invalidate cache entry."""
        self.cache.delete(key)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self.cache.stats()
