# Edge Cache Implementation Guide

## Overview

GAP-363 implements an LRU + TTL cache for the ATP Edge Router Service to reduce latency and improve performance by caching embeddings and tool results at the network edge.

## Features

- **LRU Eviction Policy**: Least Recently Used entries are evicted when cache reaches capacity
- **TTL-based Expiration**: Entries automatically expire after a configurable time
- **Thread-safe Operations**: Safe for concurrent access in multi-threaded environments
- **Async Support**: Full async/await support for integration with FastAPI
- **Metrics Integration**: Comprehensive Prometheus metrics for monitoring
- **Configurable**: Cache size and TTL are configurable per deployment

## Architecture

### Core Components

1. **EdgeCache**: Synchronous cache implementation with background cleanup
2. **AsyncEdgeCache**: Async wrapper for seamless FastAPI integration
3. **CacheEntry**: Data structure for cached items with metadata
4. **Metrics**: Prometheus-compatible metrics for observability

### Cache Key Generation

Cache keys are generated using SHA256 hashing of the JSON-serialized request data:

```python
def _generate_key(self, request_data: dict[str, Any]) -> str:
    serialized = json.dumps(request_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
```

This ensures:
- Consistent keys for identical requests
- Key uniqueness across different request patterns
- Deterministic key generation

## Configuration

Add cache settings to your `EdgeConfig`:

```python
@dataclass
class EdgeConfig:
    # ... existing config ...

    # Cache settings
    enable_cache: bool = True  # Enable/disable caching
    cache_max_size: int = 1000  # Maximum cache entries
    cache_default_ttl_seconds: int = 300  # Default TTL (5 minutes)
```

## Usage

### Basic Cache Operations

```python
from router_service.edge_cache import AsyncEdgeCache

# Initialize cache
cache = AsyncEdgeCache(max_size=1000, default_ttl_seconds=300)
await cache.start()

# Store a response
request_data = {"prompt": "Hello world", "quality": "balanced"}
response_data = {"type": "final", "text": "Hello! How can I help you?"}
await cache.put(request_data, response_data)

# Retrieve from cache
cached_response = await cache.get(request_data)
if cached_response:
    print("Cache hit!")
else:
    print("Cache miss")

# Invalidate specific entry
await cache.invalidate(request_data)

# Clear entire cache
await cache.clear()

# Get cache statistics
stats = await cache.get_stats()
print(f"Hit ratio: {stats['hit_ratio']:.2%}")
```

### Integration with Edge Router

The cache is automatically integrated into the edge router's request processing pipeline:

1. **Cache Check**: First, check if the request is in cache
2. **SLM Processing**: If not cached and SLM can handle it, process and cache result
3. **Core Relay**: If not cached, relay to core and cache the response
4. **Cache Storage**: Store successful responses in cache for future requests

## Metrics

The cache exposes the following Prometheus metrics:

- `edge_cache_hits_total`: Total number of cache hits
- `edge_cache_misses_total`: Total number of cache misses
- `edge_cache_evictions_total`: Total number of cache evictions
- `edge_cache_size`: Current number of entries in cache
- `edge_cache_hit_ratio`: Cache hit ratio (0.0 to 1.0)

## API Endpoints

The edge router provides cache management endpoints:

### GET /cache/stats
Returns cache statistics:
```json
{
  "total_entries": 150,
  "max_size": 1000,
  "hit_ratio": 0.75,
  "total_requests": 200,
  "total_hits": 150,
  "total_misses": 50,
  "default_ttl_seconds": 300
}
```

### POST /cache/clear
Clears all cache entries:
```json
{"message": "Cache cleared successfully"}
```

### POST /cache/invalidate
Invalidates a specific cache entry:
```json
{"message": "Cache entry invalidated successfully"}
```

## Performance Characteristics

### Time Complexity
- **Get**: O(1) average case (hash table lookup)
- **Put**: O(1) average case
- **Eviction**: O(1) (LRU with OrderedDict)

### Space Complexity
- O(n) where n is the number of cached entries
- Each entry stores: request data hash (32 bytes) + response data + metadata (~100 bytes overhead)

### Memory Usage
- Base overhead: ~50KB for cache structure
- Per entry: ~100-500 bytes depending on response size
- Example: 1000 entries with average 1KB responses = ~1.1MB total

## Best Practices

### Cache Key Design
- Use consistent request data formatting
- Include all parameters that affect the response
- Avoid including timestamps or non-deterministic data

### TTL Configuration
- Set TTL based on data freshness requirements
- Consider request patterns (frequently accessed data can have longer TTL)
- Balance between cache hit rate and data staleness

### Size Configuration
- Monitor cache hit ratio and adjust size accordingly
- Consider memory constraints of edge devices
- Start with conservative sizes and scale up based on usage patterns

### Monitoring
- Monitor hit ratio (>70% is generally good)
- Watch for eviction rates (high eviction may indicate cache too small)
- Track memory usage to ensure edge devices aren't overwhelmed

## Error Handling

The cache includes robust error handling:
- Background cleanup errors are logged but don't crash the service
- Cache operations gracefully handle edge cases
- Async operations properly handle event loop management

## Testing

Comprehensive test coverage includes:
- Basic cache operations (put/get/invalidate/clear)
- TTL expiration behavior
- LRU eviction under memory pressure
- Thread safety and concurrent access
- Async wrapper functionality
- Integration with edge router
- Metrics collection and reporting

Run tests with:
```bash
python -m pytest tests/test_edge_router.py::TestEdgeCache -v
python -m pytest tests/test_edge_router.py::TestAsyncEdgeCache -v
python -m pytest tests/test_edge_router.py::TestEdgeRouterWithCache -v
```

## Troubleshooting

### Common Issues

1. **Low Hit Ratio**
   - Check TTL settings (too short = premature expiration)
   - Verify cache key consistency
   - Monitor for cache size issues (frequent evictions)

2. **High Memory Usage**
   - Reduce cache size
   - Implement more aggressive TTL
   - Monitor response sizes

3. **Cache Misses on Identical Requests**
   - Check request data serialization consistency
   - Verify JSON sorting in key generation
   - Look for non-deterministic data in requests

### Debug Information

Enable debug logging to see cache operations:
```python
import logging
logging.getLogger('router_service.edge_cache').setLevel(logging.DEBUG)
```

This will show cache hits, misses, evictions, and cleanup operations.

## Future Enhancements

Potential improvements for future versions:
- **Distributed Caching**: Redis/memcached integration for multi-node deployments
- **Cache Warming**: Proactive cache population based on usage patterns
- **Compression**: Compress cached responses to reduce memory usage
- **Persistence**: Optional disk persistence for cache survival across restarts
- **Advanced Eviction**: Custom eviction policies based on access patterns
