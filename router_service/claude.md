# Router Service - Claude Guide

## Overview

The router service is the **core of ATP** - a FastAPI application that implements intelligent LLM routing with cost/quality/latency optimization.

**Location**: `/home/user/atp-main/router_service/`
**Main Entry**: `service.py` (3,045 lines)
**Module Count**: 136+ Python files

### 🚨 **CRITICAL IMPLEMENTATION NOTES**

**The router currently generates SYNTHETIC responses for demonstration/testing purposes.**

**What `/v1/ask` endpoint actually does** (`service.py:1408-1449`):
1. Runs bandit model selection algorithms (works correctly)
2. Selects from 4 hardcoded fake models in `routing_constants.py`
3. **Generates synthetic "lorem" text chunks** instead of calling adapters
4. Simulates latency with `asyncio.sleep()`
5. Assigns random quality scores: `random.uniform(0.7, 0.9)`
6. Calculates fake costs from hardcoded model pricing
7. Records synthetic observations for future routing decisions

**Result**: Beautiful architecture with sophisticated algorithms, but **responses are not real AI completions**.

**See "TODO: Core Routing Implementation" section below for integration path.**

## Key Components

### Core Files

#### service.py
- **FastAPI application** with all endpoints
- **Main endpoints**: `/v1/ask`, `/healthz`, `/metrics`, `/mcp`, `/admin/*`
- **Streaming support**: Server-Sent Events for responses
- **WebSocket support**: MCP (Model Context Protocol) interface

#### models.py
- **Pydantic models** for request/response validation
- Key models: `AskRequest`, `FinalResponse`, `Chunk`
- All models have type hints and validation

#### config.py
- **Settings management** using environment variables
- **Validation**: Ensures ROUTER_ADMIN_API_KEY is set and valid
- **Access**: Import `from .config import settings`

### Routing and Selection

#### choose_model.py
- **Model selection logic**
- Implements cost/quality/latency balancing
- Entry point: `choose()` function

#### adaptive_stats.py
- **Bandit algorithms** for model selection
- Thompson sampling and UCB (Upper Confidence Bound)
- Functions: `compute_ucb_scores()`, `thompson_select()`, `ucb_select()`

#### lifecycle.py
- **Model promotion/demotion** based on performance
- Functions: `evaluate_promotions()`, `evaluate_demotions()`

### API Key Management

#### admin_keys.py
- **RBAC** (Role-Based Access Control)
- **API key CRUD** operations
- **Audit logging** for all key operations

### Error Handling

#### errors.py
- **ErrorCode enum** with all error types
- **error_response()** function for consistent error responses
- **Always use** instead of raising HTTPException directly

#### error_mapping.py
- **Exception mapping** to stable error codes
- **marshal_exception()** yields structured error payloads

### State Management

#### state_backend.py
- **Abstraction** for state storage
- **Backends**: Memory (dev) and Redis (production)
- **MemorySchedulerBackend** and **RedisSchedulerBackend**

### Observability

#### logging_utils.py
- **StructuredLogger** for consistent logging
- **Usage**: `logger = StructuredLogger("component.name")`
- **Always use** instead of print()

#### tracing.py
- **OpenTelemetry integration**
- **Initialization**: `init_tracing()`
- **Tracer**: `get_tracer()` returns tracer instance

### Security

#### waf.py
- **Web Application Firewall**
- **check_prompt()** validates incoming prompts
- Configurable patterns via WAF_PATTERNS env var

#### pii.py
- **PII detection and redaction**
- Imported from memory-gateway module
- Automatic scrubbing before logging

### Memory Integration

#### Memory gateway connection
- **HTTP client** to memory-gateway service
- **Default URL**: http://localhost:8080
- **Configurable**: MEMORY_GATEWAY_URL env var

## Common Patterns

### Adding a New Endpoint

