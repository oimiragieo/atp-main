# Enterprise Multi-Tier Caching System

This document describes the enterprise multi-tier caching system that provides L1 (in-memory) and L2 (Redis) caching with production-grade features.

## Overview

The enterprise caching system provides:

- **Multi-Tier Architecture**: L1 (in-memory) + L2 (Redis) caching
- **Redis Cluster Support**: High availability with automatic failover
- **Cache Strategies**: Write-through, write-behind, read-through
- **Intelligent Invalidation**: Pattern-based and batch invalidation
- **Comprehensive Metrics**: Detailed performance monitoring
- **Health Monitoring**: Automatic health checks and recovery
- **Repository Integration**: Seamless integration with data access layer

## Architecture

```
Application Layer
       ↓
Cache Manager (router_service/cache/cache_manager.py)
       ↓
┌─────────────┬─────────────┐
│  L1 Cache   │  L2 Cache   │
│ (In-Memory) │   (Redis)   │
└─────────────┴─────────────┘
       ↓             ↓
   Local RAM    Redis Cluster
```

## Key Components

### 1. Cache Manager (`cache_manager.py`)

Central coordinator for all caching operations:

```python
from router_service.cache import get_cache_manager

cache_manager = get_cache_manager()

# Basic operations
await cache_manager.set("key", "value", ttl=300)
value = await cache_manager.get("key")
await cache_manager.delete("key")

# Pattern operations
await cache_manager.invalidate_pattern("user:*")
keys = await cache_manager.keys("session:*")
```

### 2. L1 Cache (`l1_cache.py`)

High-performance in-memory cache:

```python
from router_service.cache import L1Cache

l1_cache = L1Cache(
    max_size=1000,      # Maximum entries
    default_ttl=300,    # 5 minutes
    cleanup_interval=60 # Cleanup every minute
)

# Synchronous operations
l1_cache.set("key", "value", ttl=60)
value = l1_cache.get("key")
l1_cache.delete("key")
```

### 3. L2 Cache (`l2_cache.py`)

Redis-based distributed cache:

```python
from router_service.cache import RedisL2Cache

l2_cache = RedisL2Cache(
    redis_url="redis://localhost:6379/0",
    cluster_enabled=True,
    cluster_nodes=["redis1:6379", "redis2:6379", "redis3:6379"]
)

# Async operations
await l2_cache.set("key", "value", ttl=3600)
value = await l2_cache.get("key")
await l2_cache.delete("key")
```

### 4. Cache Configuration (`cache_config.py`)

Centralized configuration management:

```python
from router_service.cache import CacheConfig

config = CacheConfig.from_environment()
# Or create custom config
config = CacheConfig(
    l1_enabled=True,
    l2_enabled=True,
    write_through=True,
    redis_cluster_enabled=True
)
```

## Configuration

### Environment Variables

```bash
# L1 Cache Configuration
CACHE_L1_ENABLED=true
CACHE_L1_TTL=300
CACHE_L1_MAX_SIZE=1000
CACHE_L1_CLEANUP_INTERVAL=60

# L2 Cache Configuration
CACHE_L2_ENABLED=true
CACHE_L2_TTL=3600
CACHE_L2_KEY_PREFIX=atp:cache:

# Redis Configuration
ROUTER_REDIS_URL=redis://localhost:6379/0
REDIS_CLUSTER_ENABLED=true
REDIS_CLUSTER_NODES=["redis1:6379","redis2:6379","redis3:6379"]
REDIS_MAX_CONNECTIONS=20
REDIS_SOCKET_TIMEOUT=5.0

# Cache Strategy
CACHE_WRITE_THROUGH=true
CACHE_WRITE_BEHIND=false
CACHE_READ_THROUGH=true
CACHE_NULL_VALUES=false

# Invalidation
CACHE_INVALIDATION_ENABLED=true
CACHE_INVALIDATION_BATCH_SIZE=100
CACHE_INVALIDATION_TIMEOUT=1.0

# Metrics
CACHE_METRICS_ENABLED=true
CACHE_METRICS_DETAILED=false
```

### Docker Compose Redis Cluster

```yaml
version: "3.8"
services:
  redis-node-1:
    image: redis:7.2-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes
    ports: ["7001:6379"]
    volumes: ["redis-node-1-data:/data"]

  redis-node-2:
    image: redis:7.2-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes
    ports: ["7002:6379"]
    volumes: ["redis-node-2-data:/data"]

  redis-node-3:
    image: redis:7.2-alpine
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes
    ports: ["7003:6379"]
    volumes: ["redis-node-3-data:/data"]

volumes:
  redis-node-1-data:
  redis-node-2-data:
  redis-node-3-data:
```

