"""Example of integrating the enhanced caching system with the router service."""

import asyncio
import logging
import time
from typing import Any

from .cache import CacheConfig, get_cache_manager, initialize_cache_manager
from .models.database import Model
from .repositories.cached_base import CachedBaseRepository

logger = logging.getLogger(__name__)


class CachedModelRepository(CachedBaseRepository[Model]):
    """Example of using the cached base repository for models."""

    def __init__(self):
        super().__init__(Model, cache_prefix="model:")

    async def get_by_name_cached(self, name: str) -> Model:
        """Get model by name with caching."""
        cache_key = self._make_cache_key(f"name:{name}")

        # Try cache first
        cached_model = await self.cache_manager.get(cache_key)
        if cached_model:
            return cached_model

        # Query database
        model = await self.find_one_by(name=name)

        # Cache result
        if model:
            await self.cache_manager.set(cache_key, model, self.default_ttl)

        return model

    async def get_models_by_provider_cached(self, provider_name: str) -> list[Model]:
        """Get models by provider with caching."""
        cache_key = self._make_cache_key(f"provider:{provider_name}")

        # Try cache first
        cached_models = await self.cache_manager.get(cache_key)
        if cached_models:
            return cached_models

        # Query database (this would need to be implemented based on your schema)
        models = await self.find_by(provider_name=provider_name)

        # Cache result
        await self.cache_manager.set(cache_key, models, self.list_cache_ttl)

        return models


async def demonstrate_basic_caching():
    """Demonstrate basic caching operations."""
    print("=== Basic Caching Operations ===\n")

    # Initialize cache manager with custom configuration
    config = CacheConfig(
        l1_enabled=True,
        l2_enabled=True,  # Will use NoOp if Redis not available
        l1_default_ttl=300,
        l2_default_ttl=3600,
        write_through=True,
        read_through=True,
        metrics_enabled=True,
    )

    cache_manager = await initialize_cache_manager(config)

    # Basic operations
    print("1. Setting cache values...")
    await cache_manager.set("user:123", {"name": "John", "email": "john@example.com"})
    await cache_manager.set("config:timeout", 30)
    await cache_manager.set("model:gpt-4", {"provider": "openai", "cost": 0.03})

    print("2. Getting cache values...")
    user = await cache_manager.get("user:123")
    timeout = await cache_manager.get("config:timeout")
    model = await cache_manager.get("model:gpt-4")

    print(f"   User: {user}")
    print(f"   Timeout: {timeout}")
    print(f"   Model: {model}")

    print("3. Testing cache hits and misses...")
    start_time = time.time()
    for _i in range(100):
        await cache_manager.get("user:123")  # Should hit L1 cache
    l1_time = time.time() - start_time

    # Clear L1 to test L2
    if cache_manager.l1_cache:
        cache_manager.l1_cache.clear()

    start_time = time.time()
    for _i in range(100):
        await cache_manager.get("user:123")  # Should hit L2 cache
    l2_time = time.time() - start_time

    print(f"   L1 cache (100 gets): {l1_time:.4f}s")
    print(f"   L2 cache (100 gets): {l2_time:.4f}s")

    print("4. Cache statistics:")
    stats = cache_manager.get_statistics()
    print(f"   L1 entries: {stats.get('l1_cache', {}).get('total_entries', 0)}")
    print(f"   L1 memory: {stats.get('l1_cache', {}).get('memory_usage_bytes', 0)} bytes")

    await cache_manager.close()
    print()


async def demonstrate_cache_invalidation():
    """Demonstrate cache invalidation strategies."""
    print("=== Cache Invalidation Strategies ===\n")

    cache_manager = get_cache_manager()

    # Set up test data
    await cache_manager.set("session:user1", {"active": True, "last_seen": time.time()})
    await cache_manager.set("session:user2", {"active": True, "last_seen": time.time()})
    await cache_manager.set("session:user3", {"active": False, "last_seen": time.time() - 3600})
    await cache_manager.set("config:feature_flags", {"new_ui": True, "beta_features": False})

    print("1. Single key invalidation...")
    await cache_manager.invalidate("session:user1")
    await asyncio.sleep(0.1)  # Allow invalidation to process

    user1_session = await cache_manager.get("session:user1")
    user2_session = await cache_manager.get("session:user2")

    print(f"   User1 session after invalidation: {user1_session}")
    print(f"   User2 session (should exist): {user2_session is not None}")

    print("2. Pattern-based invalidation...")
    invalidated_count = await cache_manager.invalidate_pattern("session:*")
    await asyncio.sleep(0.1)  # Allow invalidation to process

    print(f"   Invalidated {invalidated_count} session keys")

    remaining_sessions = await cache_manager.keys("session:*")
    config_exists = await cache_manager.exists("config:feature_flags")

    print(f"   Remaining session keys: {len(remaining_sessions)}")
    print(f"   Config still exists: {config_exists}")

    print()


