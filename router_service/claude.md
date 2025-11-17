# Router Service - Claude Guide

## Overview

The router service is the **core of ATP** - a FastAPI application that implements intelligent LLM routing with cost/quality/latency optimization.

**Location**: `/home/user/atp-main/router_service/`
**Main Entry**: `service.py` (3,045 lines)
**Module Count**: 136+ Python files

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

- [ ] Never hardcode secrets
- [ ] Always validate input with Pydantic
- [ ] Use parameterized queries for SQL
- [ ] Sanitize before logging
- [ ] Check API keys
- [ ] Rate limit requests
- [ ] Validate file paths
- [ ] Use HTTPS in production

## Additional Resources

- **Main docs**: `/home/user/atp-main/docs/01_ATP.md`
- **Architecture**: `/home/user/atp-main/DEEP_DIVE_REVIEW.md`
- **Contributing**: `/home/user/atp-main/CONTRIBUTING.md`
- **Root guide**: `/home/user/atp-main/claude.md`

---

**For detailed patterns, see**: `.claude/rules/development.md`
**For AI assistant guidance, see**: `.claude/rules/ai-assistant.md`
