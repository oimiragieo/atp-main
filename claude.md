# ATP Platform - Claude Code Guide

## Project Overview

**ATP (Adaptive Transformer Platform)** is an enterprise-grade intelligent routing system for Large Language Models (LLMs). It's a sophisticated load balancer and cost-optimizer designed to route AI requests to optimal providers.

**Critical: ATP is NOT an LLM itself** - it's middleware that routes to providers (Anthropic, OpenAI, etc.)

### ✅ **CURRENT IMPLEMENTATION STATUS** (Updated 2025-11-19)

**Adapter integration is COMPLETE and ready for production deployment.**

**What this means:**
- ✅ **Phase 1-3 adapter integration completed** - Real LLM API calls now supported
- ✅ **AdapterClient infrastructure** - gRPC client with connection pooling
- ✅ **Dynamic model catalog** - Models loaded from registered adapters
- ✅ **Feature flags for rollout** - Safe gradual deployment via environment variables
- ⚠️ **Disabled by default** - Currently in synthetic mode for safe rollout

**Current Behavior:**
- **Default mode** (USE_REAL_ADAPTERS=0): Generates synthetic "lorem" text for testing
- **Real adapter mode** (USE_REAL_ADAPTERS=1): Streams from actual LLM providers via gRPC
- **Gradual rollout** (ADAPTER_ROLLOUT_PERCENT=10): 10% real traffic, 90% synthetic

**To enable real LLM calls:**
```bash
# Option 1: Full activation
export USE_REAL_ADAPTERS=1

# Option 2: Gradual rollout (10% traffic)
export ADAPTER_ROLLOUT_PERCENT=10
```

**Production readiness:**
- ✅ Graceful fallback to synthetic mode on adapter errors
- ✅ Comprehensive error handling and logging
- ✅ Connection pooling for efficiency
- ✅ Validated with test suite

**For implementation details:** See `router_service/claude.md` "Adapter Integration Status" section

## Quick Reference

### Essential Files
- **Quick Start**: `QUICK_START.md` - 5-minute setup
- **Full Guide**: `GETTING_STARTED.md` - Complete onboarding
- **AI Assistant Help**: `AI_ASSISTANT_GUIDE.md` - For AI assistants helping users
- **Troubleshooting**: `TROUBLESHOOTING.md` - Common issues and fixes
- **Environment**: `ENVIRONMENT_VARIABLES.md` - All configuration options
- **Adapter Status**: `ADAPTER_STATUS.md` - Which adapters work vs stubs

### Critical Gotchas

1. **Default Adapters are STUBS** - They return mock/hardcoded responses, NOT real AI
   - Only Anthropic and OpenAI adapters are production-ready
   - See `ADAPTER_STATUS.md` for details

2. **ROUTER_ADMIN_API_KEY Required** - Router won't start without it (≥32 chars)
   - Quick fix: `cp .env.example .env` and edit

3. **Default Port is 7443** (not 8000)
   - Router: http://localhost:7443
   - Memory Gateway: http://localhost:8080

4. **Some CLI Commands Don't Work** - See `tools/cli/CLI_STATUS.md`
   - Working: `atpctl chat`, `atpctl system`, `atpctl config`
   - Broken: `atpctl providers`, `atpctl cluster`

## Project Structure

```
atp-main/
├── router_service/         # Main router (FastAPI, 3000+ lines)
│   ├── service.py         # FastAPI app and endpoints
│   ├── models.py          # Pydantic data models
│   ├── choose_model.py    # Model selection logic
│   ├── admin_keys.py      # API key management
│   └── ...130+ modules
│
├── adapters/python/       # LLM provider integrations
│   ├── anthropic_adapter/ # ✅ Production (real API)
│   ├── openai_adapter/    # ✅ Production (real API)
│   ├── ollama_adapter/    # ⚠️ Stub (mock responses)
│   └── ...more stubs
│
├── services/memory-gateway/ # Distributed memory/state
│   ├── main.py           # FastAPI KV store
│   ├── memory_store.py   # Redis backend
│   └── pii.py            # PII detection
│
├── client/               # Client libraries and demos
│   ├── health_check.py   # Health endpoint tests
│   ├── memory_put_get.py # Memory operations demo
│   └── mcp_cli.py        # MCP client
│
├── tools/                # Utilities and CLI (100+ files)
│   ├── cli/              # atpctl command-line tool
│   └── atp_sdk.py        # WebSocket SDK
│
├── tests/                # Test suite (2,079+ tests, 84% coverage)
│   ├── test_*.py         # Unit tests
│   ├── integration/      # Integration tests
│   └── conftest.py       # Pytest fixtures
│
├── deploy/               # Deployment configs
│   ├── docker/           # Docker Compose
│   ├── k8s/              # Kubernetes
│   ├── helm/             # Helm charts
│   └── terraform/        # Infrastructure as code
│
└── docs/                 # Technical specifications
    ├── 01_ATP.md         # ATP protocol spec
    └── 04_AGP_Federation_Spec.md

```