## Cache Strategies

### Write-Through
Writes to both L1 and L2 simultaneously:

```python
config = CacheConfig(write_through=True, write_behind=False)
cache_manager = CacheManager(config)

# Writes to both L1 and L2
await cache_manager.set("key", "value")
```

### Write-Behind
Writes to L1 immediately, L2 asynchronously:

```python
config = CacheConfig(write_through=False, write_behind=True)
cache_manager = CacheManager(config)

# Writes to L1 immediately, schedules L2 write
await cache_manager.set("key", "value")
```

### Read-Through
Reads from L2 if L1 miss:

```python
config = CacheConfig(read_through=True)
cache_manager = CacheManager(config)

# Checks L1 first, then L2, populates L1 on L2 hit
value = await cache_manager.get("key")
```

## Repository Integration

### Enhanced Base Repository

```python
from router_service.repositories.cached_base import CachedBaseRepository
from router_service.models.database import Model

class ModelRepository(CachedBaseRepository[Model]):
    def __init__(self):
        super().__init__(Model, cache_prefix="model:")
    
    async def get_by_name_cached(self, name: str) -> Optional[Model]:
        cache_key = self._make_cache_key(f"name:{name}")
        
        # Try cache first
        cached_model = await self.cache_manager.get(cache_key)
        if cached_model:
            return cached_model
        
        # Query database
        model = await self.find_one_by(name=name)
        
        # Cache result
        if model:
            await self.cache_manager.set(cache_key, model)
        
        return model
```

### Automatic Cache Invalidation

```python
# Repository operations automatically invalidate related caches
repo = ModelRepository()

# Creates model and invalidates list caches
model = await repo.create(name="gpt-4", provider="openai")

# Updates model and invalidates related caches
await repo.update(model.id, cost_per_token=0.00003)

# Deletes model and invalidates all related caches
await repo.delete(model.id)
```

## Invalidation Strategies

### Single Key Invalidation

```python
# Immediate invalidation
await cache_manager.delete("user:123")

# Queued invalidation (batched)
await cache_manager.invalidate("user:123")
```

### Pattern-Based Invalidation

```python
# Invalidate all user sessions
count = await cache_manager.invalidate_pattern("session:*")

# Invalidate all model caches
await cache_manager.invalidate_pattern("model:*")
```

### Batch Invalidation

```python
# Automatic batching of invalidation requests
for user_id in user_ids:
    await cache_manager.invalidate(f"user:{user_id}")

# Processed in batches for efficiency
```

## Monitoring and Metrics

### Health Checks

```python
# Check overall cache health
health = await cache_manager.health_check()
print(f"L1 Cache: {health['l1_cache']}")
print(f"L2 Cache: {health['l2_cache']}")
print(f"Overall: {health['overall']}")
```

### Performance Metrics

Available metrics include:

- **Hit/Miss Ratios**: L1, L2, and combined ratios
- **Operation Latency**: Histograms for get/set/delete operations
- **Memory Usage**: L1 cache memory consumption
- **Connection Health**: Redis connection status
- **Invalidation Stats**: Invalidation success/failure rates

```python
# Get detailed statistics
stats = cache_manager.get_statistics()
print(f"Hit ratio: {stats['metrics']['combined']['hit_ratio']:.2%}")
print(f"L1 size: {stats['l1_cache']['total_entries']}")
```

### Prometheus Metrics

All metrics are automatically exported to Prometheus:

```
# Cache hit rates
cache_l1_hits_total
cache_l2_hits_total
cache_hit_ratio

# Performance metrics
cache_operation_duration_seconds
cache_l1_memory_bytes

# Redis cluster metrics
redis_cluster_nodes_healthy
redis_cluster_slots_ok
```

## Redis Cluster Management

### Cluster Health Monitoring

```python
from router_service.cache.redis_cluster import create_cluster_manager

cluster_manager = await create_cluster_manager([
    "redis1:6379", "redis2:6379", "redis3:6379"
])

# Get cluster information
info = await cluster_manager.get_cluster_info()
print(f"Cluster state: {info['cluster_state']}")
print(f"Healthy nodes: {info['healthy_nodes']}/{info['total_nodes']}")
```

