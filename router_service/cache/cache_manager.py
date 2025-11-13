"""Multi-tier cache manager with L1 (in-memory) and L2 (Redis) caching."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

from .cache_config import CacheConfig
from .cache_metrics import get_cache_metrics
from .l1_cache import L1Cache
from .l2_cache import L2Cache, NoOpL2Cache, RedisL2Cache

logger = logging.getLogger(__name__)


class CacheManager:
    """Multi-tier cache manager with L1 and L2 caching."""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig.from_environment()
        
        # Initialize L1 cache
        self.l1_cache = L1Cache(
            max_size=self.config.l1_max_size,
            default_ttl=self.config.l1_default_ttl,
            cleanup_interval=self.config.l1_cleanup_interval,
            enable_metrics=self.config.metrics_enabled
        ) if self.config.l1_enabled else None
        
        # Initialize L2 cache
        self.l2_cache = self._create_l2_cache()
        
        # Metrics
        self._metrics = get_cache_metrics() if self.config.metrics_enabled else None
        
        # Invalidation tracking
        self._invalidation_queue: asyncio.Queue = asyncio.Queue()
        self._invalidation_task: Optional[asyncio.Task] = None
        
        # Start background tasks
        self._start_background_tasks()
        
        logger.info(f"Cache manager initialized - L1: {self.config.l1_enabled}, L2: {self.config.l2_enabled}")
    
    def _create_l2_cache(self) -> L2Cache:
        """Create L2 cache instance based on configuration."""
        if not self.config.l2_enabled:
            return NoOpL2Cache()
        
        return RedisL2Cache(
            redis_url=self.config.redis_url,
            key_prefix=self.config.l2_key_prefix,
            default_ttl=self.config.l2_default_ttl,
            cluster_enabled=self.config.redis_cluster_enabled,
            cluster_nodes=self.config.redis_cluster_nodes,
            max_connections=self.config.redis_max_connections,
            socket_timeout=self.config.redis_socket_timeout,
            socket_connect_timeout=self.config.redis_socket_connect_timeout,
            retry_on_timeout=self.config.redis_retry_on_timeout,
            enable_metrics=self.config.metrics_enabled
        )
    
    def _start_background_tasks(self) -> None:
        """Start background tasks for cache management."""
        if self.config.invalidation_enabled:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._invalidation_task = loop.create_task(self._invalidation_worker())
            except RuntimeError:
                # No event loop running
                pass
    
    async def _invalidation_worker(self) -> None:
        """Background worker for processing cache invalidations."""
        batch = []
        
        while True:
            try:
                # Collect invalidation requests
                try:
                    # Wait for first item
                    item = await asyncio.wait_for(
                        self._invalidation_queue.get(),
                        timeout=self.config.invalidation_timeout
                    )
                    batch.append(item)
                    
                    # Collect additional items up to batch size
                    while len(batch) < self.config.invalidation_batch_size:
                        try:
                            item = self._invalidation_queue.get_nowait()
                            batch.append(item)
                        except asyncio.QueueEmpty:
                            break
                
                except asyncio.TimeoutError:
                    # No items to process, continue
                    continue
                
                # Process batch
                if batch:
                    await self._process_invalidation_batch(batch)
                    batch.clear()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache invalidation worker error: {e}")
                if self._metrics:
                    self._metrics.record_invalidation_error()
    
    async def _process_invalidation_batch(self, batch: List[str]) -> None:
        """Process a batch of cache invalidations."""
        try:
            # Remove from L1 cache
            if self.l1_cache:
                for key in batch:
                    self.l1_cache.delete(key)
            
            # Remove from L2 cache
            if self.config.l2_enabled:
                tasks = [self.l2_cache.delete(key) for key in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            if self._metrics:
                self._metrics.record_invalidation_sent(len(batch))
            
            logger.debug(f"Processed invalidation batch of {len(batch)} keys")
        
        except Exception as e:
            logger.error(f"Failed to process invalidation batch: {e}")
            if self._metrics:
                self._metrics.record_invalidation_error()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache (L1 first, then L2)."""
        start_time = time.time()
        
        try:
            # Try L1 cache first
            if self.l1_cache:
                value = self.l1_cache.get(key)
                if value is not None:
                    return value
            
            # Try L2 cache if L1 miss and read-through enabled
            if self.config.read_through and self.config.l2_enabled:
                value = await self.l2_cache.get(key)
                if value is not None:
                    # Populate L1 cache if enabled
                    if self.l1_cache:
                        self.l1_cache.set(key, value)
                    return value
            
            return None
        
        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "get")
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        start_time = time.time()
        
        try:
            success = True
            
            # Handle null values
            if value is None and not self.config.cache_null_values:
                return await self.delete(key)
            
            if self.config.write_through:
                # Write to both L1 and L2 simultaneously
                tasks = []
                
                if self.l1_cache:
                    # L1 is synchronous
                    self.l1_cache.set(key, value, ttl)
                
                if self.config.l2_enabled:
                    tasks.append(self.l2_cache.set(key, value, ttl))
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    success = all(isinstance(r, bool) and r for r in results)
            
            elif self.config.write_behind:
                # Write to L1 immediately, L2 asynchronously
                if self.l1_cache:
                    self.l1_cache.set(key, value, ttl)
                
                if self.config.l2_enabled:
                    # Schedule async write to L2
                    asyncio.create_task(self.l2_cache.set(key, value, ttl))
            
            else:
                # Write to L1 only
                if self.l1_cache:
                    self.l1_cache.set(key, value, ttl)
            
            return success
        
        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "set")
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        start_time = time.time()
        
        try:
            success = True
            
            # Delete from L1
            if self.l1_cache:
                self.l1_cache.delete(key)
            
            # Delete from L2
            if self.config.l2_enabled:
                l2_success = await self.l2_cache.delete(key)
                success = success and l2_success
            
            return success
        
        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "delete")
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        # Check L1 first
        if self.l1_cache and self.l1_cache.exists(key):
            return True
        
        # Check L2 if enabled
        if self.config.l2_enabled:
            return await self.l2_cache.exists(key)
        
        return False
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        # Clear L1
        if self.l1_cache:
            self.l1_cache.clear()
        
        # Clear L2
        if self.config.l2_enabled:
            await self.l2_cache.clear()
    
    async def keys(self, pattern: str = "*") -> Set[str]:
        """Get keys matching pattern."""
        all_keys = set()
        
        # Get keys from L1
        if self.l1_cache:
            l1_keys = self.l1_cache.keys()
            if pattern == "*":
                all_keys.update(l1_keys)
            else:
                # Simple pattern matching (could be enhanced)
                import fnmatch
                all_keys.update(key for key in l1_keys if fnmatch.fnmatch(key, pattern))
        
        # Get keys from L2
        if self.config.l2_enabled:
            l2_keys = await self.l2_cache.keys(pattern)
            all_keys.update(l2_keys)
        
        return all_keys
    
    async def invalidate(self, key: str) -> None:
        """Invalidate a cache key."""
        if self.config.invalidation_enabled:
            await self._invalidation_queue.put(key)
        else:
            # Immediate invalidation
            await self.delete(key)
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        keys = await self.keys(pattern)
        
        if self.config.invalidation_enabled:
            for key in keys:
                await self._invalidation_queue.put(key)
        else:
            # Immediate invalidation
            tasks = [self.delete(key) for key in keys]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return len(keys)
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on cache components."""
        health = {
            "l1_cache": True,
            "l2_cache": True,
            "overall": True
        }
        
        # Check L1 cache
        if self.l1_cache:
            try:
                # Simple test
                test_key = "__health_check__"
                self.l1_cache.set(test_key, "test", 1)
                value = self.l1_cache.get(test_key)
                health["l1_cache"] = value == "test"
                self.l1_cache.delete(test_key)
            except Exception as e:
                health["l1_cache"] = False
                health["l1_error"] = str(e)
        
        # Check L2 cache
        if self.config.l2_enabled:
            try:
                health["l2_cache"] = await self.l2_cache.health_check()
            except Exception as e:
                health["l2_cache"] = False
                health["l2_error"] = str(e)
        
        health["overall"] = health["l1_cache"] and health["l2_cache"]
        return health
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {
            "config": {
                "l1_enabled": self.config.l1_enabled,
                "l2_enabled": self.config.l2_enabled,
                "write_through": self.config.write_through,
                "read_through": self.config.read_through
            }
        }
        
        # L1 statistics
        if self.l1_cache:
            stats["l1_cache"] = self.l1_cache.get_statistics()
        
        # Metrics statistics
        if self._metrics:
            stats["metrics"] = self._metrics.get_statistics()
        
        return stats
    
    async def close(self) -> None:
        """Close cache manager and cleanup resources."""
        # Cancel background tasks
        if self._invalidation_task and not self._invalidation_task.done():
            self._invalidation_task.cancel()
            try:
                await self._invalidation_task
            except asyncio.CancelledError:
                pass
        
        # Close L1 cache
        if self.l1_cache:
            self.l1_cache.shutdown()
        
        # Close L2 cache
        if hasattr(self.l2_cache, 'close'):
            await self.l2_cache.close()
        
        logger.info("Cache manager closed")


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


async def initialize_cache_manager(config: Optional[CacheConfig] = None) -> CacheManager:
    """Initialize the cache manager with optional configuration."""
    global _cache_manager
    _cache_manager = CacheManager(config)
    
    # Perform initial health check
    health = await _cache_manager.health_check()
    if not health["overall"]:
        logger.warning(f"Cache manager health check failed: {health}")
    else:
        logger.info("Cache manager initialized and health check passed")
    
    return _cache_manager