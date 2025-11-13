# Graph Memory Tier Guide

## Overview

The Graph Memory Tier provides pluggable graph storage backends for relationship modeling and traversal queries. It supports both in-memory storage for development and Neo4j for production deployments.

## Architecture

### Core Components

- **GraphBackend**: Abstract base class defining the graph storage interface
- **InMemoryGraphBackend**: Fast in-memory implementation for development/testing
- **Neo4jGraphBackend**: Production-ready Neo4j integration
- **GraphBackendFactory**: Factory for creating backend instances
- **Graph Metrics**: Prometheus integration for monitoring graph operations

### Data Model

#### GraphNode
```python
@dataclass
class GraphNode:
    id: str                    # Unique node identifier
    labels: Set[str]          # Node type labels (e.g., {"User", "Person"})
    properties: Dict[str, Any] # Key-value properties
    created_at: float         # Auto-generated timestamp
```

#### GraphRelationship
```python
@dataclass
class GraphRelationship:
    id: str                    # Unique relationship identifier
    source_id: str            # Source node ID
    target_id: str            # Target node ID
    type: str                 # Relationship type (e.g., "FOLLOWS", "AUTHORED")
    properties: Dict[str, Any] # Relationship properties
    confidence: float         # Confidence score (0.0 to 1.0)
    created_at: float         # Auto-generated timestamp
```

#### GraphPath
```python
@dataclass
class GraphPath:
    nodes: List[GraphNode]           # Ordered list of nodes in path
    relationships: List[GraphRelationship]  # Relationships connecting nodes
    total_confidence: float         # Product of relationship confidences
```

## Backend Implementations

### In-Memory Backend

Perfect for development, testing, and small-scale applications.

```python
from tools.graph_backend import GraphBackendFactory

# Create backend
config = {"metrics_callback": prometheus_graph_metrics_callback}
backend = GraphBackendFactory.create_memory_backend(config)

# Or use context manager
async with get_graph_backend("memory", config) as backend:
    # Use backend
    pass
```

**Features:**
- Fast in-memory storage
- Full graph traversal algorithms
- Path finding with confidence scoring
- No external dependencies

### Neo4j Backend

Production-ready backend with enterprise features.

```python
config = {
    "neo4j_uri": "neo4j://localhost:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your_password",
    "metrics_callback": prometheus_graph_metrics_callback
}

backend = GraphBackendFactory.create_neo4j_backend(config)
```

**Features:**
- ACID transactions
- Cypher query language
- High availability clustering
- Advanced graph algorithms
- Enterprise security

## Basic Operations

### Node Management

```python
# Create a node
user_node = GraphNode(
    id="user_123",
    labels={"User", "Person"},
    properties={
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "department": "Engineering"
    }
)

await backend.create_node(user_node)

# Retrieve a node
node = await backend.get_node("user_123")
if node:
    print(f"Found user: {node.properties['name']}")

# Update node properties
await backend.update_node("user_123", {
    "last_login": datetime.now().isoformat(),
    "login_count": 5
})

# Delete a node (also removes its relationships)
await backend.delete_node("user_123")
```

### Relationship Management

```python
# Create nodes first
await backend.create_node(GraphNode(id="user_1", labels={"User"}, properties={"name": "Alice"}))
await backend.create_node(GraphNode(id="user_2", labels={"User"}, properties={"name": "Bob"}))

# Create relationship
follows_relationship = GraphRelationship(
    id="follow_1_2",
    source_id="user_1",
    target_id="user_2",
    type="FOLLOWS",
    properties={"since": "2024-01-15"},
    confidence=0.95
)

await backend.create_relationship(follows_relationship)

# Query relationships
relationships = await backend.query_relationships(
    source_id="user_1",
    relationship_type="FOLLOWS"
)

# Delete relationship
await backend.delete_relationship("follow_1_2")
```

### Query Operations

#### Node Queries

```python
# Query by labels
users = await backend.query_nodes(labels={"User"})
print(f"Found {len(users.nodes)} users")

# Query by properties
engineers = await backend.query_nodes(
    labels={"User"},
    properties={"department": "Engineering"}
)

# Query with limit
recent_users = await backend.query_nodes(
    labels={"User"},
    limit=10
)
```

