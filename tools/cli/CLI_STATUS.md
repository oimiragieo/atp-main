# ATP CLI Implementation Status

**Transparency document for atpctl CLI feature availability**

Last Updated: 2025-01-17

---

## Overview

The ATP CLI (`atpctl`) is a comprehensive command-line interface for managing the ATP platform. This document clearly identifies which commands are fully functional vs. in development.

---

## Quick Reference

| Command Group | Status | Notes |
|--------------|--------|-------|
| `atpctl chat` | ✅ **FUNCTIONAL** | Full interactive REPL implemented |
| `atpctl system` | ✅ **FUNCTIONAL** | Health, metrics, logs available |
| `atpctl policies` | ✅ **FUNCTIONAL** | Policy management works (requires router API) |
| `atpctl providers` | ⚠️ **LIMITED** | CLI exists, **Router API endpoints not implemented** |
| `atpctl cluster` | ⚠️ **LIMITED** | CLI exists, **Router API endpoints not implemented** |
| `atpctl config` | ✅ **FUNCTIONAL** | Config management works |
| `atpctl status` | ✅ **FUNCTIONAL** | Platform status available |
| `atpctl version` | ✅ **FUNCTIONAL** | Version info available |

---

## Detailed Status

### ✅ Fully Functional Commands

#### 1. Chat Commands
**Location**: `atpctl/commands/chat.py`

**Available**:
- `atpctl chat repl` - Interactive REPL with conversation history
- `atpctl chat ask "question"` - Quick single question
- Session save/load/export functionality
- Multiline input support
- Markdown rendering

**Requirements**:
- Router service running on `http://localhost:7443` (or `$ATP_API_URL`)

**Example**:
```bash
atpctl chat repl
atpctl chat ask "Explain quantum computing"
```

---

#### 2. System Commands
**Location**: `atpctl/commands/system.py`

**Available**:
- `atpctl system status` - Get system health status
- `atpctl system metrics` - View system metrics
- `atpctl system logs` - Stream system logs
- `atpctl system health` - Health check

**Example**:
```bash
atpctl system status
atpctl system metrics --interval 300
atpctl system logs --follow
```

---

#### 3. Config Commands
**Location**: `atpctl/commands/config.py`

**Available**:
- `atpctl config show` - Display current configuration
- `atpctl config set KEY VALUE` - Set configuration value
- `atpctl config export FILE` - Export configuration
- `atpctl config validate` - Validate configuration

**Example**:
```bash
atpctl config show
atpctl config set max_requests_per_minute 1000
atpctl config export config.yaml
```

---

#### 4. Policies Commands
**Location**: `atpctl/commands/policies.py`

**Available**:
- `atpctl policies list` - List all policies
- `atpctl policies add` - Add new policy
- `atpctl policies delete` - Remove policy
- `atpctl policies validate` - Validate policies

**Requirements**:
- Router service with `/api/v1/policies` endpoint
- Endpoint is **IMPLEMENTED** in `router_service/policy_api.py`

**Example**:
```bash
atpctl policies list
atpctl policies validate
```

---

### ⚠️ Limited Functionality (CLI Implemented, API Missing)

#### 5. Providers Commands
**Location**: `atpctl/commands/providers.py`

**CLI Commands Implemented**:
- `atpctl providers list` - List configured providers
- `atpctl providers add` - Add new provider
- `atpctl providers delete` - Remove provider
- `atpctl providers describe` - Show provider details

**❌ Missing Router API Endpoints**:
- `GET /api/v1/providers` - **NOT IMPLEMENTED**
- `POST /api/v1/providers` - **NOT IMPLEMENTED**
- `DELETE /api/v1/providers/{id}` - **NOT IMPLEMENTED**
- `GET /api/v1/providers/{id}` - **NOT IMPLEMENTED**

**Current Status**:
- CLI code exists and is well-implemented
- **Will fail with HTTP 404** when called because router doesn't have these endpoints
- Adapter configuration is currently done via `ADAPTER_ENDPOINTS` environment variable

**Workaround**:
```bash
# Instead of CLI, configure in docker-compose.yml or .env:
export ADAPTER_ENDPOINTS='["http://anthropic-adapter:7070","http://openai-adapter:7070"]'
```

**To Make Functional**:
1. Implement provider management API in router service
2. Add endpoints to `router_service/api/v1/providers.py` (create file)
3. Register routes in `router_service/service.py`

---

#### 6. Cluster Commands
**Location**: `atpctl/commands/cluster.py`

**CLI Commands Implemented**:
- `atpctl cluster list` - List cluster nodes
- `atpctl cluster describe NODE` - Show node details
- `atpctl cluster scale N` - Scale cluster to N nodes
- `atpctl cluster drain NODE` - Drain node for maintenance

**❌ Missing Router API Endpoints**:
- `GET /api/v1/cluster/nodes` - **NOT IMPLEMENTED**
- `GET /api/v1/cluster/nodes/{id}` - **NOT IMPLEMENTED**
- `POST /api/v1/cluster/scale` - **NOT IMPLEMENTED**
- `POST /api/v1/cluster/nodes/{id}/drain` - **NOT IMPLEMENTED**