## Architecture

### **🚨 CRITICAL: Current Implementation Status**

**The router currently generates synthetic responses for demonstration purposes.**

```
Client Request
    ↓
Router Service (:7443)
    ↓
[Model Selection: Bandit Algorithm (UCB/Thompson)]
    ↓
⚠️ SYNTHETIC RESPONSE GENERATION ⚠️
    ├── Selects from hardcoded models (cheap-model, mid-model, premium-model)
    ├── Generates "lorem" placeholder text
    ├── Simulates latency with asyncio.sleep()
    ├── Calculates fake costs and quality scores
    └── Records synthetic observations
    ↓
Response (streaming)
    ↓
Client
```

**What Actually Happens** (see `router_service/service.py:1408-1449`):
- Router selects from 4 hardcoded fake models defined in `routing_constants.py`
- Generates synthetic "lorem" text chunks (not real AI)
- Simulates latency based on model parameters
- Quality scores are random: `random.uniform(0.7, 0.9)`
- Costs calculated from fake model pricing
- **No adapters are called** in the main request flow

**Production Adapters Exist But Are Not Integrated:**
- ✅ Anthropic adapter (`adapters/python/anthropic_adapter/`) - Production-ready, real API
- ✅ OpenAI adapter (`adapters/python/openai_adapter/`) - Production-ready, real API
- ⚠️ 5 other adapters - Stub implementations with mock responses

**Integration Gap:** See `router_service/claude.md` "TODO: Core Routing Implementation" section for details on connecting adapters to the main routing flow.

**Key Components:**
- **Router**: FastAPI service, intelligent routing logic, cost optimization algorithms
- **Memory Gateway**: Redis-backed KV store for session state
- **Adapters**: gRPC services (exist but not called by router)
- **Observability**: Prometheus metrics, Grafana dashboards, OpenTelemetry tracing

## Development Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Rust 1.70+ (for Rust router)
- Redis (or use Docker Compose)

### Quick Start
```bash
# 1. Clone and setup
git clone <repo>
cd atp-main
cp .env.example .env
# Edit .env and set ROUTER_ADMIN_API_KEY

# 2. Start all services
docker compose up -d

# 3. Validate
python scripts/validate_installation.py
```

### Development Workflow
```bash
# Install dependencies
pip install -r requirements-dev.txt

# Linting and formatting
make lint          # Run ruff linter
make format        # Format code with ruff
make type          # Run mypy type checking
make precommit     # All checks

# Testing
make test          # Run test suite
make coverage      # Tests with coverage (84% minimum)

# Build
make build         # Validate build
make docker        # Build Docker images
```

## Code Standards

### Python Style
- **Linter**: Ruff (configured in `pyproject.toml`)
- **Formatter**: Ruff format
- **Type Checker**: MyPy
- **Line Length**: 100 characters
- **Python Version**: 3.11+

### Common Patterns

#### Logging
```python
from .logging_utils import StructuredLogger
logger = StructuredLogger("component.name")
logger.info("Message", extra={"key": "value"})
```

#### Error Handling
```python
from .errors import ErrorCode, error_response
return error_response(ErrorCode.UNAUTHORIZED, "Details")
```

#### Configuration
```python
from .config import settings
max_chars = settings.max_prompt_chars
```

#### Metrics
```python
from metrics.registry import REGISTRY
counter = REGISTRY.counter("metric_name_total")
counter.inc()
```

### Testing
- **Framework**: pytest
- **Coverage**: Minimum 84% (enforced in CI)
- **Location**: `tests/`
- **Run**: `make test` or `pytest -v`
- **Fixtures**: See `tests/conftest.py`

## Common Tasks

### Adding a New Adapter
1. Create directory in `adapters/python/{provider}_adapter/`
2. Implement gRPC server (see `anthropic_adapter/server.py` as template)
3. Add proto definitions to `atp-router/protos/`
4. Update adapter registry in router_service
5. Add to `docker-compose.yml`
6. Document in `ADAPTER_STATUS.md`
7. Add tests in `tests/test_adapters_*.py`

### Adding a New Endpoint
1. Add route to `router_service/service.py`
2. Define Pydantic models in `router_service/models.py`
3. Add error handling with ErrorCode
4. Add metrics tracking
5. Add tests in `tests/test_service_*.py`
6. Document in API docs

