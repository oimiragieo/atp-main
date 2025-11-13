#!/usr/bin/env python3
"""Comprehensive tests for GAP-300: Vector Tier Production Backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.vector_backend import (
    InMemoryVectorBackend,
    PGVectorBackend,
    RedisVectorBackend,
    VectorBackendFactory,
    VectorQueryMetrics,
    WeaviateVectorBackend,
    get_vector_backend,
    prometheus_metrics_callback,
)


class TestInMemoryVectorBackend:
    """Test the in-memory vector backend implementation."""

    @pytest.fixture
    def backend(self):
        """Create a test backend instance."""
        config = {}
        return InMemoryVectorBackend(config)

    @pytest.fixture
    def backend_with_metrics(self):
        """Create a backend with metrics callback."""
        metrics_collected = []

        def collect_metrics(metrics: VectorQueryMetrics):
            metrics_collected.append(metrics)

        config = {"metrics_callback": collect_metrics}
        backend = InMemoryVectorBackend(config)
        backend._metrics_collected = metrics_collected
        return backend

    @pytest.mark.asyncio
    async def test_health_check(self, backend):
        """Test health check functionality."""
        assert await backend.health_check() is True

    @pytest.mark.asyncio
    async def test_upsert_and_get(self, backend):
        """Test upsert and get operations."""
        embedding = [0.1, 0.2, 0.3]
        metadata = {"text": "hello world", "category": "test"}

        # Test upsert
        await backend.upsert("test_ns", "doc1", embedding, metadata)

        # Test get
        result = await backend.get("test_ns", "doc1")
        assert result is not None
        retrieved_emb, retrieved_meta = result
        assert retrieved_emb == embedding
        assert retrieved_meta == metadata

        # Test get non-existent
        result = await backend.get("test_ns", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_basic(self, backend):
        """Test basic vector similarity query."""
        # Insert test vectors
        await backend.upsert("test_ns", "doc1", [1.0, 0.0, 0.0], {"id": 1})
        await backend.upsert("test_ns", "doc2", [0.0, 1.0, 0.0], {"id": 2})
        await backend.upsert("test_ns", "doc3", [0.0, 0.0, 1.0], {"id": 3})

        # Query with vector similar to doc1
        results = await backend.query("test_ns", [0.9, 0.1, 0.0], k=2)

        assert len(results) == 2
        assert results[0].key == "doc1"
        assert results[0].score > results[1].score  # doc1 should be most similar
        assert results[0].metadata["id"] == 1

    @pytest.mark.asyncio
    async def test_query_with_threshold(self, backend):
        """Test query with similarity threshold."""
        await backend.upsert("test_ns", "doc1", [1.0, 0.0], {"id": 1})
        await backend.upsert("test_ns", "doc2", [0.0, 1.0], {"id": 2})

        # Query with threshold
        results = await backend.query("test_ns", [1.0, 0.0], k=10, threshold=0.8)
        assert len(results) == 1
        assert results[0].key == "doc1"

    @pytest.mark.asyncio
    async def test_delete(self, backend):
        """Test delete operation."""
        await backend.upsert("test_ns", "doc1", [0.1, 0.2], {"id": 1})

        # Verify exists
        result = await backend.get("test_ns", "doc1")
        assert result is not None

        # Delete
        deleted = await backend.delete("test_ns", "doc1")
        assert deleted is True

        # Verify gone
        result = await backend.get("test_ns", "doc1")
        assert result is None

        # Delete non-existent
        deleted = await backend.delete("test_ns", "nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_list_namespaces(self, backend):
        """Test namespace listing."""
        await backend.upsert("ns1", "doc1", [0.1, 0.2], {})
        await backend.upsert("ns2", "doc1", [0.1, 0.2], {})

        namespaces = await backend.list_namespaces()
        assert set(namespaces) == {"ns1", "ns2"}

    @pytest.mark.asyncio
    async def test_clear_namespace(self, backend):
        """Test namespace clearing."""
        await backend.upsert("test_ns", "doc1", [0.1, 0.2], {})
        await backend.upsert("test_ns", "doc2", [0.3, 0.4], {})

        # Verify exists
        result1 = await backend.get("test_ns", "doc1")
        result2 = await backend.get("test_ns", "doc2")
        assert result1 is not None
        assert result2 is not None

        # Clear namespace
        count = await backend.clear_namespace("test_ns")
        assert count == 2

        # Verify empty
        result1 = await backend.get("test_ns", "doc1")
        result2 = await backend.get("test_ns", "doc2")
        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_metrics_collection(self, backend_with_metrics):
        """Test that metrics are collected for operations."""
        backend = backend_with_metrics

        # Perform operations
        await backend.upsert("test_ns", "doc1", [0.1, 0.2], {})
        await backend.query("test_ns", [0.1, 0.2], k=1)

        # Check metrics were collected
        assert len(backend._metrics_collected) >= 2

        upsert_metric = next(m for m in backend._metrics_collected if m.operation == "upsert")
        query_metric = next(m for m in backend._metrics_collected if m.operation == "query")

        assert upsert_metric.namespace == "test_ns"
        assert upsert_metric.duration_ms >= 0
        assert query_metric.namespace == "test_ns"
        assert query_metric.duration_ms >= 0


class TestVectorBackendFactory:
    """Test the backend factory."""

    def test_create_memory_backend(self):
        """Test creating in-memory backend."""
        config = {}
        backend = VectorBackendFactory.create("memory", config)
        assert isinstance(backend, InMemoryVectorBackend)

    def test_create_redis_backend(self):
        """Test creating Redis backend."""
        config = {"redis_url": "redis://localhost:6379"}
        backend = VectorBackendFactory.create("redis", config)
        assert isinstance(backend, RedisVectorBackend)

    def test_create_weaviate_backend(self):
        """Test creating Weaviate backend."""
        config = {"weaviate_url": "http://localhost:8080"}
        backend = VectorBackendFactory.create("weaviate", config)
        assert isinstance(backend, WeaviateVectorBackend)

    def test_create_pgvector_backend(self):
        """Test creating PGVector backend."""
        config = {"pg_connection_string": "postgresql://user:pass@localhost:5432/db"}
        backend = VectorBackendFactory.create("pgvector", config)
        assert isinstance(backend, PGVectorBackend)

    def test_create_unknown_backend(self):
        """Test creating unknown backend type raises error."""
        config = {}
        with pytest.raises(ValueError, match="Unknown backend type"):
            VectorBackendFactory.create("unknown", config)


class TestVectorBackendContextManager:
    """Test the vector backend context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using backend as context manager."""
        config = {}

        async with get_vector_backend("memory", config) as backend:
            assert isinstance(backend, InMemoryVectorBackend)

            # Test basic operation
            await backend.upsert("test", "doc1", [0.1, 0.2], {})
            result = await backend.get("test", "doc1")
            assert result is not None


class TestEmbeddingUpsertSearchParity:
    """Test embedding upsert/search parity across different scenarios."""

    @pytest.fixture
    def backend(self):
        """Create a test backend instance."""
        config = {}
        return InMemoryVectorBackend(config)

    @pytest.mark.asyncio
    async def test_exact_match_retrieval(self, backend):
        """Test that exact same embedding can be retrieved."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        metadata = {"source": "test"}

        await backend.upsert("test_ns", "exact_match", embedding, metadata)
        result = await backend.get("test_ns", "exact_match")

        assert result is not None
        retrieved_emb, retrieved_meta = result
        assert retrieved_emb == embedding
        assert retrieved_meta == metadata

    @pytest.mark.asyncio
    async def test_similarity_search_ordering(self, backend):
        """Test that similarity search returns results in correct order."""
        # Create embeddings at different "distances"
        base_emb = [1.0, 0.0, 0.0]

        await backend.upsert("test_ns", "perfect_match", base_emb, {"distance": 0})
        await backend.upsert("test_ns", "close_match", [0.9, 0.1, 0.0], {"distance": 0.1})
        await backend.upsert("test_ns", "farther_match", [0.8, 0.2, 0.0], {"distance": 0.2})
        await backend.upsert("test_ns", "orthogonal", [0.0, 1.0, 0.0], {"distance": 1.0})

        results = await backend.query("test_ns", base_emb, k=4)

        assert len(results) == 4
        # Results should be ordered by similarity (descending)
        assert results[0].key == "perfect_match"
        assert results[1].key == "close_match"
        assert results[2].key == "farther_match"
        assert results[3].key == "orthogonal"

        # Scores should be monotonically decreasing
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    @pytest.mark.asyncio
    async def test_k_parameter_respected(self, backend):
        """Test that k parameter limits results correctly."""
        # Insert many vectors
        for i in range(10):
            embedding = [float(i) / 10.0, 0.0, 0.0]
            await backend.upsert("test_ns", f"doc{i}", embedding, {"index": i})

        # Query with different k values
        results_k3 = await backend.query("test_ns", [0.0, 0.0, 0.0], k=3)
        results_k7 = await backend.query("test_ns", [0.0, 0.0, 0.0], k=7)

        assert len(results_k3) == 3
        assert len(results_k7) == 7

    @pytest.mark.asyncio
    async def test_metadata_preservation(self, backend):
        """Test that metadata is preserved through operations."""
        complex_metadata = {
            "text": "This is a test document",
            "timestamp": 1234567890,
            "tags": ["test", "vector", "search"],
            "nested": {"key": "value", "number": 42},
        }

        embedding = [0.5, 0.5, 0.5]
        await backend.upsert("test_ns", "complex_doc", embedding, complex_metadata)

        # Retrieve and verify
        result = await backend.get("test_ns", "complex_doc")
        assert result is not None
        _, retrieved_meta = result
        assert retrieved_meta == complex_metadata

        # Search and verify
        search_results = await backend.query("test_ns", embedding, k=1)
        assert len(search_results) == 1
        assert search_results[0].metadata == complex_metadata

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, backend):
        """Test that namespaces are properly isolated."""
        # Insert same key in different namespaces
        emb1 = [1.0, 0.0]
        emb2 = [0.0, 1.0]

        await backend.upsert("ns1", "shared_key", emb1, {"ns": "ns1"})
        await backend.upsert("ns2", "shared_key", emb2, {"ns": "ns2"})

        # Retrieve from each namespace
        result1 = await backend.get("ns1", "shared_key")
        result2 = await backend.get("ns2", "shared_key")

        assert result1 is not None
        assert result2 is not None

        emb1_ret, meta1 = result1
        emb2_ret, meta2 = result2

        assert emb1_ret == emb1
        assert emb2_ret == emb2
        assert meta1["ns"] == "ns1"
        assert meta2["ns"] == "ns2"

        # Search in each namespace
        results1 = await backend.query("ns1", emb1, k=1)
        results2 = await backend.query("ns2", emb2, k=1)

        assert len(results1) == 1
        assert len(results2) == 1
        assert results1[0].key == "shared_key"
        assert results2[0].key == "shared_key"


