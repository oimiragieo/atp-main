# Tests Directory - Claude Guide

## Overview

Comprehensive test suite for ATP platform with **2,079+ tests** and **84% code coverage**.

**Location**: `/home/user/atp-main/tests/`
**Framework**: pytest
**Coverage**: 84% minimum (enforced in CI)

## Running Tests

### Quick Commands
```bash
# All tests
pytest -v

# Specific test file
pytest tests/test_service.py -v

# Specific test function
pytest tests/test_service.py::test_health_check -v

# With coverage
make coverage

# Fast tests only (skip slow tests)
pytest -m "not slow" -v

# Integration tests only
pytest -m "integration" -v
```

### Makefile Targets
```bash
make test          # Core test suite
make coverage      # Tests with coverage report
make precommit     # Lint + type + test
```

## Test Organization

### Test Categories

#### Unit Tests
- **Pattern**: `test_*.py` in root tests/
- **Purpose**: Test individual components in isolation
- **Example**: `test_models.py`, `test_config.py`

#### Integration Tests
- **Pattern**: `tests/integration/test_*.py`
- **Purpose**: Test component interactions
- **Example**: `test_adapter_integration.py`

#### End-to-End Tests
- **Pattern**: `tests/e2e/test_*.py`
- **Purpose**: Test complete user workflows
- **Example**: `test_ws_end_to_end.py`

## Key Test Files

### Router Service Tests
- `test_service.py` - Main service endpoints
- `test_ask_endpoint.py` - /v1/ask endpoint
- `test_health_endpoints.py` - Health checks
- `test_admin_endpoints.py` - Admin API

### Adapter Tests
- `test_adapters_health.py` - Adapter health checks
- `test_anthropic_adapter.py` - Anthropic integration
- `test_openai_adapter.py` - OpenAI integration
- `test_ollama_adapter.py` - Ollama stub

### Security Tests
- `test_abuse_prevention.py` - Safety/security (36KB)
- `test_waf.py` - Web Application Firewall
- `test_admin_keys.py` - API key management

### Feature Tests
- `test_lifecycle.py` - Model promotion/demotion
- `test_choose_model.py` - Model selection
- `test_adaptive_stats.py` - Bandit algorithms
- `test_state_backend.py` - State management

### Memory Gateway Tests
- `test_memory_gateway.py` - Memory operations
- `test_pii.py` - PII detection/redaction

## Test Fixtures

**Location**: `conftest.py`

### Common Fixtures

```python
# Example usage in tests
def test_with_client(client):
    """Use FastAPI test client."""
    response = client.get("/healthz")
    assert response.status_code == 200

def test_with_app(app):
    """Use FastAPI app instance."""
    assert app.title == "ATP Router"

def test_with_mock_adapter(mock_adapter):
    """Use mocked adapter."""
    response = mock_adapter.complete("test")
    assert response is not None
```

## Writing Tests

### Test Template
```python
"""Test module for component X."""
import pytest
from router_service.component import function_to_test

def test_function_success():
    """Test successful case."""
    result = function_to_test(valid_input)
    assert result == expected_output

def test_function_validation():
    """Test input validation."""
    with pytest.raises(ValueError):
        function_to_test(invalid_input)

def test_function_edge_case():
    """Test edge case."""
    result = function_to_test(edge_case_input)
    assert result is not None

@pytest.mark.slow
def test_function_performance():
    """Test performance (marked as slow)."""
    import time
    start = time.time()
    result = function_to_test(large_input)
    duration = time.time() - start
    assert duration < 1.0  # Should complete in <1s

@pytest.mark.integration
def test_function_integration():
    """Test integration with other components."""
    # Integration test logic
    pass
```

### Testing Async Functions
```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

### Testing FastAPI Endpoints
```python
from fastapi.testclient import TestClient
from router_service.service import app

client = TestClient(app)

def test_endpoint():
    """Test endpoint."""
    response = client.post("/v1/ask", json={
        "prompt": "Test prompt",
        "quality": "balanced"
    })
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
```

### Mocking External Services
```python
from unittest.mock import Mock, patch

@patch('router_service.component.external_api_call')
def test_with_mock(mock_api):
    """Test with mocked external API."""
    mock_api.return_value = {"status": "success"}

    result = function_that_calls_api()

    assert result["status"] == "success"
    mock_api.assert_called_once()
```

## Test Markers

### Available Markers
```python
@pytest.mark.slow           # Long-running tests (skip with -m "not slow")
@pytest.mark.integration    # Integration tests
@pytest.mark.asyncio        # Async tests (handled automatically by pytest-asyncio)
```

### Running Specific Markers
```bash
# Skip slow tests
pytest -m "not slow"