### Debugging
```bash
# Check service logs
docker compose logs -f router
docker compose logs -f memory-gateway

# Health checks
curl http://localhost:7443/healthz
curl http://localhost:8080/healthz

# Metrics
curl http://localhost:7443/metrics

# Interactive testing
python client/health_check.py
python client/memory_put_get.py

# CLI REPL
atpctl chat repl
```

## Environment Variables

**Required:**
- `ROUTER_ADMIN_API_KEY` - Admin API key (≥32 chars, REQUIRED for startup)

**Optional but Important:**
- `ROUTER_REDIS_URL` - Redis connection (default: localhost:6379)
- `ROUTER_ENABLE_TRACING` - Enable OpenTelemetry (0 or 1)
- `ANTHROPIC_API_KEY` - For Anthropic adapter
- `OPENAI_API_KEY` - For OpenAI adapter
- `ROUTER_MAX_PROMPT_CHARS` - Max prompt length (default: 10000)
- `ENABLE_QOS_PRIORITY` - Quality of service (0 or 1)

**See `ENVIRONMENT_VARIABLES.md` for complete reference**

## Troubleshooting

### Router won't start
- **Cause**: Missing `ROUTER_ADMIN_API_KEY`
- **Fix**: Set in `.env` file (≥32 characters)

### Connection refused on port 7443
- **Cause**: Services still starting
- **Fix**: Wait 30 seconds, check `docker compose ps`

### Getting mock/hardcoded responses
- **Cause**: Using stub adapters (ollama, persona)
- **Fix**: Configure production adapter (Anthropic or OpenAI)

### CLI commands return 404
- **Cause**: Some CLI commands not fully implemented
- **Fix**: Check `tools/cli/CLI_STATUS.md` for working commands

**See `TROUBLESHOOTING.md` for more details**

## Key Files for AI Assistants

### Understanding the System
- `AI_ASSISTANT_GUIDE.md` - Comprehensive guide for AI assistants
- `ADAPTER_STATUS.md` - Adapter production readiness
- `tools/cli/CLI_STATUS.md` - CLI command status

### User Guidance
- `QUICK_START.md` - 5-minute setup guide
- `GETTING_STARTED.md` - Complete onboarding
- `TROUBLESHOOTING.md` - Common issues and solutions

### Technical Reference
- `docs/01_ATP.md` - ATP protocol specification
- `ENVIRONMENT_VARIABLES.md` - Configuration reference
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - Production setup

### Development
- `CONTRIBUTING.md` - Contribution guidelines
- `pyproject.toml` - Python project config (ruff, pytest, mypy)
- `Makefile` - Build and test commands

## Security Considerations

- **No hardcoded secrets** - All via environment variables
- **API key management** - Admin keys with RBAC (enforced at startup)
- **PII scrubbing** - Automatic redaction (see `pii.py`)
- **WAF** - Web application firewall (see `waf.py`)
- **Rate limiting** - Configurable RPS limits
- **Audit logging** - All admin actions logged
- **CORS security** - Restricted to safe HTTP methods (GET, POST, OPTIONS)
- **Input validation** - All API endpoints enforce length and type constraints

### Recent Security Improvements (2025-11-17)

#### Phase 1: Core Security Fixes
1. **CORS Hardening** (`router_service/core/app.py:134`)
   - Restricted `allow_methods` from wildcard to `["GET", "POST", "OPTIONS"]`
   - Prevents unauthorized PUT, DELETE, PATCH requests

2. **Input Validation** (`router_service/api/v1/router.py`)
   - Added `max_length=100000` to prompt fields
   - Constrained `quality` to `Literal["fast", "balanced", "high"]`
   - Added range validation to `max_cost_usd` (0-100) and `latency_slo_ms` (0-300000)

3. **Logging Security** (Multiple files)
   - Replaced ALL `print()` statements with proper structured logging
   - Files: `event_emitter.py`, `adaptive_reconciliation.py`, `cache/l1_cache.py`, `task_clustering_pipeline.py`
   - Prevents information leakage through stdout

#### Phase 2: Authentication & Tool Security
4. **Authentication Middleware** (`router_service/middleware/auth.py` - NEW)
   - API key authentication with constant-time comparison
   - Protects all endpoints except public ones (/healthz, /metrics, /docs)
   - Configure via `ROUTER_REQUIRE_AUTH=1` to enable
   - Logs authentication failures for monitoring

5. **Bash Tool Hardening** (`router_service/tools/builtin/bash.py`)
   - Command validation against dangerous patterns
   - Blocks: rm -rf /, dd, sudo, fork bombs, eval, exec
   - Disabled by default - requires `ROUTER_ENABLE_BASH_TOOL=1`
   - Defense-in-depth with pattern matching and length limits

