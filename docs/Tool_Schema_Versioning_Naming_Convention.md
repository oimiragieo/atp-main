# MCP Tool Schema Versioning Naming Convention

## Overview

This document defines the naming convention and versioning strategy for MCP (Model Context Protocol) tool schemas used in the ATP Router system.

## Version Format

Schema versions follow [Semantic Versioning](https://semver.org/) with the format:

```
vMAJOR.MINOR.PATCH
```

Where:
- **MAJOR**: Breaking changes that are not backward compatible
- **MINOR**: New features that are backward compatible
- **PATCH**: Bug fixes that are backward compatible

## Directory Structure

```
schemas/mcp/
├── v1.0/                    # Major version 1, minor version 0
│   ├── base.json           # Base message schema
│   ├── toolOutput.json     # Tool output message schema
│   ├── error.json          # Error message schema
│   └── ...
├── v1.1/                    # Major version 1, minor version 1
│   ├── base.json
│   ├── toolOutput.json
│   └── ...
└── v2.0/                    # Major version 2, minor version 0
    ├── base.json
    ├── toolOutput.json
    └── ...
```

## Schema File Naming

Schema files are named according to their message type:

- `base.json` - Base message structure
- `toolOutput.json` - Tool output messages
- `error.json` - Error messages
- `event.json` - System events
- `plan.json` - Execution plans
- `final.json` - Completion messages
- `heartbeat.json` - Connection health
- `listTools.json` - Tool listing requests
- `callTool.json` - Tool invocation requests
- `index.json` - Schema index and metadata

## Version Compatibility Rules

### Backward Compatibility
- **PATCH versions** (e.g., 1.0.0 → 1.0.1): Always backward compatible
- **MINOR versions** (e.g., 1.0.x → 1.1.x): Backward compatible
- **MAJOR versions** (e.g., 1.x.x → 2.x.x): May break compatibility

### Fallback Strategy
When a client requests a version that doesn't exist, the system falls back according to this priority:

1. **Exact match**: Use the exact requested version
2. **Compatible minor**: Use the latest minor version in the same major version
3. **Compatible major**: Use the latest version in the same major version
4. **Latest available**: Use the absolute latest version as last resort

### Examples

```python
# Request v1.2, available: v1.0, v1.1, v2.0
# Result: v1.1 (latest compatible minor)

# Request v1.5, available: v1.0, v1.1, v2.0
# Result: v1.1 (latest in major version 1)

# Request v3.0, available: v1.0, v1.1, v2.0
# Result: v2.0 (latest available)
```

## Schema Content Guidelines

### Required Fields
All schemas must include:
- `$schema`: JSON Schema version
- `$id`: Unique schema identifier
- `title`: Human-readable title
- `description`: Schema purpose and usage
- `type`: Root type (usually "object")

### Optional Fields
- `properties`: Object properties
- `required`: Required property names
- `additionalProperties`: Allow unknown properties
- `examples`: Usage examples

### Version Metadata
Schemas should include version information:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://atp-project/schemas/mcp/v1.0/toolOutput.json",
  "title": "MCP Tool Output Message",
  "description": "Schema for tool output messages in MCP protocol v1.0",
  "version": "1.0",
  "type": "object",
  ...
}
```

## Deprecation Policy

### Deprecating Fields
When deprecating fields in a schema:
1. Mark the field with `"deprecated": true`
2. Add a deprecation notice in the field description
3. Remove the field in the next major version

```json
{
  "oldField": {
    "type": "string",
    "deprecated": true,
    "description": "Deprecated in v2.0, use newField instead"
  }
}
```

### Deprecating Versions
When deprecating entire schema versions:
1. Mark the version as deprecated in the index.json
2. Provide migration guide
3. Remove deprecated versions after 2 major versions

## Implementation Notes

### Client Fallback Logic
Clients should implement graceful fallback:
```python
try:
    schema = versioning.load_schema("toolOutput", "v1.2")
except FileNotFoundError:
    # Fallback to latest compatible
    schema = versioning.load_schema("toolOutput")  # Uses latest
```

### Server Negotiation
Servers should advertise supported versions and negotiate:
```python
negotiated = versioning.negotiate_version(client_requested, "toolOutput")
response = {"negotiatedVersion": negotiated}
```

## Migration Guide

### Upgrading from v1.0 to v1.1
- No breaking changes
- Added `sequence` field for streaming support
- Clients can safely upgrade

### Upgrading from v1.x to v2.0
- Breaking change: `metadata` field now required
- Clients must handle the new required field
- Use version negotiation to maintain compatibility

## Testing

Schema versioning must be tested for:
- Exact version matching
- Compatible version fallback
- Incompatible version rejection
- Schema validation with different versions
- Deprecation warnings
