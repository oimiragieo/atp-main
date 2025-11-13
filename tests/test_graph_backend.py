#!/usr/bin/env python3
"""Comprehensive tests for GAP-301: Graph Memory Tier Backend."""

import time
from unittest.mock import MagicMock, patch

import pytest

from tools.graph_backend import (
    GraphBackendFactory,
    GraphNode,
    GraphPath,
    GraphQueryMetrics,
    GraphQueryResult,
    GraphRelationship,
    InMemoryGraphBackend,
    Neo4jGraphBackend,
    get_graph_backend,
    prometheus_graph_metrics_callback,
)


class TestInMemoryGraphBackend:
    """Test in-memory graph backend."""

    @pytest.fixture
    def backend(self):
        """Create in-memory graph backend."""
        config = {"metrics_callback": prometheus_graph_metrics_callback}
        return InMemoryGraphBackend(config)

    @pytest.mark.asyncio
    async def test_health_check(self, backend):
        """Test health check."""
        healthy = await backend.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_create_and_get_node(self, backend):
        """Test node creation and retrieval."""
        node = GraphNode(id="test_node", labels={"Test", "Node"}, properties={"name": "Test Node", "value": 42})

        await backend.create_node(node)
        retrieved = await backend.get_node("test_node")

        assert retrieved is not None
        assert retrieved.id == "test_node"
        assert retrieved.labels == {"Test", "Node"}
        assert retrieved.properties["name"] == "Test Node"

    @pytest.mark.asyncio
    async def test_update_node(self, backend):
        """Test node updates."""
        node = GraphNode(id="update_node", labels={"Test"}, properties={"value": 1})

        await backend.create_node(node)
        await backend.update_node("update_node", {"value": 2, "new_prop": "test"})

        updated = await backend.get_node("update_node")
        assert updated.properties["value"] == 2
        assert updated.properties["new_prop"] == "test"

    @pytest.mark.asyncio
    async def test_delete_node(self, backend):
        """Test node deletion."""
        node = GraphNode(id="delete_node", labels={"Test"}, properties={})
        await backend.create_node(node)

        await backend.delete_node("delete_node")
        retrieved = await backend.get_node("delete_node")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_create_and_get_relationship(self, backend):
        """Test relationship creation and retrieval."""
        source_node = GraphNode(id="source", labels={"Source"}, properties={})
        target_node = GraphNode(id="target", labels={"Target"}, properties={})

        await backend.create_node(source_node)
        await backend.create_node(target_node)

        relationship = GraphRelationship(
            id="test_rel",
            source_id="source",
            target_id="target",
            type="CONNECTS_TO",
            properties={"weight": 0.8},
            confidence=0.9,
        )

        await backend.create_relationship(relationship)
        retrieved = await backend.get_relationship("test_rel")

        assert retrieved is not None
        assert retrieved.source_id == "source"
        assert retrieved.target_id == "target"
        assert retrieved.type == "CONNECTS_TO"
        assert retrieved.confidence == 0.9

    @pytest.mark.asyncio
    async def test_delete_relationship(self, backend):
        """Test relationship deletion."""
        # Create nodes and relationship
        source_node = GraphNode(id="source2", labels={"Source"}, properties={})
        target_node = GraphNode(id="target2", labels={"Target"}, properties={})

        await backend.create_node(source_node)
        await backend.create_node(target_node)

        relationship = GraphRelationship(
            id="delete_rel", source_id="source2", target_id="target2", type="CONNECTS_TO", properties={}
        )

        await backend.create_relationship(relationship)
        await backend.delete_relationship("delete_rel")

        retrieved = await backend.get_relationship("delete_rel")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_query_nodes_by_labels(self, backend):
        """Test querying nodes by labels."""
        node1 = GraphNode(id="node1", labels={"Person", "User"}, properties={"name": "Alice"})
        node2 = GraphNode(id="node2", labels={"Person", "Admin"}, properties={"name": "Bob"})
        node3 = GraphNode(id="node3", labels={"Document"}, properties={"title": "Doc"})

        await backend.create_node(node1)
        await backend.create_node(node2)
        await backend.create_node(node3)

        # Query by single label
        results = await backend.query_nodes(labels={"Person"})
        assert len(results.nodes) == 2

        # Query by multiple labels
        results = await backend.query_nodes(labels={"Person", "Admin"})
        assert len(results.nodes) == 1
        assert results.nodes[0].id == "node2"

    @pytest.mark.asyncio
    async def test_query_nodes_by_properties(self, backend):
        """Test querying nodes by properties."""
        node1 = GraphNode(id="prop1", labels={"Test"}, properties={"category": "A", "value": 1})
        node2 = GraphNode(id="prop2", labels={"Test"}, properties={"category": "B", "value": 2})

        await backend.create_node(node1)
        await backend.create_node(node2)

        results = await backend.query_nodes(properties={"category": "A"})
        assert len(results.nodes) == 1
        assert results.nodes[0].id == "prop1"

    @pytest.mark.asyncio
    async def test_query_relationships(self, backend):
        """Test querying relationships."""
        # Create nodes
        await backend.create_node(GraphNode(id="q1", labels={"Node"}, properties={}))
        await backend.create_node(GraphNode(id="q2", labels={"Node"}, properties={}))
        await backend.create_node(GraphNode(id="q3", labels={"Node"}, properties={}))

        # Create relationships
        rel1 = GraphRelationship(id="r1", source_id="q1", target_id="q2", type="FOLLOWS", properties={})
        rel2 = GraphRelationship(id="r2", source_id="q2", target_id="q3", type="FOLLOWS", properties={})
        rel3 = GraphRelationship(id="r3", source_id="q1", target_id="q3", type="LIKES", properties={})

        await backend.create_relationship(rel1)
        await backend.create_relationship(rel2)
        await backend.create_relationship(rel3)

        # Query by source
        results = await backend.query_relationships(source_id="q1")
        assert len(results.relationships) == 2

        # Query by type
        results = await backend.query_relationships(relationship_type="FOLLOWS")
        assert len(results.relationships) == 2

        # Query by source and type
        results = await backend.query_relationships(source_id="q1", relationship_type="LIKES")
        assert len(results.relationships) == 1

    @pytest.mark.asyncio
    async def test_find_paths(self, backend):
        """Test path finding between nodes."""
        # Create a simple graph: A -> B -> C
        await backend.create_node(GraphNode(id="A", labels={"Node"}, properties={}))
        await backend.create_node(GraphNode(id="B", labels={"Node"}, properties={}))
        await backend.create_node(GraphNode(id="C", labels={"Node"}, properties={}))

        await backend.create_relationship(
            GraphRelationship(id="AB", source_id="A", target_id="B", type="CONNECTS", properties={}, confidence=1.0)
        )
        await backend.create_relationship(
            GraphRelationship(id="BC", source_id="B", target_id="C", type="CONNECTS", properties={}, confidence=1.0)
        )

        paths = await backend.find_paths("A", "C", max_depth=3)
        assert len(paths) == 1
        assert len(paths[0].nodes) == 3  # A, B, C
        assert len(paths[0].relationships) == 2  # AB, BC

    @pytest.mark.asyncio
    async def test_get_neighbors(self, backend):
        """Test getting neighboring nodes."""
        # Create nodes
        await backend.create_node(GraphNode(id="center", labels={"Center"}, properties={}))
        await backend.create_node(GraphNode(id="neighbor1", labels={"Neighbor"}, properties={}))
        await backend.create_node(GraphNode(id="neighbor2", labels={"Neighbor"}, properties={}))

        # Create relationships
        await backend.create_relationship(
            GraphRelationship(id="c1", source_id="center", target_id="neighbor1", type="CONNECTS", properties={})
        )
        await backend.create_relationship(
            GraphRelationship(id="c2", source_id="center", target_id="neighbor2", type="CONNECTS", properties={})
        )

        neighbors = await backend.get_neighbors("center")
        assert len(neighbors.nodes) == 2
        assert len(neighbors.relationships) == 2

        neighbor_ids = {node.id for node in neighbors.nodes}
        assert neighbor_ids == {"neighbor1", "neighbor2"}

    @pytest.mark.asyncio
    async def test_clear_backend(self, backend):
        """Test clearing the backend."""
        # Create some data
        await backend.create_node(GraphNode(id="clear_test", labels={"Test"}, properties={}))
        await backend.create_relationship(
            GraphRelationship(
                id="clear_rel", source_id="clear_test", target_id="clear_test", type="SELF", properties={}
            )
        )

        # Clear
        await backend.clear()

        # Verify empty
        nodes = await backend.query_nodes()
        relationships = await backend.query_relationships()
        assert len(nodes.nodes) == 0
        assert len(relationships.relationships) == 0

    @pytest.mark.asyncio
    async def test_error_handling(self, backend):
        """Test error handling for invalid operations."""
        # Try to get non-existent node
        node = await backend.get_node("nonexistent")
        assert node is None

        # Try to create duplicate node
        node = GraphNode(id="dup", labels={"Test"}, properties={})
        await backend.create_node(node)

        with pytest.raises(ValueError, match="already exists"):
            await backend.create_node(node)

        # Try to delete non-existent node
        with pytest.raises(ValueError, match="not found"):
            await backend.delete_node("nonexistent")

        # Try to create relationship with non-existent nodes
        with pytest.raises(ValueError, match="not found"):
            await backend.create_relationship(
                GraphRelationship(
                    id="bad_rel", source_id="nonexistent", target_id="dup", type="CONNECTS", properties={}
                )
            )