```python
from fastapi import FastAPI, HTTPException
from .models import YourRequest, YourResponse
from .errors import ErrorCode, error_response
from .logging_utils import StructuredLogger
from metrics.registry import REGISTRY

logger = StructuredLogger("router.your_feature")
request_counter = REGISTRY.counter("your_feature_requests_total")

@app.post("/v1/your-endpoint")
async def your_endpoint(request: YourRequest) -> YourResponse:
    """Your endpoint description."""
    logger.info("Processing request", extra={"request_id": request.id})
    request_counter.inc()

    try:
        # Your logic here
        result = await process(request)
        return YourResponse(data=result)
    except ValueError as e:
        logger.error("Validation failed", exc_info=e)
        return error_response(ErrorCode.INVALID_INPUT, str(e))
```

### Using Configuration

```python
from .config import settings

# Good
max_chars = settings.max_prompt_chars
api_key = settings.api_key
enable_tracing = settings.enable_tracing

# Bad - Don't use os.getenv() directly
max_chars = int(os.getenv("ROUTER_MAX_PROMPT_CHARS", "10000"))
```

### Logging Pattern

```python
from .logging_utils import StructuredLogger

logger = StructuredLogger("router.component")

# Info
logger.info("Operation started", extra={"user_id": "123"})

# Warning
logger.warning("Rate limit approaching", extra={"current": 90, "limit": 100})

# Error with exception
try:
    risky_operation()
except Exception as e:
    logger.error("Operation failed", exc_info=e)
```

### Error Handling

```python
from .errors import ErrorCode, error_response

# Return error response
if not authorized:
    return error_response(
        ErrorCode.UNAUTHORIZED,
        "Missing or invalid API key"
    )

# With extra context
return error_response(
    ErrorCode.RATE_LIMIT_EXCEEDED,
    "Too many requests",
    extra={"retry_after": 60}
)
```

### Metrics Pattern

```python
from metrics.registry import REGISTRY

# Counter (incrementing count)
request_counter = REGISTRY.counter("feature_requests_total")
request_counter.inc()

# Gauge (current value)
active_connections = REGISTRY.gauge("feature_connections_active")
active_connections.set(10)
active_connections.inc()  # +1
active_connections.dec()  # -1

# Histogram (distribution)
latency_histogram = REGISTRY.histogram("feature_latency_seconds")
latency_histogram.observe(0.125)
```

## Module Organization

```
router_service/
├── service.py              # Main FastAPI app
├── models.py               # Pydantic models
├── config.py               # Settings
├── errors.py               # Error definitions
├── error_mapping.py        # Exception mapping
│
├── choose_model.py         # Model selection
├── adaptive_stats.py       # Bandit algorithms
├── lifecycle.py            # Promotion/demotion
│
├── admin_keys.py           # API key management
├── auth_*.py               # Authentication modules
│
├── state_backend.py        # State abstraction
├── logging_utils.py        # Structured logging
├── tracing.py              # OpenTelemetry
│
├── waf.py                  # Web Application Firewall
├── abuse_prevention.py     # Safety guardrails
│
├── task_classify.py        # Prompt classification
├── observation_schema.py   # Metrics schema
├── shadow_evaluation.py    # A/B testing
│
└── ... (90+ more modules)
```

## Testing

### Location
- **Tests**: `/home/user/atp-main/tests/test_*.py`
- **Fixtures**: `/home/user/atp-main/tests/conftest.py`

### Running Tests
```bash
# All tests
pytest -v

# Specific test
pytest tests/test_service.py::test_health_check -v

# With coverage
make coverage
```

### Writing Tests
```python
import pytest
from router_service.service import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health_check():
    """Test health check endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "OK"

def test_ask_endpoint_unauthorized():
    """Test ask endpoint without API key."""
    response = client.post("/v1/ask", json={
        "prompt": "Test prompt"
    })
    assert response.status_code == 401
```

## Configuration

### Required Environment Variables
- `ROUTER_ADMIN_API_KEY` - Admin API key (≥32 chars, REQUIRED)