# Only integration tests
pytest -m "integration"

# Only fast unit tests
pytest -m "not slow and not integration"
```

## Coverage Requirements

### Minimum Coverage
- **Overall**: 84% minimum (enforced in CI)
- **Per file**: No strict requirement, but aim for >80%

### Coverage Report
```bash
# Generate coverage report
make coverage

# View HTML report
make coverage
open htmlcov/index.html
```

### Coverage Configuration
See `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["router_service", "memory-gateway"]
omit = [
    "*/tests/*",
    "*_pb2.py",
    "*_pb2_grpc.py",
]

[tool.coverage.report]
precision = 2
show_missing = true
```

## Common Patterns

### Setup and Teardown
```python
import pytest

@pytest.fixture
def setup_data():
    """Setup test data."""
    data = {"key": "value"}
    yield data
    # Cleanup after test
    del data

def test_with_setup(setup_data):
    """Test with setup data."""
    assert setup_data["key"] == "value"
```

### Parametrized Tests
```python
@pytest.mark.parametrize("input,expected", [
    ("test1", "result1"),
    ("test2", "result2"),
    ("test3", "result3"),
])
def test_multiple_cases(input, expected):
    """Test multiple cases."""
    result = function(input)
    assert result == expected
```

### Testing Exceptions
```python
def test_exception_raised():
    """Test exception is raised."""
    with pytest.raises(ValueError) as exc_info:
        function_that_raises()

    assert "expected error message" in str(exc_info.value)
```

### Testing Logs
```python
import logging

def test_logging(caplog):
    """Test logging output."""
    with caplog.at_level(logging.INFO):
        function_that_logs()

    assert "Expected log message" in caplog.text
```

## Debugging Tests

### Running Single Test
```bash
# Run specific test with verbose output
pytest tests/test_service.py::test_health_check -v -s

# -s shows print statements
# -v shows verbose output
```

### Using pdb Debugger
```python
def test_with_debugger():
    """Test with debugger."""
    import pdb; pdb.set_trace()  # Debugger will stop here
    result = function()
    assert result is not None
```

### Viewing Logs
```bash
# Show logs during test run
pytest -v -s --log-cli-level=DEBUG
```

## Best Practices

### Do This ✅
```python
# Clear test names
def test_health_check_returns_ok():
    """Test health check returns OK status."""
    pass

# Test one thing per test
def test_validation_rejects_empty_prompt():
    """Test validation rejects empty prompt."""
    pass

# Use fixtures for common setup
@pytest.fixture
def valid_request():
    return {"prompt": "test", "quality": "balanced"}

# Arrange-Act-Assert pattern
def test_process_request():
    # Arrange
    request = create_request()

    # Act
    result = process(request)

    # Assert
    assert result.status == "success"
```

### Don't Do This ❌
```python
# Vague test names
def test_stuff():
    pass

# Testing multiple things
def test_everything():
    test_validation()
    test_processing()
    test_response()

# Hardcoded test data scattered everywhere
def test_x():
    data = {"key": "value"}  # Should be fixture
    ...
```

## CI/CD Integration

### GitHub Actions
Tests run automatically on:
- Every push
- Every pull request
- Nightly builds

### Required Checks
- [ ] All tests pass
- [ ] Coverage ≥ 84%
- [ ] No linting errors
- [ ] Type checking passes

## Troubleshooting

### Tests Failing Locally But Pass in CI
- **Check**: Python version (must be 3.11+)
- **Check**: Dependencies (`pip install -r requirements-dev.txt`)
- **Check**: Environment variables (CI uses .env.example)

### Import Errors
- **Fix**: Run tests from project root
- **Fix**: Ensure PYTHONPATH includes project root

### Flaky Tests
- **Identify**: Tests that sometimes pass, sometimes fail
- **Fix**: Look for race conditions, timing issues, or external dependencies
- **Mark**: Use `@pytest.mark.flaky` if needed

### Slow Tests
- **Identify**: Tests taking >1 second
- **Mark**: Use `@pytest.mark.slow`
- **Optimize**: Mock external calls, use smaller test data

## Additional Resources

- **pytest docs**: https://docs.pytest.org
- **Coverage docs**: https://coverage.readthedocs.io
- **Project config**: `/home/user/atp-main/pyproject.toml`
- **Development rules**: `/home/user/atp-main/.claude/rules/development.md`

---

**For comprehensive testing strategy, see**: `/home/user/atp-main/TESTING.md` (to be created)
**For development workflow, see**: `/home/user/atp-main/.claude/rules/development.md`