async def demonstrate_repository_caching():
    """Demonstrate repository-level caching."""
    print("=== Repository-Level Caching ===\n")

    # This would normally use a real database
    # For demo purposes, we'll simulate it
    print("1. Repository caching simulation...")
    print("   (In real usage, this would integrate with your database models)")

    # Simulate cache warming
    cache_manager = get_cache_manager()

    # Simulate model data
    model_data = {
        "gpt-4": {"provider": "openai", "cost_per_token": 0.00003, "quality": 0.95},
        "claude-3": {"provider": "anthropic", "cost_per_token": 0.000015, "quality": 0.92},
        "llama-2": {"provider": "local", "cost_per_token": 0.0, "quality": 0.75},
    }

    print("2. Warming model cache...")
    for model_name, data in model_data.items():
        cache_key = f"model:{model_name}"
        await cache_manager.set(cache_key, data, 600)  # 10 minute TTL

    print("3. Simulating model lookups...")
    start_time = time.time()

    for _ in range(50):
        for model_name in model_data.keys():
            cache_key = f"model:{model_name}"
            model = await cache_manager.get(cache_key)
            if model:
                # Simulate some processing
                model.get("quality", 0.0)

    lookup_time = time.time() - start_time
    print(f"   50 lookups x 3 models = 150 cache hits in {lookup_time:.4f}s")

    print("4. Cache statistics after repository simulation:")
    stats = cache_manager.get_statistics()
    if "metrics" in stats:
        metrics = stats["metrics"]
        total_hits = metrics.get("combined", {}).get("total_hits", 0)
        hit_ratio = metrics.get("combined", {}).get("hit_ratio", 0.0)
        print(f"   Total cache hits: {total_hits}")
        print(f"   Hit ratio: {hit_ratio:.2%}")

    print()


async def demonstrate_health_monitoring():
    """Demonstrate cache health monitoring."""
    print("=== Cache Health Monitoring ===\n")

    cache_manager = get_cache_manager()

    print("1. Overall health check...")
    health = await cache_manager.health_check()

    print(f"   L1 Cache: {'✅' if health['l1_cache'] else '❌'}")
    print(f"   L2 Cache: {'✅' if health['l2_cache'] else '❌'}")
    print(f"   Overall: {'✅' if health['overall'] else '❌'}")

    if not health["overall"]:
        print("   Issues detected:")
        for component, status in health.items():
            if component.endswith("_error"):
                print(f"     {component}: {status}")

    print("2. Detailed statistics...")
    stats = cache_manager.get_statistics()

    if "l1_cache" in stats:
        l1_stats = stats["l1_cache"]
        print("   L1 Cache:")
        print(f"     Entries: {l1_stats.get('total_entries', 0)}")
        print(f"     Memory: {l1_stats.get('memory_usage_bytes', 0)} bytes")
        print(f"     Max size: {l1_stats.get('max_size', 0)}")

    if "metrics" in stats:
        metrics = stats["metrics"]
        print("   Cache Metrics:")

        l1_metrics = metrics.get("l1_cache", {})
        if l1_metrics:
            print(f"     L1 hits: {l1_metrics.get('hits', 0)}")
            print(f"     L1 misses: {l1_metrics.get('misses', 0)}")
            print(f"     L1 evictions: {l1_metrics.get('evictions', 0)}")

        l2_metrics = metrics.get("l2_cache", {})
        if l2_metrics:
            print(f"     L2 hits: {l2_metrics.get('hits', 0)}")
            print(f"     L2 misses: {l2_metrics.get('misses', 0)}")
            print(f"     L2 errors: {l2_metrics.get('errors', 0)}")

    print()


async def demonstrate_performance_comparison():
    """Demonstrate performance comparison between cached and uncached operations."""
    print("=== Performance Comparison ===\n")

    cache_manager = get_cache_manager()

    # Simulate expensive operations
    async def expensive_operation(key: str) -> dict[str, Any]:
        """Simulate an expensive database or API call."""
        await asyncio.sleep(0.01)  # 10ms delay
        return {"key": key, "computed_at": time.time(), "expensive_result": f"result_for_{key}"}

    # Test data
    test_keys = [f"item_{i}" for i in range(20)]

    print("1. Without caching (cold)...")
    start_time = time.time()

    uncached_results = []
    for key in test_keys:
        result = await expensive_operation(key)
        uncached_results.append(result)

    uncached_time = time.time() - start_time
    print(f"   Time: {uncached_time:.3f}s for {len(test_keys)} operations")

    print("2. With caching (warm cache)...")

    # Pre-populate cache
    for key in test_keys:
        result = await expensive_operation(key)
        await cache_manager.set(f"expensive:{key}", result, 300)

    start_time = time.time()

    cached_results = []
    for key in test_keys:
        result = await cache_manager.get(f"expensive:{key}")
        cached_results.append(result)

    cached_time = time.time() - start_time
    print(f"   Time: {cached_time:.3f}s for {len(test_keys)} operations")

    speedup = uncached_time / cached_time if cached_time > 0 else float("inf")
    print(f"   Speedup: {speedup:.1f}x faster with caching")

    print("3. Mixed scenario (some cached, some not)...")

    # Clear half the cache
    for i in range(0, len(test_keys), 2):
        await cache_manager.delete(f"expensive:{test_keys[i]}")

    start_time = time.time()

    mixed_results = []
    cache_hits = 0
    cache_misses = 0

    for key in test_keys:
        cache_key = f"expensive:{key}"
        result = await cache_manager.get(cache_key)

        if result is None:
            # Cache miss - perform expensive operation
            result = await expensive_operation(key)
            await cache_manager.set(cache_key, result, 300)
            cache_misses += 1
        else:
            cache_hits += 1

        mixed_results.append(result)

    mixed_time = time.time() - start_time
    print(f"   Time: {mixed_time:.3f}s ({cache_hits} hits, {cache_misses} misses)")

    print()


async def main():
    """Main demonstration function."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Suppress verbose logs
    logging.getLogger("router_service.cache").setLevel(logging.WARNING)

    try:
        print("🚀 Enterprise Caching System Demonstration\n")

        # Run demonstrations
        await demonstrate_basic_caching()
        await demonstrate_cache_invalidation()
        await demonstrate_repository_caching()
        await demonstrate_health_monitoring()
        await demonstrate_performance_comparison()

        print("✅ All demonstrations completed successfully!")

    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        logger.exception("Demonstration execution failed")
        return 1

    finally:
        # Cleanup
        cache_manager = get_cache_manager()
        await cache_manager.close()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