### Optional Environment Variables
- `ROUTER_DATA_DIR` - Data directory (default: `../data`)
- `ROUTER_MAX_PROMPT_CHARS` - Max prompt length (default: 10000)
- `ROUTER_ENABLE_TRACING` - Enable tracing (0 or 1)
- `ROUTER_REDIS_URL` - Redis connection (default: localhost:6379)
- `ROUTER_ENABLE_METRICS` - Enable metrics (default: 1)
- `ENABLE_QOS_PRIORITY` - Quality of service (default: 0)

See `/home/user/atp-main/ENVIRONMENT_VARIABLES.md` for complete list.

## Debugging

### Check Logs
```bash
# Docker logs
docker compose logs -f router

# Local development
# Logs go to stdout
```

### Health Check
```bash
curl http://localhost:7443/healthz
# Should return: OK
```

### Metrics
```bash
curl http://localhost:7443/metrics
# Prometheus format metrics
```

### Common Issues

#### Router won't start
- **Check**: Is ROUTER_ADMIN_API_KEY set in .env?
- **Fix**: Add to .env (≥32 characters)

#### Import errors
- **Check**: Is PYTHONPATH set correctly?
- **Fix**: Run from project root or set PYTHONPATH

#### Tests failing
- **Check**: Are all dependencies installed?
- **Fix**: `pip install -r requirements-dev.txt`

## Development Workflow

### Before Committing
```bash
# 1. Lint
make lint

# 2. Format
make format

# 3. Type check
make type

# 4. Test
make test

# 5. Coverage
make coverage
```

### Adding New Features

1. **Create module** in router_service/
2. **Define models** in models.py (if needed)
3. **Add endpoint** to service.py
4. **Add error handling** using ErrorCode
5. **Add logging** using StructuredLogger
6. **Add metrics** using REGISTRY
7. **Write tests** in tests/
8. **Document** in appropriate .md file

## Performance Considerations

### Async/Await
- All I/O operations should be async
- Use `asyncio.gather()` for concurrent operations
- Don't block event loop

### Database Queries
- Use connection pooling
- Paginate large result sets
- Cache expensive queries

### Memory Usage
- Monitor with `psutil`
- Clean up resources in finally blocks
- Use context managers

## Security Checklist

- [x] Never hardcode secrets (enforced via config validation)
- [x] Always validate input with Pydantic (added Literal types and constraints)
- [x] Use parameterized queries for SQL (verified in adaptive_stats.py)
- [x] Sanitize before logging (replaced print() with logger)
- [x] Check API keys (enforced at startup in __post_init__)
- [ ] Rate limit requests (TODO: implement per-endpoint rate limiting)
- [ ] Validate file paths (TODO: audit file operations)
- [ ] Use HTTPS in production (deployment concern)

### Security Audit Findings (2025-11-17)

**Phase 1 Fixes:**
1. CORS misconfiguration - Restricted to safe methods only
2. Input validation gaps - Added constraints to all request models
3. Logging security - Removed ALL print() statements
4. API key validation - Enforced at config initialization

**Phase 2 Improvements:**
5. Authentication middleware - NEW comprehensive API key system
6. Bash tool hardening - Command validation and safety checks
7. Structured logging - All production code uses logger

**Files Modified (Phase 1 + 2):**
- `core/app.py` - CORS + authentication middleware
- `config.py` - API key enforcement
- `api/v1/router.py` - Input validation
- `event_emitter.py`, `adaptive_reconciliation.py`, `cache/l1_cache.py`, `task_clustering_pipeline.py` - Logging
- `middleware/auth.py` - NEW authentication system
- `tools/builtin/bash.py` - Security hardening

**Known Limitations:**
1. SQLite for production stats - Should migrate to PostgreSQL
2. threading.Lock in async code - Documented for future refactor
3. Bash tool requires sandboxing - Disabled by default

**TODO: Core Routing Implementation**

The core routing endpoints currently return placeholder responses instead of calling actual adapters. Implementation required:

