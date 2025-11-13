# ADR: Memory/Context Exposure via Tools

## Status
Proposed

## Context

The ATP system maintains a rich memory fabric through the Memory Gateway service, which provides key-value storage with audit logging, PII detection, quota management, and consistency levels. However, this memory is currently only accessible through direct HTTP API calls to the Memory Gateway.

We need to expose memory and context operations through the MCP (Model Context Protocol) tool interface to allow:
1. AI agents to query and manipulate memory state
2. Contextual information to be available during tool execution
3. Memory operations to be part of the tool permission and audit system

## Decision

We will implement memory/context exposure through MCP tools with the following design:

### Tool Definitions

#### 1. `listMemory` Tool
Lists memory objects in a namespace with filtering and pagination.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "namespace": {
      "type": "string",
      "description": "Memory namespace to list"
    },
    "prefix": {
      "type": "string",
      "description": "Key prefix filter (optional)"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 50,
      "description": "Maximum number of keys to return"
    },
    "cursor": {
      "type": "string",
      "description": "Pagination cursor (optional)"
    }
  },
  "required": ["namespace"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "keys": {
      "type": "array",
      "items": {"type": "string"},
      "description": "List of memory keys"
    },
    "cursor": {
      "type": "string",
      "description": "Next page cursor (null if no more results)"
    },
    "total": {
      "type": "integer",
      "description": "Total number of keys in namespace"
    }
  }
}
```

#### 2. `getContext` Tool
Retrieves contextual information for the current session/agent.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "context_type": {
      "type": "string",
      "enum": ["session", "agent", "task", "all"],
      "default": "all",
      "description": "Type of context to retrieve"
    },
    "include_history": {
      "type": "boolean",
      "default": false,
      "description": "Include historical context"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "session_id": {"type": "string"},
    "agent_id": {"type": "string"},
    "task_id": {"type": "string"},
    "start_time": {"type": "string", "format": "date-time"},
    "memory_usage": {
      "type": "object",
      "properties": {
        "tokens_used": {"type": "integer"},
        "usd_spent": {"type": "number"}
      }
    },
    "tool_history": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tool_name": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"},
          "success": {"type": "boolean"}
        }
      }
    }
  }
}
```

#### 3. `putMemory` Tool
Stores data in memory with validation and audit.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "namespace": {
      "type": "string",
      "description": "Memory namespace"
    },
    "key": {
      "type": "string",
      "description": "Memory key"
    },
    "value": {
      "description": "Value to store (any JSON-serializable data)"
    },
    "ttl_seconds": {
      "type": "integer",
      "minimum": 0,
      "description": "Time-to-live in seconds (optional)"
    }
  },
  "required": ["namespace", "key", "value"]
}
```

### Security & Access Control

#### Permission Model
- **Namespace-level permissions**: Tools can only access authorized namespaces
- **Operation-level permissions**: Separate permissions for read/write operations
- **PII filtering**: Automatic redaction of sensitive data in tool responses
- **Audit logging**: All memory operations through tools are logged

#### Permission Configuration
```yaml
tool_permissions:
  listMemory:
    allowed_namespaces: ["session.*", "agent.*", "public.*"]
    operations: ["read"]
  getContext:
    allowed_context_types: ["session", "agent", "task"]
    operations: ["read"]
  putMemory:
    allowed_namespaces: ["session.*", "agent.*"]
    operations: ["write"]
    max_ttl_seconds: 3600
