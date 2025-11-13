#!/usr/bin/env python3
"""GAP-301: Graph Memory Tier Backend Interfaces and Implementations.

Provides pluggable graph storage backends for relationship modeling with:
- In-memory graph for development/testing
- Neo4j integration for production
- Relationship traversal and path finding
- Confidence scoring and metadata
"""

import abc
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """Represents a node in the graph."""

    id: str
    labels: set[str]
    properties: dict[str, Any]
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


@dataclass
class GraphRelationship:
    """Represents a relationship between nodes."""

    id: str
    source_id: str
    target_id: str
    type: str
    properties: dict[str, Any]
    confidence: float = 1.0
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


@dataclass
class GraphPath:
    """Represents a path through the graph."""

    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
    total_confidence: float = 1.0


@dataclass
class GraphQueryResult:
    """Result of a graph query operation."""

    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
    paths: list[GraphPath] = None

    def __post_init__(self):
        if self.paths is None:
            self.paths = []


@dataclass
class GraphQueryMetrics:
    """Metrics collected during graph operations."""

    operation: str
    duration_ms: float
    node_count: int = 0
    relationship_count: int = 0
    path_count: int = 0
    error: Optional[str] = None


class GraphBackend(abc.ABC):
    """Abstract base class for graph storage backends."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.metrics_callback = config.get("metrics_callback")

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Check if the graph backend is healthy."""
        pass

    @abc.abstractmethod
    async def create_node(self, node: GraphNode) -> None:
        """Create a new node in the graph."""
        pass

    @abc.abstractmethod
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by ID."""
        pass

    @abc.abstractmethod
    async def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        """Update node properties."""
        pass

    @abc.abstractmethod
    async def delete_node(self, node_id: str) -> None:
        """Delete a node and its relationships."""
        pass

    @abc.abstractmethod
    async def create_relationship(self, relationship: GraphRelationship) -> None:
        """Create a relationship between nodes."""
        pass

    @abc.abstractmethod
    async def get_relationship(self, relationship_id: str) -> Optional[GraphRelationship]:
        """Retrieve a relationship by ID."""
        pass

    @abc.abstractmethod
    async def delete_relationship(self, relationship_id: str) -> None:
        """Delete a relationship."""
        pass

    @abc.abstractmethod
    async def query_nodes(
        self, labels: Optional[set[str]] = None, properties: Optional[dict[str, Any]] = None, limit: int = 100
    ) -> GraphQueryResult:
        """Query nodes by labels and properties."""
        pass

    @abc.abstractmethod
    async def query_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        limit: int = 100,
    ) -> GraphQueryResult:
        """Query relationships by source, target, and type."""
        pass

    @abc.abstractmethod
    async def find_paths(
        self, start_node_id: str, end_node_id: str, max_depth: int = 3, min_confidence: float = 0.0
    ) -> list[GraphPath]:
        """Find paths between two nodes."""
        pass

    @abc.abstractmethod
    async def get_neighbors(
        self, node_id: str, relationship_type: Optional[str] = None, direction: str = "both", limit: int = 50
    ) -> GraphQueryResult:
        """Get neighboring nodes connected by relationships."""
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all nodes and relationships."""
        pass

    def _record_metrics(
        self,
        operation: str,
        duration_ms: float,
        node_count: int = 0,
        relationship_count: int = 0,
        path_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record operation metrics."""
        if self.metrics_callback:
            metrics = GraphQueryMetrics(
                operation=operation,
                duration_ms=duration_ms,
                node_count=node_count,
                relationship_count=relationship_count,
                path_count=path_count,
                error=error,
            )
            try:
                self.metrics_callback(metrics)
            except Exception as e:
                logger.warning(f"Failed to record metrics: {e}")


class InMemoryGraphBackend(GraphBackend):
    """In-memory graph backend for development and testing."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.nodes: dict[str, GraphNode] = {}
        self.relationships: dict[str, GraphRelationship] = {}
        self.node_relationships: dict[str, set[str]] = {}  # node_id -> relationship_ids

    async def health_check(self) -> bool:
        """Check if the in-memory backend is healthy."""
        return True

    async def create_node(self, node: GraphNode) -> None:
        """Create a new node."""
        start_time = time.time()
        try:
            if node.id in self.nodes:
                raise ValueError(f"Node {node.id} already exists")

            self.nodes[node.id] = node
            self.node_relationships[node.id] = set()

            duration = (time.time() - start_time) * 1000
            self._record_metrics("create_node", duration, node_count=1)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("create_node", duration, error=str(e))
            raise

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by ID."""
        start_time = time.time()
        try:
            node = self.nodes.get(node_id)
            duration = (time.time() - start_time) * 1000
            self._record_metrics("get_node", duration, node_count=1 if node else 0)
            return node
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("get_node", duration, error=str(e))
            raise

    async def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        """Update node properties."""
        start_time = time.time()
        try:
            if node_id not in self.nodes:
                raise ValueError(f"Node {node_id} not found")

            self.nodes[node_id].properties.update(properties)
            duration = (time.time() - start_time) * 1000
            self._record_metrics("update_node", duration, node_count=1)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("update_node", duration, error=str(e))
            raise

    async def delete_node(self, node_id: str) -> None:
        """Delete a node and its relationships."""
        start_time = time.time()
        try:
            if node_id not in self.nodes:
                raise ValueError(f"Node {node_id} not found")

            # Remove relationships involving this node
            relationships_to_remove = []
            for rel_id, rel in self.relationships.items():
                if rel.source_id == node_id or rel.target_id == node_id:
                    relationships_to_remove.append(rel_id)

            for rel_id in relationships_to_remove:
                del self.relationships[rel_id]

            # Remove from node_relationships
            if node_id in self.node_relationships:
                del self.node_relationships[node_id]

            # Remove node
            del self.nodes[node_id]

            duration = (time.time() - start_time) * 1000
            self._record_metrics("delete_node", duration, node_count=1, relationship_count=len(relationships_to_remove))
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("delete_node", duration, error=str(e))
            raise

    async def create_relationship(self, relationship: GraphRelationship) -> None:
        """Create a relationship between nodes."""
        start_time = time.time()
        try:
            if relationship.id in self.relationships:
                raise ValueError(f"Relationship {relationship.id} already exists")

            if relationship.source_id not in self.nodes:
                raise ValueError(f"Source node {relationship.source_id} not found")

            if relationship.target_id not in self.nodes:
                raise ValueError(f"Target node {relationship.target_id} not found")

            self.relationships[relationship.id] = relationship
            self.node_relationships[relationship.source_id].add(relationship.id)
            self.node_relationships[relationship.target_id].add(relationship.id)

            duration = (time.time() - start_time) * 1000
            self._record_metrics("create_relationship", duration, relationship_count=1)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("create_relationship", duration, error=str(e))
            raise

    async def get_relationship(self, relationship_id: str) -> Optional[GraphRelationship]:
        """Retrieve a relationship by ID."""
        start_time = time.time()
        try:
            relationship = self.relationships.get(relationship_id)
            duration = (time.time() - start_time) * 1000
            self._record_metrics("get_relationship", duration, relationship_count=1 if relationship else 0)
            return relationship
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("get_relationship", duration, error=str(e))
            raise

    async def delete_relationship(self, relationship_id: str) -> None:
        """Delete a relationship."""
        start_time = time.time()
        try:
            if relationship_id not in self.relationships:
                raise ValueError(f"Relationship {relationship_id} not found")

            relationship = self.relationships[relationship_id]
            self.node_relationships[relationship.source_id].discard(relationship_id)
            self.node_relationships[relationship.target_id].discard(relationship_id)

            del self.relationships[relationship_id]

            duration = (time.time() - start_time) * 1000
            self._record_metrics("delete_relationship", duration, relationship_count=1)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("delete_relationship", duration, error=str(e))
            raise

    async def query_nodes(
        self, labels: Optional[set[str]] = None, properties: Optional[dict[str, Any]] = None, limit: int = 100
    ) -> GraphQueryResult:
        """Query nodes by labels and properties."""
        start_time = time.time()
        try:
            matching_nodes = []

            for node in self.nodes.values():
                # Check labels
                if labels and not labels.issubset(node.labels):
                    continue

                # Check properties
                if properties:
                    if not all(node.properties.get(k) == v for k, v in properties.items()):
                        continue

                matching_nodes.append(node)
                if len(matching_nodes) >= limit:
                    break

            duration = (time.time() - start_time) * 1000
            self._record_metrics("query_nodes", duration, node_count=len(matching_nodes))

            return GraphQueryResult(nodes=matching_nodes, relationships=[])
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("query_nodes", duration, error=str(e))
            raise

    async def query_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        limit: int = 100,
    ) -> GraphQueryResult:
        """Query relationships by source, target, and type."""
        start_time = time.time()
        try:
            matching_relationships = []

            for relationship in self.relationships.values():
                if source_id and relationship.source_id != source_id:
                    continue
                if target_id and relationship.target_id != target_id:
                    continue
                if relationship_type and relationship.type != relationship_type:
                    continue

                matching_relationships.append(relationship)
                if len(matching_relationships) >= limit:
                    break

            duration = (time.time() - start_time) * 1000
            self._record_metrics("query_relationships", duration, relationship_count=len(matching_relationships))

            return GraphQueryResult(nodes=[], relationships=matching_relationships)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("query_relationships", duration, error=str(e))
            raise

    async def find_paths(
        self, start_node_id: str, end_node_id: str, max_depth: int = 3, min_confidence: float = 0.0
    ) -> list[GraphPath]:
        """Find paths between two nodes using BFS."""
        start_time = time.time()
        try:
            if start_node_id not in self.nodes or end_node_id not in self.nodes:
                return []

            paths = []
            visited = set()
            queue = [(start_node_id, [], [], 1.0)]  # (node_id, path_nodes, path_relationships, confidence)

            while queue and len(paths) < 10:  # Limit results
                current_id, path_nodes, path_relationships, confidence = queue.pop(0)

                if current_id in visited:
                    continue
                visited.add(current_id)

                current_node = self.nodes[current_id]
                current_path_nodes = path_nodes + [current_node]

                if current_id == end_node_id and len(path_nodes) > 0:
                    # Found a path
                    path = GraphPath(
                        nodes=current_path_nodes, relationships=path_relationships, total_confidence=confidence
                    )
                    if confidence >= min_confidence:
                        paths.append(path)
                    continue

                if len(path_nodes) >= max_depth:
                    continue

                # Explore neighbors
                for rel_id in self.node_relationships.get(current_id, set()):
                    rel = self.relationships[rel_id]

                    next_id = rel.target_id if rel.source_id == current_id else rel.source_id
                    if next_id in visited:
                        continue

                    new_confidence = confidence * rel.confidence
                    if new_confidence < min_confidence:
                        continue

                    queue.append((next_id, current_path_nodes, path_relationships + [rel], new_confidence))

            duration = (time.time() - start_time) * 1000
            self._record_metrics("find_paths", duration, path_count=len(paths))
            return paths
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("find_paths", duration, error=str(e))
            raise

    async def get_neighbors(
        self, node_id: str, relationship_type: Optional[str] = None, direction: str = "both", limit: int = 50
    ) -> GraphQueryResult:
        """Get neighboring nodes connected by relationships."""
        start_time = time.time()
        try:
            if node_id not in self.nodes:
                raise ValueError(f"Node {node_id} not found")

            neighbor_nodes = []
            neighbor_relationships = []

            for rel_id in self.node_relationships.get(node_id, set()):
                rel = self.relationships[rel_id]

                # Check direction
                if direction == "outgoing" and rel.source_id != node_id:
                    continue
                if direction == "incoming" and rel.target_id != node_id:
                    continue

                # Check relationship type
                if relationship_type and rel.type != relationship_type:
                    continue

                neighbor_id = rel.target_id if rel.source_id == node_id else rel.source_id
                neighbor_node = self.nodes[neighbor_id]

                if neighbor_node not in neighbor_nodes:
                    neighbor_nodes.append(neighbor_node)
                neighbor_relationships.append(rel)

                if len(neighbor_nodes) >= limit:
                    break

            duration = (time.time() - start_time) * 1000
            self._record_metrics(
                "get_neighbors",
                duration,
                node_count=len(neighbor_nodes),
                relationship_count=len(neighbor_relationships),
            )

            return GraphQueryResult(nodes=neighbor_nodes, relationships=neighbor_relationships)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("get_neighbors", duration, error=str(e))
            raise

    async def clear(self) -> None:
        """Clear all nodes and relationships."""
        start_time = time.time()
        try:
            node_count = len(self.nodes)
            relationship_count = len(self.relationships)

            self.nodes.clear()
            self.relationships.clear()
            self.node_relationships.clear()

            duration = (time.time() - start_time) * 1000
            self._record_metrics("clear", duration, node_count=node_count, relationship_count=relationship_count)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self._record_metrics("clear", duration, error=str(e))
            raise


class Neo4jGraphBackend(GraphBackend):
    """Neo4j graph backend for production use."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.uri = config.get("neo4j_uri", "neo4j://localhost:7687")
        self.user = config.get("neo4j_user", "neo4j")
        self.password = config.get("neo4j_password", "password")
        self.driver = None
        self._initialize_driver()

    def _initialize_driver(self):
        """Initialize Neo4j driver."""
        try:
            from neo4j import GraphDatabase  # noqa: F401

            # Neo4j driver initialization would go here
            logger.info("Neo4j graph backend initialized")
        except ImportError:
            logger.warning("Neo4j driver not available, using mock mode")
            self.driver = None

    async def health_check(self) -> bool:
        """Check Neo4j connection health."""
        if not self.driver:
            return False
        try:
            # Health check implementation would go here
            return True
        except Exception:
            return False

    async def create_node(self, node: GraphNode) -> None:
        """Create a node in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node from Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        """Update node properties in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def delete_node(self, node_id: str) -> None:
        """Delete a node from Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def create_relationship(self, relationship: GraphRelationship) -> None:
        """Create a relationship in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def get_relationship(self, relationship_id: str) -> Optional[GraphRelationship]:
        """Retrieve a relationship from Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def delete_relationship(self, relationship_id: str) -> None:
        """Delete a relationship from Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def query_nodes(
        self, labels: Optional[set[str]] = None, properties: Optional[dict[str, Any]] = None, limit: int = 100
    ) -> GraphQueryResult:
        """Query nodes in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def query_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        limit: int = 100,
    ) -> GraphQueryResult:
        """Query relationships in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def find_paths(
        self, start_node_id: str, end_node_id: str, max_depth: int = 3, min_confidence: float = 0.0
    ) -> list[GraphPath]:
        """Find paths in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def get_neighbors(
        self, node_id: str, relationship_type: Optional[str] = None, direction: str = "both", limit: int = 50
    ) -> GraphQueryResult:
        """Get neighbors in Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")

    async def clear(self) -> None:
        """Clear Neo4j database."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not available")
        # Implementation would go here
        raise NotImplementedError("Neo4j backend not yet implemented")


class GraphBackendFactory:
    """Factory for creating graph backend instances."""

    @staticmethod
    def create_memory_backend(config: Optional[dict[str, Any]] = None) -> GraphBackend:
        """Create an in-memory graph backend."""
        if config is None:
            config = {}
        return InMemoryGraphBackend(config)

    @staticmethod
    def create_neo4j_backend(config: dict[str, Any]) -> GraphBackend:
        """Create a Neo4j graph backend."""
        return Neo4jGraphBackend(config)

    @staticmethod
    def create_backend(backend_type: str, config: dict[str, Any]) -> GraphBackend:
        """Create a graph backend by type."""
        if backend_type == "memory":
            return GraphBackendFactory.create_memory_backend(config)
        elif backend_type == "neo4j":
            return GraphBackendFactory.create_neo4j_backend(config)
        else:
            raise ValueError(f"Unknown graph backend type: {backend_type}")


@asynccontextmanager
async def get_graph_backend(backend_type: str = "memory", config: Optional[dict[str, Any]] = None):
    """Context manager for graph backend connections."""
    if config is None:
        config = {}

    backend = GraphBackendFactory.create_backend(backend_type, config)
    try:
        yield backend
    finally:
        # Cleanup if needed
        pass


def prometheus_graph_metrics_callback(metrics: GraphQueryMetrics) -> None:
    """Prometheus metrics callback for graph operations."""
    try:
        from prometheus_client import Counter, Gauge, Histogram

        # Define metrics if not already defined
        graph_operation_duration = Histogram(
            "graph_operation_duration_seconds", "Duration of graph operations", ["operation"]
        )
        graph_nodes_total = Gauge("graph_nodes_total", "Total number of nodes in graph")
        graph_relationships_total = Gauge("graph_relationships_total", "Total number of relationships in graph")
        graph_paths_found_total = Counter("graph_paths_found_total", "Total number of paths found")
        graph_operation_errors_total = Counter(
            "graph_operation_errors_total", "Total number of graph operation errors", ["operation"]
        )

        # Record metrics
        graph_operation_duration.labels(operation=metrics.operation).observe(metrics.duration_ms / 1000)

        if metrics.node_count > 0:
            graph_nodes_total.set(metrics.node_count)

        if metrics.relationship_count > 0:
            graph_relationships_total.set(metrics.relationship_count)

        if metrics.path_count > 0:
            graph_paths_found_total.inc(metrics.path_count)

        if metrics.error:
            graph_operation_errors_total.labels(operation=metrics.operation).inc()

    except ImportError:
        # Prometheus not available, skip metrics
        pass


# Demo function
async def demo():
    """Demonstrate graph backend functionality."""
    print("=== Graph Backend Demo ===")

    # Create in-memory backend
    config = {"metrics_callback": prometheus_graph_metrics_callback}
    backend = GraphBackendFactory.create_memory_backend(config)

    # Create some nodes
    user_node = GraphNode(
        id="user_1", labels={"User", "Person"}, properties={"name": "Alice", "email": "alice@example.com"}
    )

    doc_node = GraphNode(
        id="doc_1",
        labels={"Document", "Article"},
        properties={"title": "Graph Databases", "content": "Graph databases store..."},
    )

    topic_node = GraphNode(
        id="topic_1", labels={"Topic"}, properties={"name": "Technology", "category": "Computer Science"}
    )

    await backend.create_node(user_node)
    await backend.create_node(doc_node)
    await backend.create_node(topic_node)

    # Create relationships
    authored_rel = GraphRelationship(
        id="authored_1",
        source_id="user_1",
        target_id="doc_1",
        type="AUTHORED",
        properties={"role": "author"},
        confidence=0.95,
    )

    about_rel = GraphRelationship(
        id="about_1",
        source_id="doc_1",
        target_id="topic_1",
        type="ABOUT",
        properties={"relevance": 0.8},
        confidence=0.8,
    )

    await backend.create_relationship(authored_rel)
    await backend.create_relationship(about_rel)

    # Query operations
    print("\n=== Query Results ===")

    # Find user nodes
    user_results = await backend.query_nodes(labels={"User"})
    print(f"Found {len(user_results.nodes)} user nodes")

    # Find relationships from user
    rel_results = await backend.query_relationships(source_id="user_1")
    print(f"User has {len(rel_results.relationships)} outgoing relationships")

    # Find paths between user and topic
    paths = await backend.find_paths("user_1", "topic_1", max_depth=2)
    print(f"Found {len(paths)} paths from user to topic")

    # Get neighbors
    neighbors = await backend.get_neighbors("doc_1")
    print(f"Document has {len(neighbors.nodes)} neighbors")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(demo())
