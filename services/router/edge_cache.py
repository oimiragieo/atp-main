"""
Edge Cache Implementation for ATP Router Service

This module provides an LRU + TTL cache for embeddings and tool results
to reduce latency and improve performance in edge routing scenarios.

GAP-363: Edge cache implementation
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from metrics.registry import (
    EDGE_CACHE_EVICTIONS_TOTAL,
    EDGE_CACHE_HIT_RATIO,
    EDGE_CACHE_HITS_TOTAL,
    EDGE_CACHE_MISSES_TOTAL,
    EDGE_CACHE_SIZE,
)


@dataclass
class CacheEntry:
    """Represents a cached item with TTL and metadata."""

    value: Any
    timestamp: float
    ttl_seconds: int
    access_count: int = 0
    last_accessed: float = 0.0

    def is_expired(self) -> bool:
        """Check if the entry has expired."""
        return time.time() - self.timestamp > self.ttl_seconds

    def touch(self):
        """Update access metadata."""
        self.access_count += 1
        self.last_accessed = time.time()


class EdgeCache:
    """
    LRU + TTL cache implementation for edge routing.

    Features:
    - LRU eviction policy
    - TTL-based expiration
    - Thread-safe operations
    - Configurable max size and TTL
    - Metrics integration
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: int = 300):
        """
        Initialize the edge cache.

        Args:
            max_size: Maximum number of entries in the cache
            default_ttl_seconds: Default TTL for cache entries (5 minutes)
        """
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._cleanup_interval = 60  # Cleanup every minute
        self._cleanup_thread: threading.Thread | None = None
        self._running = False

        # Metrics tracking
        self._total_requests = 0
        self._total_hits = 0

    def start(self):
        """Start the background cleanup thread."""
        if self._running:
            return

        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop(self):
        """Stop the background cleanup thread."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

    def _cleanup_loop(self):
        """Background cleanup loop to remove expired entries."""
        while self._running:
            try:
                self._cleanup_expired()
                time.sleep(self._cleanup_interval)
            except Exception:
                # Log error but continue cleanup
                logger = logging.getLogger(__name__)
                logger.exception("Error during cache cleanup")

    def _cleanup_expired(self):
        """Remove expired entries from the cache."""
        with self._lock:
            expired_keys = []
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]
                EDGE_CACHE_EVICTIONS_TOTAL.inc()

            EDGE_CACHE_SIZE.set(len(self._cache))

    def _generate_key(self, request_data: dict[str, Any]) -> str:
        """
        Generate a cache key from request data.

        Args:
            request_data: Dictionary containing request parameters

        Returns:
            SHA256 hash of the serialized request data
        """
        # Sort keys for consistent hashing
        serialized = json.dumps(request_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(self, request_data: dict[str, Any]) -> Any | None:
        """
        Retrieve a value from the cache.

        Args:
            request_data: Dictionary containing request parameters

        Returns:
            Cached value if found and not expired, None otherwise
        """
        key = self._generate_key(request_data)

        with self._lock:
            self._total_requests += 1

            if key in self._cache:
                entry = self._cache[key]

                if entry.is_expired():
                    # Remove expired entry
                    del self._cache[key]
                    EDGE_CACHE_EVICTIONS_TOTAL.inc()
                    EDGE_CACHE_SIZE.set(len(self._cache))
                    EDGE_CACHE_MISSES_TOTAL.inc()
                    return None

                # Move to end (most recently used)
                self._cache.move_to_end(key)
                entry.touch()

                self._total_hits += 1
                EDGE_CACHE_HITS_TOTAL.inc()

                # Update hit ratio
                if self._total_requests > 0:
                    hit_ratio = self._total_hits / self._total_requests
                    EDGE_CACHE_HIT_RATIO.set(hit_ratio)

                return entry.value
            else:
                EDGE_CACHE_MISSES_TOTAL.inc()
                return None

    def put(self, request_data: dict[str, Any], value: Any, ttl_seconds: int | None = None):
        """
        Store a value in the cache.

        Args:
            request_data: Dictionary containing request parameters
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (uses default if None)
        """
        key = self._generate_key(request_data)
        ttl = ttl_seconds or self.default_ttl_seconds

        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]

            # Evict LRU if at capacity
            if len(self._cache) >= self.max_size:
                evicted_key, _ = self._cache.popitem(last=False)  # Remove LRU (first item)
                EDGE_CACHE_EVICTIONS_TOTAL.inc()

            # Add new entry
            entry = CacheEntry(value=value, timestamp=time.time(), ttl_seconds=ttl)
            self._cache[key] = entry
            EDGE_CACHE_SIZE.set(len(self._cache))

    def invalidate(self, request_data: dict[str, Any]):
        """
        Remove a specific entry from the cache.

        Args:
            request_data: Dictionary containing request parameters
        """
        key = self._generate_key(request_data)

        with self._lock:
            if key in self._cache:
                del self._cache[key]
                EDGE_CACHE_SIZE.set(len(self._cache))

    def clear(self):
        """Clear all entries from the cache."""
        with self._lock:
            evicted_count = len(self._cache)
            self._cache.clear()
            EDGE_CACHE_EVICTIONS_TOTAL.inc(evicted_count)
            EDGE_CACHE_SIZE.set(0)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary containing cache statistics
        """
        with self._lock:
            total_entries = len(self._cache)
            hit_ratio = (self._total_hits / self._total_requests) if self._total_requests > 0 else 0.0

            return {
                "total_entries": total_entries,
                "max_size": self.max_size,
                "hit_ratio": hit_ratio,
                "total_requests": self._total_requests,
                "total_hits": self._total_hits,
                "total_misses": self._total_requests - self._total_hits,
                "default_ttl_seconds": self.default_ttl_seconds,
            }


class AsyncEdgeCache:
    """
    Async wrapper for EdgeCache to support async operations.
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: int = 300):
        self._cache = EdgeCache(max_size, default_ttl_seconds)
        self._loop = None

    def _get_loop(self):
        """Get the current event loop, creating one if necessary."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def start(self):
        """Start the cache cleanup thread."""
        self._cache.start()

    def stop(self):
        """Stop the cache cleanup thread."""
        self._cache.stop()

    async def get(self, request_data: dict[str, Any]) -> Any | None:
        """Async get operation."""
        loop = self._get_loop()
        return await loop.run_in_executor(None, self._cache.get, request_data)

    async def put(self, request_data: dict[str, Any], value: Any, ttl_seconds: int | None = None):
        """Async put operation."""
        loop = self._get_loop()
        await loop.run_in_executor(None, self._cache.put, request_data, value, ttl_seconds)

    async def invalidate(self, request_data: dict[str, Any]):
        """Async invalidate operation."""
        loop = self._get_loop()
        await loop.run_in_executor(None, self._cache.invalidate, request_data)

    async def clear(self):
        """Async clear operation."""
        loop = self._get_loop()
        await loop.run_in_executor(None, self._cache.clear)

    async def get_stats(self) -> dict[str, Any]:
        """Async get stats operation."""
        loop = self._get_loop()
        return await loop.run_in_executor(None, self._cache.get_stats)