### Automatic Failover

The system automatically handles Redis node failures:

- **Health Monitoring**: Continuous monitoring of all cluster nodes
- **Automatic Failover**: Transparent failover to healthy nodes
- **Connection Recovery**: Automatic reconnection when nodes recover
- **Metrics Tracking**: Detailed metrics on cluster health

## Performance Optimization

### L1 Cache Tuning

```python
# Optimize for high-frequency access
l1_cache = L1Cache(
    max_size=10000,        # Larger cache
    default_ttl=60,        # Shorter TTL for fresher data
    cleanup_interval=30    # More frequent cleanup
)
```

### L2 Cache Tuning

```python
# Optimize for distributed access
l2_cache = RedisL2Cache(
    default_ttl=3600,           # Longer TTL
    max_connections=50,         # More connections
    socket_timeout=2.0,         # Faster timeout
    cluster_enabled=True        # High availability
)
```

### Cache Key Design

```python
# Good key patterns
"user:123:profile"          # Hierarchical
"session:abc123:data"       # Specific scope
"model:gpt-4:metadata"      # Clear namespace

# Avoid
"user_profile_123"          # Hard to pattern match
"data"                      # Too generic
"very_long_key_name_that_wastes_memory"  # Inefficient
```

## Testing

### Unit Tests

```bash
# Run cache system tests
python -m pytest tests/test_cache_system.py -v

# Run with coverage
python -m pytest tests/test_cache_system.py --cov=router_service.cache
```

### Integration Tests

```bash
# Test with real Redis
REDIS_URL=redis://localhost:6379/1 python -m pytest tests/test_cache_integration.py

# Test cluster functionality
REDIS_CLUSTER_ENABLED=true python -m pytest tests/test_cache_cluster.py
```

### Performance Testing

```python
# Run performance demonstration
python -m router_service.cache_integration_example
```

## Troubleshooting

### Common Issues

1. **Redis Connection Errors**
   ```bash
   # Check Redis connectivity
   redis-cli -h localhost -p 6379 ping
   
   # Check cluster status
   redis-cli -h localhost -p 6379 cluster info
   ```

2. **High Memory Usage**
   ```python
   # Monitor L1 cache size
   stats = cache_manager.get_statistics()
   print(f"L1 memory: {stats['l1_cache']['memory_usage_bytes']} bytes")
   
   # Reduce cache size or TTL
   config.l1_max_size = 500
   config.l1_default_ttl = 60
   ```

3. **Low Hit Ratios**
   ```python
   # Check hit ratio
   stats = cache_manager.get_statistics()
   hit_ratio = stats['metrics']['combined']['hit_ratio']
   
   if hit_ratio < 0.5:
       # Increase TTL or cache size
       # Review invalidation patterns
       # Check for cache stampede
   ```

### Debug Mode

```python
import logging
logging.getLogger('router_service.cache').setLevel(logging.DEBUG)

# Enable detailed metrics
config = CacheConfig(metrics_detailed=True)
```

## Migration Guide

### From Simple Caching

```python
# Before: Simple dictionary caching
cache = {}
cache["key"] = "value"
value = cache.get("key")

# After: Multi-tier caching
cache_manager = get_cache_manager()
await cache_manager.set("key", "value")
value = await cache_manager.get("key")
```

### From Redis-Only

```python
# Before: Direct Redis usage
import redis
r = redis.Redis()
r.set("key", "value")
value = r.get("key")

# After: Multi-tier with L1 acceleration
cache_manager = get_cache_manager()
await cache_manager.set("key", "value")  # Writes to both L1 and L2
value = await cache_manager.get("key")   # Fast L1 lookup
```

## Best Practices

1. **Key Naming**: Use hierarchical, descriptive keys
2. **TTL Management**: Set appropriate TTLs based on data volatility
3. **Cache Warming**: Pre-populate frequently accessed data
4. **Invalidation**: Use pattern-based invalidation for related data
5. **Monitoring**: Monitor hit ratios and performance metrics
6. **Testing**: Test cache behavior in your specific use cases

## Future Enhancements

- **Distributed Invalidation**: Cross-instance cache invalidation
- **Cache Compression**: Automatic compression for large values
- **Smart Prefetching**: Predictive cache warming
- **Multi-Region**: Cross-region cache synchronization
- **Cache Analytics**: Advanced usage pattern analysis