```

### Implementation Architecture

#### Tool Handler Integration
```python
class MemoryTools:
    def __init__(self, memory_gateway_url: str, permission_checker: PermissionChecker):
        self.gateway = MemoryGatewayClient(memory_gateway_url)
        self.permissions = permission_checker

    async def list_memory(self, args: dict) -> dict:
        # Check permissions
        if not self.permissions.check_namespace_access(args["namespace"], "read"):
            raise PermissionError("Access denied to namespace")

        # Call memory gateway
        response = await self.gateway.list_keys(
            namespace=args["namespace"],
            prefix=args.get("prefix"),
            limit=args.get("limit", 50)
        )

        # Apply PII filtering
        filtered_keys = self._filter_pii_keys(response["keys"])

        return {
            "keys": filtered_keys,
            "cursor": response.get("cursor"),
            "total": response.get("total", len(filtered_keys))
        }

    async def get_context(self, args: dict) -> dict:
        context_type = args.get("context_type", "all")
        include_history = args.get("include_history", False)

        # Gather context from various sources
        context = {
            "session_id": self._get_session_id(),
            "agent_id": self._get_agent_id(),
            "task_id": self._get_task_id(),
            "start_time": self._get_session_start_time(),
            "memory_usage": await self._get_memory_usage()
        }

        if include_history:
            context["tool_history"] = await self._get_tool_history()

        return context

    async def put_memory(self, args: dict) -> dict:
        # Validate and check permissions
        self._validate_memory_data(args["value"])
        if not self.permissions.check_namespace_access(args["namespace"], "write"):
            raise PermissionError("Write access denied to namespace")

        # Store in memory gateway
        await self.gateway.put(
            namespace=args["namespace"],
            key=args["key"],
            value=args["value"],
            ttl_seconds=args.get("ttl_seconds")
        )

        return {"success": True}
```

### Error Handling

#### Standard Error Responses
```json
{
  "type": "error",
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Access denied to namespace 'sensitive'",
    "details": {"namespace": "sensitive", "operation": "read"}
  }
}
```

```json
{
  "type": "error",
  "error": {
    "code": "PII_DETECTED",
    "message": "PII detected in memory operation",
    "details": {"redacted_fields": ["email", "phone"]}
  }
}
```

### Performance Considerations

#### Caching Strategy
- **Tool response caching**: Cache frequent context queries for 30 seconds
- **Permission caching**: Cache permission checks for 5 minutes
- **Memory gateway connection pooling**: Reuse connections to avoid overhead

#### Rate Limiting
- **Per-tool limits**: Different limits for different tools
- **Per-namespace limits**: Prevent abuse of specific namespaces
- **Burst handling**: Allow short bursts but enforce sustained limits

### Monitoring & Observability

#### Metrics
- `memory_tool_requests_total{tool_name, namespace, status}`
- `memory_tool_latency_seconds{tool_name, quantile}`
- `memory_tool_permission_denies_total{tool_name, reason}`
- `memory_tool_pii_redactions_total{tool_name}`

#### Tracing
- Tool execution spans with memory operation details
- Permission check spans
- PII filtering spans

## Consequences

### Positive
- **Unified access**: Memory operations available through MCP tool interface
- **Security**: Tool-level permissions and audit logging
- **Flexibility**: AI agents can use memory as part of their reasoning
- **Observability**: Memory operations tracked through tool metrics

### Negative
- **Complexity**: Additional layer between direct API and tool interface
- **Latency**: Tool invocation overhead vs direct API calls
- **Permission complexity**: Managing tool + namespace permissions

### Risks
- **Security gaps**: Tool permissions might not cover all memory security requirements
- **Performance impact**: Tool validation overhead on memory operations
- **Data leakage**: PII filtering might miss sensitive data patterns

## Alternatives Considered

### Direct Memory API Access
- **Pros**: Lower latency, simpler implementation
- **Cons**: No tool-level permissions, harder for AI agents to use

### Memory as Separate Protocol
- **Pros**: Specialized protocol for memory operations
- **Cons**: Additional protocol complexity, integration challenges

### Embedded Memory Operations
- **Pros**: No network calls, faster access
- **Cons**: Tight coupling, harder to scale and secure

## Implementation Plan

### Phase 1: Core Tools (Week 1-2)
- Implement `listMemory` and `getContext` tools
- Basic permission checking
- Unit tests and integration tests

### Phase 2: Advanced Features (Week 3-4)
- `putMemory` tool with validation
- PII filtering integration
- Performance optimization

### Phase 3: Production Readiness (Week 5-6)
- Comprehensive security audit
- Load testing
- Documentation and examples

## Testing Strategy

### Unit Tests
- Tool handler logic
- Permission checking
- PII filtering
- Error handling

### Integration Tests
- End-to-end tool execution
- Memory gateway integration
- Permission enforcement

### Security Tests
- Permission bypass attempts
- PII leakage scenarios
- Rate limit testing

### Performance Tests
- Tool execution latency
- Memory operation throughput
- Caching effectiveness