class TestNeo4jGraphBackend:
    """Test Neo4j graph backend (mocked)."""

    @pytest.fixture
    def backend(self):
        """Create Neo4j backend with mocked driver."""
        config = {"neo4j_uri": "neo4j://localhost:7687", "metrics_callback": prometheus_graph_metrics_callback}

        # Create backend without mocking imports for now
        backend = Neo4jGraphBackend(config)
        return backend

    @pytest.mark.asyncio
    async def test_health_check_without_driver(self, backend):
        """Test health check without driver."""
        backend.driver = None
        healthy = await backend.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_operations_without_driver(self, backend):
        """Test that operations fail gracefully without driver."""
        backend.driver = None

        with pytest.raises(RuntimeError, match="Neo4j driver not available"):
            await backend.create_node(GraphNode(id="test", labels=set(), properties={}))

        with pytest.raises(RuntimeError, match="Neo4j driver not available"):
            await backend.get_node("test")

        with pytest.raises(RuntimeError, match="Neo4j driver not available"):
            await backend.query_nodes()


class TestGraphBackendFactory:
    """Test graph backend factory."""

    def test_create_memory_backend(self):
        """Test creating memory backend."""
        config = {"test": "config"}
        backend = GraphBackendFactory.create_memory_backend(config)
        assert isinstance(backend, InMemoryGraphBackend)
        assert backend.config == config

    def test_create_neo4j_backend(self):
        """Test creating Neo4j backend."""
        config = {"neo4j_uri": "neo4j://localhost:7687"}
        backend = GraphBackendFactory.create_neo4j_backend(config)
        assert isinstance(backend, Neo4jGraphBackend)
        assert backend.config == config

    def test_create_backend_by_type(self):
        """Test creating backend by type string."""
        # Memory backend
        backend = GraphBackendFactory.create_backend("memory", {})
        assert isinstance(backend, InMemoryGraphBackend)

        # Neo4j backend
        backend = GraphBackendFactory.create_backend("neo4j", {"neo4j_uri": "neo4j://localhost:7687"})
        assert isinstance(backend, Neo4jGraphBackend)

        # Invalid type
        with pytest.raises(ValueError, match="Unknown graph backend type"):
            GraphBackendFactory.create_backend("invalid", {})