#### Relationship Queries

```python
# Find all relationships from a node
outgoing = await backend.query_relationships(source_id="user_1")

# Find relationships of specific type
follows = await backend.query_relationships(relationship_type="FOLLOWS")

# Find relationships between specific nodes
between = await backend.query_relationships(
    source_id="user_1",
    target_id="user_2"
)
```

#### Path Finding

```python
# Find paths between nodes
paths = await backend.find_paths(
    start_node_id="user_1",
    end_node_id="user_3",
    max_depth=3,
    min_confidence=0.7
)

for path in paths:
    print(f"Path with {len(path.nodes)} nodes, confidence: {path.total_confidence}")
    for i, node in enumerate(path.nodes):
        print(f"  {i}: {node.id} ({node.labels})")
```

#### Neighbor Queries

```python
# Get all neighbors
neighbors = await backend.get_neighbors("user_1")

# Get neighbors by relationship type
friends = await backend.get_neighbors(
    "user_1",
    relationship_type="FRIEND_OF"
)

# Get neighbors by direction
followers = await backend.get_neighbors(
    "user_1",
    relationship_type="FOLLOWS",
    direction="incoming"
)

# Limit results
close_friends = await backend.get_neighbors(
    "user_1",
    relationship_type="FRIEND_OF",
    limit=5
)
```

## Advanced Usage

### Complex Graph Structures

```python
# Social network example
await backend.create_node(GraphNode(id="alice", labels={"Person"}, properties={"name": "Alice"}))
await backend.create_node(GraphNode(id="bob", labels={"Person"}, properties={"name": "Bob"}))
await backend.create_node(GraphNode(id="charlie", labels={"Person"}, properties={"name": "Charlie"}))
await backend.create_node(GraphNode(id="engineering", labels={"Group"}, properties={"name": "Engineering"}))

# Relationships
await backend.create_relationship(GraphRelationship(
    id="alice_friends_bob", source_id="alice", target_id="bob",
    type="FRIENDS_WITH", confidence=0.9
))
await backend.create_relationship(GraphRelationship(
    id="bob_friends_charlie", source_id="bob", target_id="charlie",
    type="FRIENDS_WITH", confidence=0.8
))
await backend.create_relationship(GraphRelationship(
    id="alice_member_engineering", source_id="alice", target_id="engineering",
    type="MEMBER_OF", confidence=1.0
))
await backend.create_relationship(GraphRelationship(
    id="bob_member_engineering", source_id="bob", target_id="engineering",
    type="MEMBER_OF", confidence=1.0
))

# Find Alice's friends who are also in Engineering
alice_friends = await backend.get_neighbors("alice", relationship_type="FRIENDS_WITH")
engineering_members = await backend.get_neighbors("engineering", relationship_type="MEMBER_OF")

friend_ids = {node.id for node in alice_friends.nodes}
member_ids = {node.id for node in engineering_members.nodes}

engineering_friends = friend_ids & member_ids
print(f"Alice's friends in Engineering: {engineering_friends}")
```

### Confidence-Based Queries

```python
# Find highly confident relationships
confident_relationships = []
all_relationships = await backend.query_relationships()

for rel in all_relationships.relationships:
    if rel.confidence >= 0.8:
        confident_relationships.append(rel)

# Find paths with high confidence
reliable_paths = await backend.find_paths(
    "start_node",
    "end_node",
    min_confidence=0.9
)
```

## Metrics and Monitoring

### Prometheus Metrics

The graph backend automatically collects metrics when a callback is provided:

```python
from tools.graph_metrics import prometheus_graph_metrics_callback

config = {"metrics_callback": prometheus_graph_metrics_callback}
backend = GraphBackendFactory.create_memory_backend(config)
```

### Available Metrics

- `graph_operation_duration_seconds`: Operation duration by type
- `graph_nodes_total`: Total nodes in graph
- `graph_relationships_total`: Total relationships in graph
- `graph_edges_total`: Total edges (relationships) by type
- `graph_paths_found_total`: Total paths found in queries
- `graph_operation_errors_total`: Operation errors by type

