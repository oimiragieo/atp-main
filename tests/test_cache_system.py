"""Tests for the enterprise caching system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from router_service.cache import CacheConfig, CacheManager, L1Cache, get_cache_manager


@pytest.mark.asyncio
async def test_l1_cache_basic_operations():
    """Test basic L1 cache operations."""
    cache = L1Cache(max_size=100, default_ttl=60, enable_metrics=False)
    
    # Test set and get
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    
    # Test delete
    assert cache.delete("key1") is True
    assert cache.get("key1") is None
    assert cache.delete("nonexistent") is False
    
    # Test exists
    cache.set("key2", "value2")
    assert cache.exists("key2") is True
    assert cache.exists("nonexistent") is False
    
    # Test clear
    cache.set("key3", "value3")
    cache.clear()
    assert cache.get("key2") is None
    assert cache.get("key3") is None
    
    cache.shutdown()


@pytest.mark.asyncio
async def test_l1_cache_ttl_expiration():
    """Test L1 cache TTL expiration."""
    cache = L1Cache(max_size=100, default_ttl=1, enable_metrics=False)
    
    # Set with short TTL
    cache.set("key1", "value1", ttl=1)
    assert cache.get("key1") == "value1"
    
    # Wait for expiration
    await asyncio.sleep(1.1)
    assert cache.get("key1") is None
    
    cache.shutdown()


@pytest.mark.asyncio
async def test_l1_cache_lru_eviction():
    """Test L1 cache LRU eviction."""
    cache = L1Cache(max_size=2, default_ttl=60, enable_metrics=False)
    
    # Fill cache to capacity
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    
    # Access key1 to make it more recently used
    cache.get("key1")
    
    # Add third key, should evict key2 (least recently used)
    cache.set("key3", "value3")
    
    assert cache.get("key1") == "value1"  # Should still exist
    assert cache.get("key2") is None      # Should be evicted
    assert cache.get("key3") == "value3"  # Should exist
    
    cache.shutdown()


@pytest.mark.asyncio
async def test_cache_config_from_environment():
    """Test cache configuration from environment variables."""
    with patch.dict('os.environ', {
        'CACHE_L1_ENABLED': 'true',
        'CACHE_L1_TTL': '600',
        'CACHE_L2_ENABLED': 'false',
        'REDIS_URL': 'redis://test:6379/1'
    }):
        config = CacheConfig.from_environment()
        
        assert config.l1_enabled is True
        assert config.l1_default_ttl == 600
        assert config.l2_enabled is False
        assert config.redis_url == 'redis://test:6379/1'


@pytest.mark.asyncio
async def test_cache_manager_l1_only():
    """Test cache manager with L1 cache only."""
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=False,
        metrics_enabled=False
    )
    
    cache_manager = CacheManager(config)
    
    # Test basic operations
    await cache_manager.set("key1", "value1")
    assert await cache_manager.get("key1") == "value1"
    
    assert await cache_manager.exists("key1") is True
    assert await cache_manager.exists("nonexistent") is False
    
    assert await cache_manager.delete("key1") is True
    assert await cache_manager.get("key1") is None
    
    await cache_manager.close()


@pytest.mark.asyncio
async def test_cache_manager_with_mock_redis():
    """Test cache manager with mocked Redis L2 cache."""
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=True,
        write_through=True,
        read_through=True,
        metrics_enabled=False
    )
    
    # Mock Redis L2 cache
    mock_l2_cache = AsyncMock()
    mock_l2_cache.get.return_value = None
    mock_l2_cache.set.return_value = True
    mock_l2_cache.delete.return_value = True
    mock_l2_cache.exists.return_value = False
    mock_l2_cache.health_check.return_value = True
    
    with patch('router_service.cache.cache_manager.RedisL2Cache', return_value=mock_l2_cache):
        cache_manager = CacheManager(config)
        
        # Test write-through behavior
        await cache_manager.set("key1", "value1")
        
        # Should write to both L1 and L2
        mock_l2_cache.set.assert_called_once_with("key1", "value1", None)
        
        # Test read from L1 (should not hit L2)
        value = await cache_manager.get("key1")
        assert value == "value1"
        mock_l2_cache.get.assert_not_called()
        
        # Test L1 miss, L2 hit
        cache_manager.l1_cache.delete("key1")
        mock_l2_cache.get.return_value = "value1_from_l2"
        
        value = await cache_manager.get("key1")
        assert value == "value1_from_l2"
        mock_l2_cache.get.assert_called_once_with("key1")
        
        await cache_manager.close()


@pytest.mark.asyncio
async def test_cache_manager_health_check():
    """Test cache manager health check."""
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=False,
        metrics_enabled=False
    )
    
    cache_manager = CacheManager(config)
    
    health = await cache_manager.health_check()
    
    assert health["l1_cache"] is True
    assert health["l2_cache"] is True  # NoOp L2 cache always returns True
    assert health["overall"] is True
    
    await cache_manager.close()


@pytest.mark.asyncio
async def test_cache_manager_invalidation():
    """Test cache invalidation functionality."""
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=False,
        invalidation_enabled=True,
        metrics_enabled=False
    )
    
    cache_manager = CacheManager(config)
    
    # Set some values
    await cache_manager.set("key1", "value1")
    await cache_manager.set("key2", "value2")
    await cache_manager.set("prefix:key3", "value3")
    
    # Test single key invalidation
    await cache_manager.invalidate("key1")
    await asyncio.sleep(0.1)  # Allow invalidation to process
    
    assert await cache_manager.get("key1") is None
    assert await cache_manager.get("key2") == "value2"
    
    # Test pattern invalidation
    count = await cache_manager.invalidate_pattern("prefix:*")
    await asyncio.sleep(0.1)  # Allow invalidation to process
    
    assert count >= 1
    assert await cache_manager.get("prefix:key3") is None
    
    await cache_manager.close()


@pytest.mark.asyncio
async def test_cache_manager_statistics():
    """Test cache manager statistics."""
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=False,
        metrics_enabled=False
    )
    
    cache_manager = CacheManager(config)
    
    # Perform some operations
    await cache_manager.set("key1", "value1")
    await cache_manager.get("key1")
    await cache_manager.get("nonexistent")
    
    stats = cache_manager.get_statistics()
    
    assert "config" in stats
    assert "l1_cache" in stats
    assert stats["config"]["l1_enabled"] is True
    assert stats["config"]["l2_enabled"] is False
    
    await cache_manager.close()


@pytest.mark.asyncio
async def test_global_cache_manager():
    """Test global cache manager singleton."""
    # Clear any existing instance
    import router_service.cache.cache_manager
    router_service.cache.cache_manager._cache_manager = None
    
    # Get global instance
    cache_manager1 = get_cache_manager()
    cache_manager2 = get_cache_manager()
    
    # Should be the same instance
    assert cache_manager1 is cache_manager2
    
    await cache_manager1.close()


@pytest.mark.asyncio
async def test_cache_manager_write_strategies():
    """Test different cache write strategies."""
    # Test write-behind strategy
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=True,
        write_through=False,
        write_behind=True,
        metrics_enabled=False
    )
    
    mock_l2_cache = AsyncMock()
    mock_l2_cache.set.return_value = True
    mock_l2_cache.health_check.return_value = True
    
    with patch('router_service.cache.cache_manager.RedisL2Cache', return_value=mock_l2_cache):
        cache_manager = CacheManager(config)
        
        # Write-behind should write to L1 immediately, L2 asynchronously
        await cache_manager.set("key1", "value1")
        
        # L1 should have the value immediately
        assert cache_manager.l1_cache.get("key1") == "value1"
        
        # L2 write should be scheduled asynchronously
        await asyncio.sleep(0.1)  # Allow async task to complete
        mock_l2_cache.set.assert_called_once()
        
        await cache_manager.close()


if __name__ == "__main__":
    pytest.main([__file__])