"""
Tests for adaptive TTL cache with LFU hot key detection.
"""

import os
import sys
import time

import pytest

# Add memory-gateway to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))

from adaptive_cache import CacheEntry, LFUCache, WriteThroughCache


class TestLFUCache:
    """Test LFU Cache functionality."""

    def test_basic_put_get(self):
        """Test basic put and get operations."""
        cache = LFUCache(max_size=10, base_ttl_s=60.0)

        # Put and get
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.size() == 1

    def test_expiration(self):
        """Test TTL expiration."""
        cache = LFUCache(max_size=10, base_ttl_s=0.1)  # Very short TTL

        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.2)  # Wait for expiration
        assert cache.get("key1") is None
        assert cache.size() == 0

    def test_lfu_eviction(self):
        """Test LFU eviction when cache is full."""
        cache = LFUCache(max_size=2, base_ttl_s=60.0)

        # Fill cache
        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # Access key1 multiple times to make it "hot"
        cache.get("key1")
        cache.get("key1")
        cache.get("key1")

        # Access key2 only once
        cache.get("key2")

        # Add third item - should evict key2 (less frequently used)
        cache.put("key3", "value3")

        assert cache.get("key1") == "value1"  # Should still be there
        assert cache.get("key2") is None     # Should be evicted
        assert cache.get("key3") == "value3"  # Should be there

    def test_adaptive_ttl_hot_key(self):
        """Test adaptive TTL for hot keys."""
        # Create entry and make it hot
        entry = CacheEntry(key="hot_key", value="hot_value", ttl_s=1.0)

        # Simulate accesses
        for _ in range(5):  # Exceed threshold
            entry.access()

        adaptive_ttl = entry.calculate_adaptive_ttl(1.0, 3.0, 3)
        assert adaptive_ttl == 3.0  # Should be extended

    def test_adaptive_ttl_cold_key(self):
        """Test adaptive TTL for cold keys."""
        # Create entry but don't make it hot
        entry = CacheEntry(key="cold_key", value="cold_value", ttl_s=1.0)

        # Simulate few accesses
        for _ in range(2):  # Below threshold
            entry.access()

        adaptive_ttl = entry.calculate_adaptive_ttl(1.0, 3.0, 3)
        assert adaptive_ttl == 1.0  # Should use base TTL

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = LFUCache(max_size=10, base_ttl_s=60.0, frequency_threshold=3)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # Access key1 multiple times
        for _ in range(5):
            cache.get("key1")

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["total_accesses"] == 5
        assert stats["hot_keys"] == 1  # key1 should be hot


class TestWriteThroughCache:
    """Test write-through cache functionality."""

    def test_write_through_get(self):
        """Test write-through get operation."""
        backend_data = {"key1": "backend_value1"}

        def backend_get(key):
            return backend_data.get(key)

        def backend_put(key, value):
            backend_data[key] = value

        cache = WriteThroughCache(backend_get, backend_put)

        # First get should hit backend
        assert cache.get("key1") == "backend_value1"

        # Second get should hit cache
        assert cache.get("key1") == "backend_value1"

    def test_write_through_put(self):
        """Test write-through put operation."""
        backend_data = {}

        def backend_get(key):
            return backend_data.get(key)

        def backend_put(key, value):
            backend_data[key] = value

        cache = WriteThroughCache(backend_get, backend_put)

        # Put should write to backend and cache
        cache.put("key1", "value1")

        # Verify in backend
        assert backend_data["key1"] == "value1"

        # Verify in cache
        assert cache.get("key1") == "value1"

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        backend_data = {"key1": "value1"}

        def backend_get(key):
            return backend_data.get(key)

        def backend_put(key, value):
            backend_data[key] = value

        cache = WriteThroughCache(backend_get, backend_put)

        # Load into cache
        assert cache.get("key1") == "value1"

        # Invalidate
        cache.invalidate("key1")

        # Next get should hit backend again
        backend_data["key1"] = "updated_value"
        assert cache.get("key1") == "updated_value"


def test_latency_reduction():
    """Test that hot keys have reduced latency due to longer TTL."""
    cache = LFUCache(max_size=10, base_ttl_s=1.0, hot_multiplier=5.0, frequency_threshold=3)

    # Put a key
    cache.put("hot_key", "value", ttl_s=1.0)

    # Make it hot
    for _ in range(5):
        cache.get("hot_key")

    # Wait some time (but not enough for base TTL)
    time.sleep(0.8)

    # Hot key should still be available due to extended TTL
    assert cache.get("hot_key") == "value"

    # Put a cold key
    cache.put("cold_key", "cold_value", ttl_s=1.0)

    # Access it only once
    cache.get("cold_key")

    # Wait for base TTL to expire
    time.sleep(1.1)

    # Cold key should be expired
    assert cache.get("cold_key") is None


if __name__ == "__main__":
    pytest.main([__file__])
