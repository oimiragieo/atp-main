# MCP Protocol JSON Schemas

This directory contains JSON Schema definitions for the MCP (Model Context Protocol) message formats used in the ATP Router system.

## Directory Structure

```
schemas/mcp/
├── v1.0/                    # Schema version 1.0
│   ├── base.json           # Base message schema
│   ├── toolOutput.json     # Tool output message schema
│   ├── error.json          # Error message schema
│   ├── event.json          # Event message schema
│   ├── plan.json           # Plan message schema
│   ├── final.json          # Final message schema
│   ├── heartbeat.json      # Heartbeat message schema
│   ├── listTools.json      # List tools message schema
│   ├── callTool.json       # Call tool message schema
│   └── index.json          # Schema index and feature flags
└── README.md               # This file
```

## Schema Versioning

### Version 1.0 (Current)

The v1.0 schemas define the complete MCP protocol message format including:

- **Base Schema** (`base.json`): Common structure for all MCP messages
- **Tool Output** (`toolOutput.json`): Streaming tool responses with experiment metadata
- **Error Handling** (`error.json`): Structured error messages with error codes
- **Events** (`event.json`): System events like model switching and champion selection
- **Plans** (`plan.json`): Execution plans with role-based metadata
- **Final Messages** (`final.json`): Completion messages with performance metrics
- **Heartbeats** (`heartbeat.json`): Connection health monitoring
- **Tool Management** (`listTools.json`, `callTool.json`): Tool discovery and invocation

### Versioning Strategy

1. **Semantic Versioning**: Versions follow MAJOR.MINOR.PATCH format
2. **Backward Compatibility**: New minor versions maintain backward compatibility
3. **Breaking Changes**: Major version increments for breaking changes
4. **Deprecation Period**: Deprecated fields marked with `deprecated: true`

### Supported Features by Version

| Feature | v1.0 |
|---------|------|
| Streaming Responses | ✅ |
| Partial Messages | ✅ |
| Experiment Metadata | ✅ |
| Differential Privacy | ✅ |
| Heartbeat Monitoring | ✅ |
| Error Code Standardization | ✅ |
| Role-based Execution | ✅ |

## Usage

### Python Validation

```python
import json
import jsonschema
from pathlib import Path

# Load schema
schema_path = Path("schemas/mcp/v1.0/toolOutput.json")
with open(schema_path) as f:
    schema = json.load(f)

# Validate message
message = {
    "type": "toolOutput",
    "toolCallId": "call-123",
    "content": [{"type": "text", "text": "Hello world"}],
    "is_partial": True,
    "dp_metrics_emitted": True
}

jsonschema.validate(message, schema)
```

### Schema Index

The `index.json` file provides:
- References to all available schemas
- Feature support matrix
- Version information
- Protocol capabilities

## Message Types

### Core Messages

1. **toolOutput**: Streaming tool execution results
   - Supports partial and final messages
   - Includes experiment metadata
   - Tracks token usage and costs

2. **error**: Structured error responses
   - Standardized error codes
   - Optional tool call correlation
   - Detailed error context

3. **event**: System events and notifications
   - Model switching events
   - Champion/challenger selections
   - Session lifecycle events

4. **plan**: Execution plans with metadata
   - Step-by-step execution plans
   - Role assignments (champion/challenger)
   - Token estimation

5. **final**: Completion messages
   - Final results and metrics
   - Experiment outcomes
   - Performance statistics

### Control Messages

6. **heartbeat**: Connection health monitoring
   - Server uptime and status
   - Active connection counts
   - Memory usage metrics

7. **listTools**: Tool discovery requests
   - Optional filtering by category/tags
   - Capability-based selection

8. **callTool**: Tool invocation requests
   - Parameter validation
   - Streaming options
   - Priority settings

## Validation Rules

### Required Fields
- All messages must have a `type` field
- Message-specific required fields are enforced per schema

### Data Types
- String fields for identifiers and text content
- Integer fields for counts and sequence numbers
- Number fields for metrics and costs
- Boolean fields for flags and status indicators

### Enums
- Message types are restricted to predefined values
- Error codes follow standardized enumeration
- Event types are categorized and documented

## Testing

Comprehensive test suite available in `tests/test_mcp_schema_validation.py`:

```bash
# Run all schema validation tests
pytest tests/test_mcp_schema_validation.py -v

# Run specific test categories
pytest tests/test_mcp_schema_validation.py::TestMCPMessageValidation -v
pytest tests/test_mcp_schema_validation.py::TestSchemaConsistency -v
```

## Future Versions

### Planned Features (v1.1)
- Enhanced metadata fields
- Additional event types
- Extended error context
- Performance optimizations

### Breaking Changes (v2.0)
- Message format restructuring (if needed)
- New required fields
- Deprecated field removal

## Contributing

When adding new message types or modifying schemas:

1. Update the appropriate schema file
2. Add corresponding tests in `test_mcp_schema_validation.py`
3. Update this README with new features
4. Ensure backward compatibility for minor versions
5. Update the schema index if adding new message types

## References

- [JSON Schema Draft 07](https://json-schema.org/specification-links.html#draft-7)
- [ATP Router Documentation](../docs/)
- [MCP Protocol Specification](../docs/14_MCP_Integration.md)
