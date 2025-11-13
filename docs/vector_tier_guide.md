# Vector Tier Production Guide

## Overview

The Vector Tier provides a production-ready, pluggable vector storage and similarity search system for the ATP platform. It supports multiple backend implementations including in-memory, Redis, Weaviate, and PostgreSQL with pgvector extension.

## Architecture

### Core Components

1. **VectorBackend Interface**: Abstract base class defining the vector storage contract
2. **Backend Implementations**: Concrete implementations for different storage systems
3. **VectorBackendFactory**: Factory for creating backend instances
4. **Metrics Integration**: Prometheus metrics collection and exposure
5. **Context Manager**: Lifecycle management for backend connections

### Supported Backends

| Backend | Description | Use Case |
|---------|-------------|----------|
| In-Memory | Fast, volatile storage | Development, testing, caching |
| Redis | Redis Stack with vector support | Production caching, real-time search |
| Weaviate | Native vector database | Full-featured vector search |
| PostgreSQL + pgvector | Relational database with vector extension | Enterprise deployments |

## Quick Start

### Basic Usage

```python
import asyncio
from tools.vector_backend import get_vector_backend

async def example():
    config = {
        'metrics_callback': create_prometheus_metrics_callback('memory')
    }

    async with get_vector_backend("memory", config) as backend:
        # Store a vector
        await backend.upsert(
            namespace="documents",
            key="doc1",
            embedding=[0.1, 0.2, 0.3],
            metadata={"title": "Sample Document", "category": "example"}
        )

        # Search for similar vectors
        results = await backend.query(
            namespace="documents",
            embedding=[0.1, 0.2, 0.35],
            k=5
        )

        for result in results:
            print(f"Found: {result.key}, Score: {result.score:.3f}")

asyncio.run(example())
```

### Backend Configuration

#### In-Memory Backend

```python
config = {
    'metrics_callback': metrics_callback  # Optional
}
backend = VectorBackendFactory.create("memory", config)
```

#### Redis Backend

```python
config = {
    'redis_url': 'redis://localhost:6379',
    'metrics_callback': metrics_callback
}
backend = VectorBackendFactory.create("redis", config)
```

#### Weaviate Backend

```python
config = {
    'weaviate_url': 'http://localhost:8080',
    'metrics_callback': metrics_callback
}
backend = VectorBackendFactory.create("weaviate", config)
```

#### PostgreSQL + pgvector Backend

```python
config = {
    'pg_connection_string': 'postgresql://user:pass@localhost:5432/vector_db',
    'metrics_callback': metrics_callback
}
backend = VectorBackendFactory.create("pgvector", config)
```

## API Reference

### VectorBackend Interface

All backend implementations provide the following methods:

#### `health_check() -> bool`
Check if the backend is healthy and accessible.

#### `upsert(namespace: str, key: str, embedding: list[float], metadata: dict) -> None`
Insert or update a vector with associated metadata.

#### `get(namespace: str, key: str) -> Optional[tuple[list[float], dict]]`
Retrieve a vector and its metadata by key.

#### `query(namespace: str, embedding: list[float], k: int = 10, threshold: Optional[float] = None) -> list[VectorSearchResult]`
Find k most similar vectors to the query embedding.

#### `delete(namespace: str, key: str) -> bool`
Delete a vector by key.

#### `list_namespaces() -> list[str]`
List all namespaces in the backend.

#### `clear_namespace(namespace: str) -> int`
Clear all vectors in a namespace. Returns count of deleted items.

## Metrics and Monitoring

### Prometheus Metrics

The vector tier exposes the following Prometheus metrics:

#### Histograms
- `vector_query_duration_seconds`: Query duration by operation and namespace
- Labels: `operation`, `namespace`, `backend_type`

#### Counters
- `vector_query_total`: Total number of queries by operation and namespace
- `vector_query_errors_total`: Total number of query errors

#### Gauges
- `vector_backend_connections_active`: Active connections to backend
- `vector_namespaces_total`: Total number of namespaces
- `vector_count_per_namespace`: Number of vectors per namespace

### Metrics Integration

