# Development Rules for ATP Platform

## Code Style and Standards

### Python Code Standards
1. **Always run linting before committing**: `make lint`
2. **Format code with ruff**: `make format`
3. **Type check with mypy**: `make type`
4. **Line length**: 100 characters maximum
5. **Python version**: 3.11+ required

### Naming Conventions
- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Methods**: `snake_case()`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`
- **Modules**: lowercase, no underscores preferred

### Import Organization
```python
# Standard library
import os
import sys
from typing import Any

# Third-party
from fastapi import FastAPI
from pydantic import BaseModel

# Local application
from .config import settings
from .models import AskRequest
```

## Logging Standards

### Always use StructuredLogger
```python
from .logging_utils import StructuredLogger
logger = StructuredLogger("component.name")

# Good
logger.info("User action", extra={"user_id": "123", "action": "login"})

# Bad - Don't use print()
print("User logged in")
```

### Log Levels
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages for failures
- `CRITICAL`: Critical failures requiring immediate attention

## Error Handling

### Always use ErrorCode enum
```python
from .errors import ErrorCode, error_response

# Good
return error_response(ErrorCode.UNAUTHORIZED, "Invalid API key")

# Bad - Don't raise generic HTTPException
raise HTTPException(status_code=401, detail="Unauthorized")
```

### Error Response Pattern
```python
# In endpoints, always return error_response()
if not authorized:
    return error_response(
        ErrorCode.UNAUTHORIZED,
        "Missing or invalid API key",
        extra={"required": "ROUTER_ADMIN_API_KEY"}
    )
```

## Configuration

### Environment Variables
1. **Never hardcode secrets** - Always use environment variables
2. **Provide sensible defaults** for non-sensitive config
3. **Fail fast** - Validate required env vars at startup
4. **Document all env vars** in `ENVIRONMENT_VARIABLES.md`

### Configuration Pattern
```python
from .config import settings

# Good - Use settings object
max_chars = settings.max_prompt_chars

# Bad - Direct os.getenv() scattered through code
max_chars = int(os.getenv("ROUTER_MAX_PROMPT_CHARS", "10000"))
```

## Testing Requirements

### All New Features Must Have Tests
- **Unit tests**: Test individual components
- **Integration tests**: Test component interactions
- **Coverage**: Minimum 84% (enforced in CI)

### Test Organization
```python
# tests/test_component_name.py
import pytest

def test_function_success():
    """Test successful case."""
    result = function_under_test()
    assert result == expected

def test_function_error():
    """Test error handling."""
    with pytest.raises(ValueError):
        function_under_test(invalid_input)
```

### Running Tests
```bash
# Before committing
make test

# With coverage
make coverage

# Specific test
pytest tests/test_service.py::test_health_check -v
```

## Documentation Requirements

### Code Documentation
1. **Docstrings** for all public functions/classes
2. **Type hints** for function signatures
3. **Comments** for complex logic only

```python
def process_request(
    request: AskRequest,
    timeout: float = 30.0
) -> FinalResponse:
    """Process an AI completion request.

    Args:
        request: The request containing prompt and parameters
        timeout: Maximum time to wait for response in seconds

    Returns:
        Final response with completion and metadata

    Raises:
        TimeoutError: If request exceeds timeout
        ValidationError: If request is invalid
    """
    # Implementation...
```

### User-Facing Documentation
1. **Update docs** when changing user-facing features
2. **Update CHANGELOG.md** for notable changes
3. **Update ENVIRONMENT_VARIABLES.md** when adding config
4. **Keep AI_ASSISTANT_GUIDE.md current** with gotchas

## Security Rules

### Never Commit Secrets
- ✅ `.env.example` with dummy values
- ❌ `.env` with real secrets
- ❌ API keys in code
- ❌ Hardcoded passwords

### Input Validation
1. **Always validate** user input with Pydantic models
2. **Sanitize** prompts before logging
3. **Use parameterized queries** for SQL (never string concat)
4. **Check file paths** for directory traversal

### API Key Management
```python
# Good - Validate API key length
if len(api_key) < 32:
    raise ValueError("API key must be at least 32 characters")

# Good - Use secure comparison
if not secrets.compare_digest(provided, expected):
    return error_response(ErrorCode.UNAUTHORIZED)
```

## Git Workflow

### Branch Naming
- `feature/short-description` - New features
- `fix/short-description` - Bug fixes
- `docs/short-description` - Documentation only
- `refactor/short-description` - Code refactoring

### Commit Messages
```
type(scope): Short description

Longer description if needed