class TestGraphBackendContextManager:
    """Test graph backend context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_memory(self):
        """Test context manager with memory backend."""
        async with get_graph_backend("memory", {"test": "config"}) as backend:
            assert isinstance(backend, InMemoryGraphBackend)
            assert backend.config["test"] == "config"

            # Test basic functionality
            healthy = await backend.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_context_manager_neo4j(self):
        """Test context manager with Neo4j backend."""
        config = {"neo4j_uri": "neo4j://localhost:7687"}
        async with get_graph_backend("neo4j", config) as backend:
            assert isinstance(backend, Neo4jGraphBackend)
            assert backend.config == config


class TestGraphQueryResult:
    """Test GraphQueryResult dataclass."""

    def test_creation(self):
        """Test GraphQueryResult creation."""
        nodes = [GraphNode(id="n1", labels=set(), properties={})]
        relationships = [GraphRelationship(id="r1", source_id="n1", target_id="n2", type="TEST", properties={})]
        paths = [GraphPath(nodes=nodes, relationships=relationships)]

        result = GraphQueryResult(nodes=nodes, relationships=relationships, paths=paths)

        assert len(result.nodes) == 1
        assert len(result.relationships) == 1
        assert len(result.paths) == 1

    def test_default_paths(self):
        """Test that paths defaults to empty list."""
        result = GraphQueryResult(nodes=[], relationships=[])
        assert result.paths == []


class TestGraphPath:
    """Test GraphPath dataclass."""

    def test_creation(self):
        """Test GraphPath creation."""
        nodes = [GraphNode(id="n1", labels=set(), properties={}), GraphNode(id="n2", labels=set(), properties={})]
        relationships = [GraphRelationship(id="r1", source_id="n1", target_id="n2", type="CONNECTS", properties={})]

        path = GraphPath(nodes=nodes, relationships=relationships, total_confidence=0.8)

        assert len(path.nodes) == 2
        assert len(path.relationships) == 1
        assert path.total_confidence == 0.8


class TestGraphNode:
    """Test GraphNode dataclass."""

    def test_creation(self):
        """Test GraphNode creation."""
        node = GraphNode(id="test_node", labels={"Person", "User"}, properties={"name": "Alice", "age": 30})

        assert node.id == "test_node"
        assert node.labels == {"Person", "User"}
        assert node.properties["name"] == "Alice"
        assert isinstance(node.created_at, float)

    def test_auto_created_at(self):
        """Test that created_at is auto-set."""
        before = time.time()
        node = GraphNode(id="test", labels=set(), properties={})
        after = time.time()

        assert before <= node.created_at <= after


class TestGraphRelationship:
    """Test GraphRelationship dataclass."""

    def test_creation(self):
        """Test GraphRelationship creation."""
        relationship = GraphRelationship(
            id="test_rel",
            source_id="source",
            target_id="target",
            type="FOLLOWS",
            properties={"since": "2023"},
            confidence=0.9,
        )

        assert relationship.id == "test_rel"
        assert relationship.source_id == "source"
        assert relationship.target_id == "target"
        assert relationship.type == "FOLLOWS"
        assert relationship.confidence == 0.9
        assert isinstance(relationship.created_at, float)


class TestGraphQueryMetrics:
    """Test GraphQueryMetrics dataclass."""

    def test_creation(self):
        """Test GraphQueryMetrics creation."""
        metrics = GraphQueryMetrics(
            operation="query_nodes",
            duration_ms=150.5,
            node_count=5,
            relationship_count=3,
            path_count=2,
            error="test error",
        )

        assert metrics.operation == "query_nodes"
        assert metrics.duration_ms == 150.5
        assert metrics.node_count == 5
        assert metrics.relationship_count == 3
        assert metrics.path_count == 2
        assert metrics.error == "test error"

    def test_defaults(self):
        """Test default values."""
        metrics = GraphQueryMetrics(operation="test", duration_ms=100.0)

        assert metrics.node_count == 0
        assert metrics.relationship_count == 0
        assert metrics.path_count == 0
        assert metrics.error is None


class TestPrometheusGraphMetricsIntegration:
    """Test Prometheus metrics integration."""

    def test_prometheus_callback_without_client(self):
        """Test that callback works without prometheus client."""
        metrics = GraphQueryMetrics(operation="test_operation", duration_ms=100.0, node_count=5)

        # Should not raise exception
        prometheus_graph_metrics_callback(metrics)

    def test_prometheus_callback_with_client(self):
        """Test callback with mocked prometheus client."""
        with patch("builtins.__import__") as mock_import:
            # Mock the prometheus_client module
            mock_prometheus = MagicMock()

            # Mock metric classes
            mock_histogram_class = MagicMock()
            mock_counter_class = MagicMock()
            mock_gauge_class = MagicMock()

            mock_prometheus.Histogram = mock_histogram_class
            mock_prometheus.Counter = mock_counter_class
            mock_prometheus.Gauge = mock_gauge_class

            # Setup mock metric instances
            mock_duration_hist = MagicMock()
            mock_nodes_gauge = MagicMock()
            mock_relationships_gauge = MagicMock()
            mock_paths_counter = MagicMock()
            mock_errors_counter = MagicMock()

            # Configure return values for metric creation
            mock_histogram_class.return_value = mock_duration_hist
            mock_gauge_class.side_effect = [mock_nodes_gauge, mock_relationships_gauge]
            mock_counter_class.side_effect = [mock_paths_counter, mock_errors_counter]

            # Mock the import to return our mock module
            def mock_import_func(name, *args, **kwargs):
                if name == "prometheus_client":
                    return mock_prometheus
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = mock_import_func

            metrics = GraphQueryMetrics(
                operation="query_nodes",
                duration_ms=200.0,
                node_count=10,
                relationship_count=5,
                path_count=2,
                error="test error",
            )

            prometheus_graph_metrics_callback(metrics)

            # Verify metrics were created with correct parameters
            mock_histogram_class.assert_called_with(
                "graph_operation_duration_seconds", "Duration of graph operations", ["operation"]
            )
            mock_gauge_class.assert_any_call("graph_nodes_total", "Total number of nodes in graph")
            mock_gauge_class.assert_any_call("graph_relationships_total", "Total number of relationships in graph")
            mock_counter_class.assert_any_call("graph_paths_found_total", "Total number of paths found")
            mock_counter_class.assert_any_call(
                "graph_operation_errors_total", "Total number of graph operation errors", ["operation"]
            )

            # Verify metrics were recorded
            mock_duration_hist.labels.assert_called_with(operation="query_nodes")
            mock_duration_hist.labels().observe.assert_called_with(0.2)

            mock_nodes_gauge.set.assert_called_with(10)
            mock_relationships_gauge.set.assert_called_with(5)
            mock_paths_counter.inc.assert_called_with(2)
            mock_errors_counter.labels.assert_called_with(operation="query_nodes")
            mock_errors_counter.labels().inc.assert_called_with()