**Current Status**:
- CLI code exists and is well-implemented
- **Will fail with HTTP 404** when called because router doesn't have these endpoints
- Scaling is currently done via `docker compose scale` or Kubernetes

**Workaround**:
```bash
# Instead of CLI, use Docker Compose:
docker compose up -d --scale router=3

# Or Kubernetes:
kubectl scale deployment atp-router --replicas=3
```

**To Make Functional**:
1. Implement cluster management API in router service
2. Add service discovery/registry
3. Add endpoints to `router_service/api/v1/cluster.py` (create file)
4. Integrate with orchestration layer (Docker, K8s)

---

## Environment Configuration

### Required for CLI

```bash
# Router URL (default: http://localhost:7443)
export ATP_API_URL="http://localhost:7443"

# API Key (if authentication enabled)
export ATP_API_KEY="your-api-key"
```

**NOTE**: Default changed from `http://localhost:8000` to `http://localhost:7443` for consistency with router default port.

---

## Feature Roadmap

### Implemented (Current)
- [x] Interactive chat REPL
- [x] System health and metrics
- [x] Configuration management
- [x] Policy management
- [x] Rich terminal UI
- [x] Multiple output formats (table, JSON, YAML)

### In Development
- [ ] Provider management API endpoints
- [ ] Cluster management API endpoints
- [ ] Shell completion support
- [ ] Streaming responses for chat

### Planned
- [ ] Cost analytics commands
- [ ] Performance profiling
- [ ] A/B testing management
- [ ] Adapter marketplace integration

---

## Comparison with Documentation

### tools/cli/README.md Claims

| Claimed Feature | Actual Status | Notes |
|----------------|---------------|-------|
| Interactive REPL | ✅ Works | Full implementation |
| Cluster Management | ⚠️ Partial | CLI exists, API missing |
| Provider Management | ⚠️ Partial | CLI exists, API missing |
| Policy Management | ✅ Works | Full implementation |
| System Monitoring | ✅ Works | Full implementation |
| Configuration Mgmt | ✅ Works | Full implementation |

### What's Misleading in Docs

The `tools/cli/README.md` shows examples like:
```bash
atpctl providers add openai --api-key YOUR_KEY
atpctl cluster scale 3
```

**Reality**: These commands exist but **will fail** because the router API endpoints don't exist yet.

**Recommendation**: Update CLI README to add status indicators for each command group.

---

## How to Use the CLI Today

### What Works
```bash
# ✅ These work great
atpctl chat repl
atpctl system status
atpctl system metrics
atpctl config show
atpctl policies list

# ✅ Quick question
atpctl chat ask "What is ATP?"
```

### What Doesn't Work Yet
```bash
# ❌ These will fail with HTTP 404
atpctl providers list
atpctl cluster list

# Use workarounds instead:
docker compose ps
docker compose up -d --scale router=3
```

---

## Testing the CLI

### Install CLI
```bash
# Install dependencies
pip install typer rich prompt-toolkit httpx pyyaml

# Install CLI
cd tools/cli
pip install -e .

# Verify installation
atpctl --help
```

### Test Functional Commands
```bash
# Ensure router is running
docker compose up -d router

# Set API URL
export ATP_API_URL="http://localhost:7443"

# Test system commands
atpctl system status
atpctl system health

# Test chat
atpctl chat ask "Hello!"

# Test config
atpctl config show
```

### Expected Failures (Known Limitations)
```bash
# These will fail - expected
atpctl providers list
# Error: HTTP 404 - endpoint not found

atpctl cluster list
# Error: HTTP 404 - endpoint not found
```

---

## Contributing

Want to help implement the missing API endpoints?

### For Provider Management
1. Create `router_service/api/v1/providers.py`
2. Implement endpoints:
   - `GET /api/v1/providers`
   - `POST /api/v1/providers`
   - `DELETE /api/v1/providers/{id}`
3. Add adapter registry/management logic
4. Update `router_service/service.py` to register routes

### For Cluster Management
1. Create `router_service/api/v1/cluster.py`
2. Implement service discovery
3. Add node registry
4. Implement scaling logic
5. Update `router_service/service.py` to register routes

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.

---

## Summary

**What to tell users**:
- ✅ Chat, system monitoring, config, and policy commands work great
- ⚠️ Provider and cluster management CLI exists but router APIs not implemented yet
- 📝 Use environment variables and docker compose for provider/cluster config for now
- 🚧 API endpoints for providers and cluster are on the roadmap

**For developers**:
- CLI code is production-quality and ready to use
- Missing piece is router API implementation
- Good opportunity for contribution

---

## See Also

- [CLI README](README.md) - Full CLI documentation
- [Environment Variables](../../ENVIRONMENT_VARIABLES.md) - Configuration reference
- [Contributing Guide](../../CONTRIBUTING.md) - Development guidelines