class TestPrometheusMetricsIntegration:
    """Test Prometheus metrics integration."""

    def test_prometheus_callback_without_client(self):
        """Test metrics callback when Prometheus client is not available."""
        metrics = VectorQueryMetrics(operation="query", duration_ms=100.0, namespace="test", result_count=5)

        # Should not raise exception
        prometheus_metrics_callback(metrics)

    def test_vector_query_metrics_structure(self):
        """Test VectorQueryMetrics data structure."""
        metrics = VectorQueryMetrics(
            operation="upsert", duration_ms=50.5, namespace="test_ns", result_count=1, error="connection_failed"
        )

        assert metrics.operation == "upsert"
        assert metrics.duration_ms == 50.5
        assert metrics.namespace == "test_ns"
        assert metrics.result_count == 1
        assert metrics.error == "connection_failed"


class TestRedisVectorBackend:
    """Test Redis vector backend (mocked)."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.jsonset.return_value = True
        mock_client.jsonget.return_value = {"embedding": [0.1, 0.2], "metadata": {"test": True}}
        mock_client.jsondelete.return_value = 1
        return mock_client

    @pytest.fixture
    def backend(self, mock_redis_client):
        """Create Redis backend with mocked client."""
        config = {"redis_url": "redis://localhost:6379"}

        mock_redis = MagicMock()
        mock_redis.Redis.from_url.return_value = mock_redis_client

        # Also mock the submodules that are imported
        mock_redis.commands = MagicMock()
        mock_redis.commands.search = MagicMock()
        mock_redis.commands.search.field = MagicMock()
        mock_redis.commands.search.indexDefinition = MagicMock()
        mock_redis.commands.search.query = MagicMock()

        with patch(
            "sys.modules",
            {
                "redis": mock_redis,
                "redis.commands": mock_redis.commands,
                "redis.commands.search": mock_redis.commands.search,
                "redis.commands.search.field": mock_redis.commands.search.field,
                "redis.commands.search.indexDefinition": mock_redis.commands.search.indexDefinition,
                "redis.commands.search.query": mock_redis.commands.search.query,
            },
        ):
            backend = RedisVectorBackend(config)
            return backend

    @pytest.mark.asyncio
    async def test_redis_health_check(self, backend):
        """Test Redis health check."""
        healthy = await backend.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_redis_upsert(self, backend):
        """Test Redis upsert operation."""
        await backend.upsert("test_ns", "doc1", [0.1, 0.2], {"test": True})
        # Should not raise exception
        assert True


class TestWeaviateVectorBackend:
    """Test Weaviate vector backend (mocked)."""

    @pytest.fixture
    def mock_weaviate_client(self):
        """Create a mock Weaviate client."""
        mock_client = MagicMock()
        mock_client.is_ready.return_value = True
        return mock_client

    @pytest.fixture
    def backend(self, mock_weaviate_client):
        """Create Weaviate backend with mocked client."""
        config = {"weaviate_url": "http://localhost:8080"}

        mock_weaviate = MagicMock()
        mock_weaviate.Client.return_value = mock_weaviate_client

        with patch("sys.modules", {"weaviate": mock_weaviate}):
            backend = WeaviateVectorBackend(config)
            return backend

    @pytest.mark.asyncio
    async def test_weaviate_health_check(self, backend):
        """Test Weaviate health check."""
        healthy = await backend.health_check()
        assert healthy is True


class TestPGVectorBackend:
    """Test PGVector backend (mocked)."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock PostgreSQL connection pool."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        # Create a proper async context manager
        class MockAsyncContextManager:
            def __init__(self, conn):
                self.conn = conn

            async def __aenter__(self):
                return self.conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_pool.acquire.return_value = MockAsyncContextManager(mock_conn)
        return mock_pool

    @pytest.fixture
    def backend(self, mock_pool):
        """Create PGVector backend with mocked pool."""
        config = {"pg_connection_string": "postgresql://user:pass@localhost:5432/db"}

        mock_asyncpg = MagicMock()

        with patch("sys.modules", {"asyncpg": mock_asyncpg}):
            backend = PGVectorBackend(config)
            # Manually set pool since asyncpg.create_pool is async
            backend.pool = mock_pool
            return backend

    @pytest.mark.asyncio
    async def test_pgvector_health_check(self, backend):
        """Test PGVector health check."""
        healthy = await backend.health_check()
        assert healthy is True