#### Phase 3: Testing & Production Readiness
6. **Automated Security Testing** (`scripts/security_tests.py` - NEW)
   - Automated OWASP Top 10 testing suite
   - Tests authentication, input validation, CORS, DoS prevention
   - Run with: `python3 scripts/security_tests.py --auth-key $ROUTER_ADMIN_API_KEY`
   - Complements manual testing in `SECURITY_TESTING_CHECKLIST.md`

7. **Production Deployment Validation** (`scripts/validate_production_deployment.py` - NEW)
   - Comprehensive pre-deployment validation script
   - Validates environment variables, authentication, security settings
   - Run before deploying: `python3 scripts/validate_production_deployment.py`
   - Exit code 0 = ready for production, 1 = critical issues found

8. **PostgreSQL Migration Guide** (`POSTGRESQL_MIGRATION_GUIDE.md` - NEW)
   - Complete guide for migrating from SQLite to PostgreSQL
   - Includes schema definitions, migration scripts, performance tuning
   - Production-ready async implementation with SQLAlchemy + asyncpg
   - Rollback plan and troubleshooting guide

9. **Core Routing Documentation** (`router_service/claude.md`)
   - Documented TODO for adapter integration in /v1/ask endpoint
   - Implementation path for connecting to production adapters
   - References to adapter registry and gRPC protocol

#### Known Limitations
- SQLite used for stats (migrate to PostgreSQL for production - see `POSTGRESQL_MIGRATION_GUIDE.md`)
- threading.Lock in async codebase (documented for future migration to asyncio.Lock)
- Bash tool requires sandboxed environment for production use
- Core routing returns placeholder responses (adapter integration pending - see `router_service/claude.md`)

**See `SECURITY.md` and `AUDIT_REPORT.md` for comprehensive details**

## Testing Strategy

- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test component interactions
- **E2E tests**: Test full request/response flows
- **Coverage target**: 84% minimum
- **CI/CD**: GitHub Actions runs all checks

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/test_service.py -v

# Run with coverage
make coverage

# Run only fast tests
pytest -m "not slow"
```

## Deployment

### Docker Compose (Development)
```bash
docker compose up -d
```

### Kubernetes (Production)
```bash
# Raw manifests
kubectl apply -f deploy/k8s/

# Or with Kustomize
kubectl apply -k deploy/kustomize/

# Or with Helm
helm install atp deploy/helm/atp/
```

### Cloud Platforms
- **AWS**: See `deploy/aws/`
- **Azure**: See `deploy/azure/`
- **GCP**: See `deploy/gcp/`
- **Terraform**: See `deploy/terraform/`

## Monitoring

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Router Metrics**: http://localhost:7443/metrics
- **Tracing**: OpenTelemetry (if enabled)

**Key Metrics:**
- `requests_total` - Total requests
- `request_duration_ms_sum` - Latency
- `adapters_registered` - Active adapters
- `error_code_*_total` - Error counters

## Additional Resources

### Documentation
- **Index**: `DOCUMENTATION_INDEX.md` - Navigation guide
- **Deep Dive**: `DEEP_DIVE_REVIEW.md` - Technical deep dive
- **Changelog**: `CHANGELOG.md` - Version history

### Community
- **Contributing**: `CONTRIBUTING.md` - How to contribute
- **Security**: `SECURITY.md` - Security policies
- **Agents**: `AGENTS.md` - Repository guidelines

## Tips for AI Assistants

1. **Always check adapter status** before telling users ATP is "working"
2. **Warn about stub adapters** - they return mock responses
3. **Reference specific docs** - don't make up information
4. **Check CLI_STATUS.md** before suggesting CLI commands
5. **Default port is 7443** - not 8000
6. **Environment variables are critical** - guide users to set them properly

**See `AI_ASSISTANT_GUIDE.md` for comprehensive AI assistant guidance**

---

**Project Status**:
- **Routing Algorithms**: Production-ready (bandit selection, cost optimization, observability)
- **Code Quality**: 84% test coverage, comprehensive test suite
- **Adapter Integration**: ✅ COMPLETE (Phases 1-3 done, disabled by default for safe rollout)
- **Production Readiness**: Ready for production use with real LLM providers (set `USE_REAL_ADAPTERS=1`)
**Last Updated**: 2025-11-20
**Version**: See `CHANGELOG.md`

**Key Files for Understanding Current State:**
- `README.md` - Project overview and current status
- `ADAPTER_STATUS.md` - Adapter implementation status
- `router_service/claude.md` - Router implementation details