Fixes #123
```

**Types**: feat, fix, docs, test, refactor, perf, chore

### Before Committing
```bash
# 1. Run all checks
make precommit

# 2. Verify tests pass
make test

# 3. Check coverage
make coverage

# 4. Stage changes
git add .

# 5. Commit with descriptive message
git commit -m "feat(router): add new endpoint for model metrics"
```

## Performance Guidelines

### Async/Await
- Use `async def` for I/O-bound operations
- Use `asyncio.gather()` for concurrent operations
- Don't block the event loop with sync I/O

```python
# Good - Async I/O
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# Bad - Blocking I/O
def fetch_data():
    response = requests.get(url)
    return response.json()
```

### Database Queries
- Use connection pooling
- Add indexes for frequently queried columns
- Use pagination for large result sets
- Cache expensive queries when appropriate

### Metrics
- Track all critical operations
- Use counters for events
- Use gauges for current values
- Use histograms for distributions

## Dependency Management

### Adding Dependencies
1. Add to `requirements.txt` (production) or `requirements-dev.txt` (dev)
2. Pin exact versions: `package==1.2.3`
3. Document why dependency is needed
4. Check for security vulnerabilities

### Updating Dependencies
```bash
# Check outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package==new.version

# Update requirements.txt
pip freeze > requirements.txt
```

## Code Review Checklist

### Before Requesting Review
- [ ] All tests pass
- [ ] Coverage ≥ 84%
- [ ] Linting passes (make lint)
- [ ] Type checking passes (make type)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if user-facing)
- [ ] No hardcoded secrets
- [ ] Error handling implemented
- [ ] Logging added for important operations

### During Review
- Focus on correctness, not style (automated)
- Check for security issues
- Verify error handling
- Ensure test coverage
- Validate documentation

## Anti-Patterns to Avoid

### Don't Do This
```python
# ❌ Don't use print() for logging
print("Processing request")

# ❌ Don't catch and ignore exceptions
try:
    process()
except Exception:
    pass

# ❌ Don't use mutable default arguments
def process(items=[]):
    items.append(1)

# ❌ Don't hardcode configuration
MAX_RETRIES = 3
API_URL = "https://api.example.com"

# ❌ Don't return different types
def get_value(key):
    if key in data:
        return data[key]
    return None  # Sometimes dict, sometimes None

# ❌ Don't use global state
CURRENT_USER = None

def set_user(user):
    global CURRENT_USER
    CURRENT_USER = user
```

### Do This Instead
```python
# ✅ Use structured logging
logger.info("Processing request", extra={"request_id": req_id})

# ✅ Handle or re-raise exceptions
try:
    process()
except ValueError as e:
    logger.error("Processing failed", exc_info=e)
    return error_response(ErrorCode.INVALID_INPUT, str(e))

# ✅ Use None or factory function for mutable defaults
def process(items=None):
    items = items or []
    items.append(1)

# ✅ Use configuration system
from .config import settings
MAX_RETRIES = settings.max_retries
API_URL = settings.api_url

# ✅ Use consistent return types or Optional
def get_value(key) -> Optional[dict]:
    return data.get(key)

# ✅ Pass context explicitly
def process_with_user(user: User, request: Request):
    # Use user parameter
```

## Metrics and Monitoring

### Always Add Metrics for New Features
```python
from metrics.registry import REGISTRY

# Counter for events
request_counter = REGISTRY.counter("feature_requests_total")
request_counter.inc()

# Gauge for current state
active_connections = REGISTRY.gauge("feature_connections_active")
active_connections.set(10)

# Histogram for distributions
latency_histogram = REGISTRY.histogram("feature_latency_seconds")
latency_histogram.observe(0.125)
```

### Tracing for Complex Operations
```python
from .tracing import get_tracer

tracer = get_tracer()

with tracer.span("operation_name"):
    # Do work
    with tracer.span("sub_operation"):
        # Nested operation
        pass
```

## Emergency Procedures

### Critical Bug in Production
1. **Immediate**: Revert to last known good version
2. **Create hotfix branch**: `hotfix/critical-issue`
3. **Fix with minimal changes**
4. **Add test that catches the bug**
5. **Deploy fix**
6. **Post-mortem**: Document what happened and how to prevent

### Performance Degradation
1. **Check metrics**: Grafana dashboards
2. **Check logs**: `docker compose logs -f router`
3. **Check resources**: CPU, memory, network
4. **Scale if needed**: `docker compose up -d --scale router=3`
5. **Investigate root cause**
6. **Optimize and redeploy**

---

**Remember**: These rules exist to maintain code quality, security, and maintainability. Follow them consistently.