**📚 Comprehensive Integration Guide**: See [`ADAPTER_INTEGRATION_GUIDE.md`](/home/user/atp-main/ADAPTER_INTEGRATION_GUIDE.md) for complete step-by-step implementation instructions.

**1. Adapter Integration in /v1/ask endpoint** (`service.py:1408-1449`)
- **Current**: Returns placeholder text `phrase = "lorem" if generated < target_tokens else "done"`
- **Required**: Integrate with adapter registry to make gRPC calls
- **Implementation Path**:
  1. Create AdapterClient infrastructure (`router_service/adapters/client.py`)
  2. Load dynamic model catalog from adapter capabilities
  3. Replace synthetic generation loop with real adapter.Stream() calls
  4. Handle streaming responses and track real metrics
  5. Parse adapter response chunks and emit to client
- **Dependencies**:
  - `router_service/adapter_registry.py` - Registry lookup
  - `tools/adapter_pb2.py` and `adapter_pb2_grpc.py` - Protocol definitions
  - Production-ready adapters: Anthropic, OpenAI (see `ADAPTER_STATUS.md`)
- **Estimated Effort**: 2-3 days for core integration
- **Status**: Critical for production - currently all /ask requests return synthetic data
- **Detailed Guide**: See Phase 3 in `ADAPTER_INTEGRATION_GUIDE.md`

**2. Dynamic Model Catalog** (`routing_constants.py:16-22`)
- **Current**: Hardcoded CATALOG with 4 fake models
- **Required**: Load models dynamically from registered adapters
- **Implementation**: See Phase 2 in `ADAPTER_INTEGRATION_GUIDE.md`
- **Estimated Effort**: 1-2 days
- **Status**: Required for real model discovery

**3. Adapter-Specific Routing** (`service.py:1801`)
- **Current**: `adapter_type` parameter extracted but not used
- **Required**: Allow users to specify which adapter to route to
- **Implementation Path**:
  1. Extract `adapter_type` from request
  2. Filter model catalog to only match specified type
  3. Pass constraint to routing logic
  4. Update model selection to respect adapter_type filter
- **Use Case**: Force routing to specific provider (e.g., only Anthropic adapters)
- **Status**: Enhancement - optional feature for advanced routing

**Implementation Resources**:
- **Integration Guide**: [`ADAPTER_INTEGRATION_GUIDE.md`](/home/user/atp-main/ADAPTER_INTEGRATION_GUIDE.md) - Complete implementation guide with code examples
- **Adapter Status**: [`ADAPTER_STATUS.md`](/home/user/atp-main/ADAPTER_STATUS.md) - Which adapters are production-ready
- **Adapter Registry**: [`router_service/adapter_registry.py`](/home/user/atp-main/router_service/adapter_registry.py) - Registry implementation
- **gRPC Protocol**: [`tools/adapter_pb2.py`](/home/user/atp-main/tools/adapter_pb2.py) - Protocol definitions
- **Production Adapters**:
  - [`adapters/python/anthropic_adapter/`](/home/user/atp-main/adapters/python/anthropic_adapter/) - Anthropic implementation
  - [`adapters/python/openai_adapter/`](/home/user/atp-main/adapters/python/openai_adapter/) - OpenAI implementation

**New Environment Variables:**
- `ROUTER_REQUIRE_AUTH` - Enable auth middleware (default: 0)
- `ROUTER_ENABLE_BASH_TOOL` - Enable bash tool (default: 0)

See `/home/user/atp-main/AUDIT_REPORT.md` for comprehensive audit results

## Additional Resources

- **Main docs**: `/home/user/atp-main/docs/01_ATP.md`
- **Architecture**: `/home/user/atp-main/DEEP_DIVE_REVIEW.md`
- **Contributing**: `/home/user/atp-main/CONTRIBUTING.md`
- **Root guide**: `/home/user/atp-main/claude.md`

---

**For detailed patterns, see**: `.claude/rules/development.md`
**For AI assistant guidance, see**: `.claude/rules/ai-assistant.md`