```python
from tools.vector_metrics import create_prometheus_metrics_callback

# Create metrics callback for a specific backend
metrics_callback = create_prometheus_metrics_callback("redis")

# Use in backend configuration
config = {
    'redis_url': 'redis://localhost:6379',
    'metrics_callback': metrics_callback
}
```

## Deployment Guide

### Docker Deployment

#### In-Memory Backend (Development)

```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY tools/vector_backend.py .
```

#### Redis Backend

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y redis-server
COPY requirements.txt .
RUN pip install -r requirements.txt redis
COPY tools/vector_backend.py .
```

#### Weaviate Backend

```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt weaviate-client
COPY tools/vector_backend.py .
```

#### PostgreSQL + pgvector Backend

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y postgresql-client
COPY requirements.txt .
RUN pip install -r requirements.txt asyncpg
COPY tools/vector_backend.py .
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vector-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: vector-backend
  template:
    metadata:
      labels:
        app: vector-backend
    spec:
      containers:
      - name: vector-backend
        image: your-registry/vector-backend:latest
        env:
        - name: BACKEND_TYPE
          value: "redis"
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

## Performance Considerations

### Backend Selection Guide

| Requirement | Recommended Backend |
|-------------|-------------------|
| Development/Testing | In-Memory |
| High Performance | Redis |
| Full-Featured Search | Weaviate |
| ACID Compliance | PostgreSQL + pgvector |
| Large Scale | Weaviate or PostgreSQL |

### Optimization Tips

1. **Index Management**: Use appropriate indexing for your backend
2. **Batch Operations**: Group multiple operations when possible
3. **Connection Pooling**: Configure appropriate connection pool sizes
4. **Memory Management**: Monitor memory usage for in-memory backends
5. **Query Optimization**: Use thresholds to limit result sets

### Benchmarking

```python
import time
import asyncio
from tools.vector_backend import get_vector_backend

async def benchmark_backend(backend_type: str, config: dict):
    async with get_vector_backend(backend_type, config) as backend:
        # Warmup
        for i in range(100):
            await backend.upsert(f"bench", f"doc{i}", [float(i)/100.0], {})

        # Benchmark queries
        start_time = time.time()
        for i in range(1000):
            await backend.query("bench", [0.5], k=10)
        query_time = time.time() - start_time

        print(f"{backend_type}: 1000 queries in {query_time:.2f}s "
              f"({query_time/1000:.4f}s per query)")

# Run benchmarks
backends = ["memory", "redis", "weaviate", "pgvector"]
for backend in backends:
    config = {}  # Configure appropriately
    await benchmark_backend(backend, config)
```

## Troubleshooting

### Common Issues

#### Connection Failures
- **Redis**: Check Redis server is running and accessible
- **Weaviate**: Verify Weaviate instance is healthy
- **PostgreSQL**: Check connection string and pgvector extension

#### Performance Issues
- **High Latency**: Check network connectivity and backend configuration
- **Memory Usage**: Monitor backend memory consumption
- **Slow Queries**: Review query patterns and indexing

#### Error Messages
- `"Redis client not available"`: Redis dependencies not installed
- `"Weaviate client not available"`: Weaviate client not installed
- `"PostgreSQL pool not available"`: Database connection issues

### Debugging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Vector backend will log detailed information
```

## Security Considerations

1. **Access Control**: Implement proper authentication and authorization
2. **Data Encryption**: Encrypt sensitive vector data at rest and in transit
3. **Input Validation**: Validate embedding dimensions and metadata
4. **Rate Limiting**: Implement rate limiting for API endpoints
5. **Audit Logging**: Log all vector operations for compliance

## Future Enhancements

- **Hybrid Search**: Combine vector similarity with keyword search
- **Filtering**: Metadata-based filtering in similarity search
- **Streaming**: Support for streaming large result sets
- **Backup/Restore**: Automated backup and restore capabilities
- **Multi-region**: Cross-region replication support

## Contributing

When adding new backend implementations:

1. Extend the `VectorBackend` abstract base class
2. Implement all required methods
3. Add comprehensive tests
4. Update this documentation
5. Ensure metrics integration

## Support

For issues and questions:
- Check the troubleshooting section above
- Review the test suite for usage examples
- File issues in the project repository</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\vector_tier_guide.md