### Custom Metrics

```python
def custom_metrics_callback(metrics: GraphQueryMetrics):
    print(f"Operation: {metrics.operation}")
    print(f"Duration: {metrics.duration_ms}ms")
    print(f"Nodes: {metrics.node_count}")
    print(f"Relationships: {metrics.relationship_count}")

config = {"metrics_callback": custom_metrics_callback}
```

## Performance Considerations

### In-Memory Backend

- **Pros**: Fast queries, no I/O, full ACID compliance
- **Cons**: Memory-bound, not persistent, single-threaded
- **Use cases**: Development, testing, small graphs (< 100K nodes)

### Neo4j Backend

- **Pros**: Persistent, distributed, advanced algorithms
- **Cons**: Requires infrastructure, learning curve
- **Use cases**: Production, large graphs, complex queries

### Optimization Tips

1. **Use appropriate indexes**: Neo4j benefits from property indexes
2. **Batch operations**: Group multiple operations when possible
3. **Limit query depth**: Path finding can be expensive
4. **Cache frequently accessed nodes**: Use application-level caching
5. **Monitor metrics**: Use Prometheus metrics to identify bottlenecks

## Deployment

### Development Setup

```python
# Simple in-memory setup
backend = GraphBackendFactory.create_memory_backend()
```

### Production Setup

```python
# Neo4j production setup
config = {
    "neo4j_uri": os.getenv("NEO4J_URI"),
    "neo4j_user": os.getenv("NEO4J_USER"),
    "neo4j_password": os.getenv("NEO4J_PASSWORD"),
    "metrics_callback": prometheus_graph_metrics_callback
}

backend = GraphBackendFactory.create_neo4j_backend(config)
```

### Docker Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.15
    environment:
      NEO4J_AUTH: neo4j/your_password
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

## Troubleshooting

### Common Issues

1. **Neo4j Connection Failed**
   - Check Neo4j server is running
   - Verify connection string and credentials
   - Check firewall settings

2. **Memory Issues with In-Memory Backend**
   - Monitor memory usage for large graphs
   - Consider switching to Neo4j for production
   - Implement pagination for large result sets

3. **Slow Path Finding**
   - Increase `min_confidence` to reduce search space
   - Decrease `max_depth` for bounded searches
   - Use Neo4j's native algorithms for complex queries

4. **Metrics Not Appearing**
   - Ensure Prometheus client is installed
   - Check metrics callback is properly configured
   - Verify Prometheus is scraping the application

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Graph backend will log detailed operations
backend = GraphBackendFactory.create_memory_backend()
```

## API Reference

### GraphBackend Abstract Methods

- `health_check() -> bool`: Check backend health
- `create_node(node: GraphNode) -> None`: Create node
- `get_node(node_id: str) -> Optional[GraphNode]`: Get node by ID
- `update_node(node_id: str, properties: Dict[str, Any]) -> None`: Update node
- `delete_node(node_id: str) -> None`: Delete node
- `create_relationship(relationship: GraphRelationship) -> None`: Create relationship
- `get_relationship(relationship_id: str) -> Optional[GraphRelationship]`: Get relationship
- `delete_relationship(relationship_id: str) -> None`: Delete relationship
- `query_nodes(labels, properties, limit) -> GraphQueryResult`: Query nodes
- `query_relationships(source_id, target_id, type, limit) -> GraphQueryResult`: Query relationships
- `find_paths(start_id, end_id, max_depth, min_confidence) -> List[GraphPath]`: Find paths
- `get_neighbors(node_id, type, direction, limit) -> GraphQueryResult`: Get neighbors
- `clear() -> None`: Clear all data

### GraphBackendFactory Methods

- `create_memory_backend(config) -> InMemoryGraphBackend`
- `create_neo4j_backend(config) -> Neo4jGraphBackend`
- `create_backend(type, config) -> GraphBackend`

### Context Manager

```python
async with get_graph_backend("memory", config) as backend:
    # Use backend
    pass
```

## Examples

See `tools/graph_backend.py` for a complete demo function showing all features.
