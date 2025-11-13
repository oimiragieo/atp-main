# ATP/AGP Enterprise Overhaul Plan
## Senior Network AI Engineer - Deep Dive & Comprehensive Refactoring

**Document Version:** 1.0
**Date:** 2025-11-13
**Status:** Active Development
**Coverage Target:** 83% → 90%+
**Timeline:** Phased Implementation (4-6 weeks)

---

## Executive Summary

This document outlines a comprehensive enterprise-grade overhaul of the ATP/AGP LLM routing and orchestration platform. Based on deep codebase analysis, industry best practices research, and enterprise architecture patterns, this plan addresses critical architectural issues, security concerns, operational gaps, and integration challenges.

### Current State Assessment

**Strengths:**
- Production-grade codebase with 83% test coverage
- Sophisticated routing algorithms (Thompson sampling, UCB, contextual bandits)
- Comprehensive observability (Prometheus, OpenTelemetry, structured logging)
- Strong security foundations (mTLS, OIDC, PII handling, WAF)
- Multi-cloud deployment ready (AWS, Azure, GCP)
- 136 well-organized router modules with clear separation of concerns

**Critical Issues Identified:**
1. **Architecture:** Monolithic `service.py` (3,040 lines) needs decomposition
2. **State Management:** Global state variables creating concurrency risks
3. **Lifecycle:** No graceful shutdown for WebSocket connections
4. **Security:** Plaintext admin keys, secrets in environment variables
5. **Operations:** Missing liveness probes, no per-tenant rate limiting
6. **Integration:** Incomplete Rust router integration
7. **Dependencies:** Circular dependencies between modules
8. **Database:** No connection pooling, synchronous I/O in async context

### Target State

Transform ATP/AGP into a fully enterprise-ready, microservices-based platform with:
- Domain-driven service decomposition
- Zero-downtime deployments with graceful shutdown
- Enterprise secrets management (HashiCorp Vault)
- Comprehensive health checks (liveness + readiness)
- Per-tenant quotas and rate limiting
- Fully integrated Rust high-performance router
- ML-based PII detection
- 90%+ test coverage with comprehensive integration tests

---

## Phase 1: Architecture Refactoring (Week 1-2)

### 1.1 Decompose Monolithic `service.py`

**Objective:** Break down the 3,040-line monolith into domain-driven services

**Current Issues:**
- Single file handling routing, admin, WebSocket, MCP, health, metrics
- Difficult to test, maintain, and scale independently
- Tight coupling between unrelated concerns

**Target Architecture:**

```
router_service/
├── core/
│   ├── app.py                 # FastAPI app factory with dependency injection
│   ├── config.py              # Centralized configuration management
│   ├── lifecycle.py           # Startup/shutdown lifecycle management
│   └── dependencies.py        # Dependency injection container
├── api/
│   ├── v1/
│   │   ├── router.py          # /v1/ask, /v1/plan routing endpoints
│   │   ├── observe.py         # /v1/observe observation logging
│   │   └── __init__.py
│   ├── admin/
│   │   ├── keys.py            # Admin key management
│   │   ├── policies.py        # Policy management
│   │   ├── metrics.py         # /metrics endpoint
│   │   └── health.py          # /healthz, /livez, /readyz
│   ├── websocket/
│   │   ├── handler.py         # WebSocket connection management
│   │   ├── mcp.py             # Model Context Protocol handler
│   │   └── streams.py         # Streaming response handler
│   └── __init__.py
├── domain/
│   ├── routing/
│   │   ├── service.py         # Routing domain service
│   │   ├── strategies.py      # Bandit, Thompson, UCB strategies
│   │   └── models.py          # Routing domain models
│   ├── observation/
│   │   ├── service.py         # Observation logging service
│   │   ├── buffer.py          # Thread-safe observation buffer
│   │   └── models.py          # Observation schemas
│   ├── adapter/
│   │   ├── registry.py        # Adapter registry service
│   │   ├── health.py          # Adapter health tracking
│   │   └── capabilities.py    # Capability advertisement
│   └── security/
│       ├── auth.py            # Authentication service
│       ├── pii.py             # PII detection/redaction service
│       └── waf.py             # WAF service
├── infrastructure/
│   ├── database/
│   │   ├── connection.py      # Connection pool management
│   │   ├── repositories.py    # Data access layer
│   │   └── models.py          # Database models
│   ├── cache/
│   │   ├── redis.py           # Redis connection management
│   │   └── strategy.py        # Caching strategies
│   ├── messaging/
│   │   └── events.py          # Event bus for inter-service communication
│   └── tracing/
│       └── instrumentation.py # OpenTelemetry instrumentation
└── shared/
    ├── errors.py              # Shared error types
    ├── logging.py             # Structured logging utilities
    └── models.py              # Shared domain models
```

**Implementation Steps:**

1. **Create App Factory Pattern** (`core/app.py`):
```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize dependencies
    await startup_services()
    yield
    # Shutdown: graceful cleanup
    await shutdown_services()

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    # Register routers
    app.include_router(router_v1.router, prefix="/v1")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(websocket.router)

    # Add middleware
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(TracingMiddleware)

    return app
```

2. **Replace Global State with Dependency Injection**:
```python
# Before (global state - BAD):
_OBS_BUFFER: list[dict[str, Any]] = []
_OBS_LOCK = threading.Lock()

# After (dependency injection - GOOD):
class ObservationService:
    def __init__(self):
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def add(self, observation: dict[str, Any]):
        async with self._lock:
            self._buffer.append(observation)

# Dependency injection
def get_observation_service() -> ObservationService:
    return app.state.observation_service
```

3. **Extract Domain Services**:
   - Routing service with strategy pattern for bandit/Thompson/UCB
   - Observation service with async buffer management
   - Adapter registry with health tracking
   - Authentication service with OIDC integration

4. **API Layer Separation**:
   - V1 endpoints for public API
   - Admin endpoints with RBAC
   - WebSocket handlers with graceful shutdown
   - Health endpoints (liveness, readiness, startup)

**Success Criteria:**
- [ ] No file > 500 lines
- [ ] All services independently testable
- [ ] Zero global mutable state
- [ ] Dependency injection throughout
- [ ] Test coverage maintained at 83%+

**Estimated Time:** 5-7 days

---

### 1.2 Implement Graceful Shutdown

**Objective:** Ensure zero data loss during deployments and shutdowns

**Current Issues:**
- WebSocket connections hang on shutdown
- No connection draining
- In-flight requests may be lost
- Background tasks not properly canceled

**Solution Architecture:**

```python
# 1. Shutdown Coordinator
class ShutdownCoordinator:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.active_connections: set[WebSocket] = set()
        self.background_tasks: set[asyncio.Task] = set()

    async def shutdown(self, timeout: float = 30.0):
        """Gracefully shutdown all connections and tasks"""
        logger.info("Initiating graceful shutdown", timeout=timeout)

        # 1. Set shutdown event (signals WebSocket loops to exit)
        self.shutdown_event.set()

        # 2. Stop accepting new connections
        # (handled by FastAPI lifespan context)

        # 3. Wait for active WebSocket connections to close
        if self.active_connections:
            logger.info("Closing WebSocket connections", count=len(self.active_connections))
            await self._close_websockets(timeout=timeout * 0.5)

        # 4. Cancel background tasks
        if self.background_tasks:
            logger.info("Canceling background tasks", count=len(self.background_tasks))
            await self._cancel_tasks(timeout=timeout * 0.3)

        # 5. Flush observation buffer
        await self._flush_observations(timeout=timeout * 0.2)

        logger.info("Graceful shutdown complete")

    async def _close_websockets(self, timeout: float):
        """Close all WebSocket connections gracefully"""
        close_tasks = [
            self._close_websocket(ws)
            for ws in self.active_connections
        ]

        try:
            await asyncio.wait_for(
                asyncio.gather(*close_tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("WebSocket close timeout exceeded",
                          remaining=len(self.active_connections))

# 2. WebSocket Handler with Shutdown Support
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    coordinator: ShutdownCoordinator = Depends(get_shutdown_coordinator)
):
    await websocket.accept()
    coordinator.active_connections.add(websocket)

    try:
        while not coordinator.shutdown_event.is_set():
            # Use wait_for with shutdown event
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=1.0  # Check shutdown every second
                )
                await process_message(data)
            except asyncio.TimeoutError:
                continue  # Check shutdown event again
            except WebSocketDisconnect:
                break
    finally:
        coordinator.active_connections.discard(websocket)
        try:
            await websocket.close()
        except Exception:
            pass

# 3. Lifespan Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    coordinator = ShutdownCoordinator()
    app.state.shutdown_coordinator = coordinator

    # Register signal handlers
    def handle_signal(signum, frame):
        logger.info("Received shutdown signal", signal=signum)
        asyncio.create_task(coordinator.shutdown())

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    yield

    # Shutdown
    await coordinator.shutdown(timeout=30.0)
```

**Implementation Steps:**

1. Create `ShutdownCoordinator` class
2. Integrate with FastAPI lifespan
3. Update WebSocket handlers to check shutdown event
4. Add signal handlers (SIGTERM, SIGINT)
5. Implement connection tracking
6. Add background task management
7. Create comprehensive shutdown tests

**Success Criteria:**
- [ ] Zero connection hangs on shutdown
- [ ] All in-flight requests complete or timeout gracefully
- [ ] Observation buffer flushed before shutdown
- [ ] Shutdown completes within 30 seconds
- [ ] Integration test validates behavior

**Estimated Time:** 2-3 days

---

### 1.3 Replace Global State with Dependency Injection

**Objective:** Eliminate all module-level globals for thread-safety and testability

**Current Issues:**
```python
# Global state anti-patterns in current code:
_OBS_BUFFER: list[dict[str, Any]] = []
_OBS_LOCK = threading.Lock()
_LAST_SCRUBBED_PROMPT: dict[str, str | None] = {"value": None}
STORE: dict = {}  # In various modules
```

**Solution - Dependency Injection Container:**

```python
# container.py
from dataclasses import dataclass
from typing import Protocol

class Container:
    """Dependency injection container"""

    def __init__(self):
        self._services: dict[type, object] = {}

    def register(self, interface: type, implementation: object):
        self._services[interface] = implementation

    def get(self, interface: type):
        if interface not in self._services:
            raise ValueError(f"Service {interface} not registered")
        return self._services[interface]

# Service interfaces
class ObservationRepository(Protocol):
    async def add(self, observation: dict) -> None: ...
    async def get_all(self) -> list[dict]: ...
    async def flush(self) -> None: ...

class AdapterRegistry(Protocol):
    async def register(self, adapter_id: str, capabilities: dict) -> None: ...
    async def get_healthy_adapters(self) -> list[str]: ...
    def get(self, adapter_id: str) -> dict | None: ...

# Concrete implementations
class InMemoryObservationRepository:
    def __init__(self):
        self._buffer: list[dict] = []
        self._lock = asyncio.Lock()

    async def add(self, observation: dict) -> None:
        async with self._lock:
            self._buffer.append(observation)

    async def get_all(self) -> list[dict]:
        async with self._lock:
            return self._buffer.copy()

    async def flush(self) -> None:
        async with self._lock:
            observations = self._buffer.copy()
            self._buffer.clear()
            # Persist observations
            await self._persist(observations)

# FastAPI integration
def create_container() -> Container:
    container = Container()

    # Register services
    container.register(
        ObservationRepository,
        InMemoryObservationRepository()
    )
    container.register(
        AdapterRegistry,
        InMemoryAdapterRegistry()
    )

    return container

# Dependency injection in endpoints
def get_observation_repo(
    request: Request
) -> ObservationRepository:
    return request.app.state.container.get(ObservationRepository)

@app.post("/v1/observe")
async def observe(
    observation: dict,
    repo: ObservationRepository = Depends(get_observation_repo)
):
    await repo.add(observation)
    return {"status": "ok"}
```

**Implementation Steps:**

1. Create dependency injection container
2. Define service interfaces (Protocols)
3. Implement concrete services
4. Replace all global state with injected services
5. Update all endpoints to use Depends()
6. Add service lifecycle management
7. Create factory functions for test fixtures

**Success Criteria:**
- [ ] Zero module-level mutable globals
- [ ] All state managed through DI container
- [ ] Services easily mockable in tests
- [ ] Thread-safe by design
- [ ] Test coverage maintained

**Estimated Time:** 3-4 days

---

## Phase 2: Security & Operations (Week 2-3)

### 2.1 Enterprise Secrets Management

**Objective:** Eliminate plaintext secrets and integrate with HashiCorp Vault

**Current Issues:**
```bash
# .env.example (INSECURE):
ROUTER_ADMIN_API_KEY=dev-admin-key-12345
ROUTER_ADMIN_KEYS=["dev-admin-key-12345","test-key-67890"]
AUDIT_SECRET=dev-audit-secret-12345
```

**Solution - HashiCorp Vault Integration:**

```python
# secrets/vault.py
import hvac
from typing import Optional
from functools import lru_cache
import asyncio

class VaultClient:
    """HashiCorp Vault integration"""

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None
    ):
        self.client = hvac.Client(url=url)

        # Support multiple auth methods
        if token:
            self.client.token = token
        elif role_id and secret_id:
            self._auth_approle(role_id, secret_id)
        else:
            raise ValueError("Must provide token or AppRole credentials")

    def _auth_approle(self, role_id: str, secret_id: str):
        """Authenticate using AppRole"""
        response = self.client.auth.approle.login(
            role_id=role_id,
            secret_id=secret_id
        )
        self.client.token = response['auth']['client_token']

    def get_secret(self, path: str, key: Optional[str] = None) -> dict | str:
        """Retrieve secret from Vault"""
        response = self.client.secrets.kv.v2.read_secret_version(path=path)
        data = response['data']['data']

        if key:
            return data[key]
        return data

    def set_secret(self, path: str, data: dict) -> None:
        """Store secret in Vault"""
        self.client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=data
        )

    def rotate_secret(self, path: str, generator_func) -> dict:
        """Rotate a secret and return new value"""
        new_secret = generator_func()
        self.set_secret(path, new_secret)
        return new_secret

# Configuration with Vault
class SecureConfig:
    """Configuration loader with Vault integration"""

    def __init__(self, vault_client: VaultClient):
        self.vault = vault_client
        self._cache = {}

    @property
    def admin_api_key(self) -> str:
        """Get admin API key from Vault"""
        if 'admin_api_key' not in self._cache:
            self._cache['admin_api_key'] = self.vault.get_secret(
                'atp/router/admin',
                'api_key'
            )
        return self._cache['admin_api_key']

    @property
    def database_password(self) -> str:
        """Get database password from Vault"""
        return self.vault.get_secret('atp/database', 'password')

    def refresh_cache(self):
        """Refresh cached secrets"""
        self._cache.clear()

# Kubernetes integration with Vault Agent
# deploy/k8s/vault-agent-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vault-agent-config
data:
  config.hcl: |
    exit_after_auth = false
    pid_file = "/var/run/vault-agent.pid"

    auto_auth {
      method {
        type = "kubernetes"
        config = {
          role = "atp-router"
        }
      }

      sink {
        type = "file"
        config = {
          path = "/vault/secrets/token"
        }
      }
    }

    template {
      source      = "/vault/templates/config.tpl"
      destination = "/vault/secrets/config.env"
    }

# Secrets rotation service
class SecretsRotationService:
    """Background service for automatic secret rotation"""

    def __init__(
        self,
        vault: VaultClient,
        rotation_interval: int = 86400  # 24 hours
    ):
        self.vault = vault
        self.rotation_interval = rotation_interval
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start rotation background task"""
        self._task = asyncio.create_task(self._rotation_loop())

    async def stop(self):
        """Stop rotation task"""
        if self._task:
            self._task.cancel()
            await self._task

    async def _rotation_loop(self):
        """Periodic secret rotation"""
        while True:
            try:
                await asyncio.sleep(self.rotation_interval)
                await self._rotate_secrets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Secret rotation failed", error=str(e))

    async def _rotate_secrets(self):
        """Rotate all rotatable secrets"""
        logger.info("Starting secret rotation")

        # Rotate admin keys
        new_key = secrets.token_urlsafe(32)
        self.vault.set_secret('atp/router/admin', {'api_key': new_key})

        # Rotate audit secret
        new_audit_secret = secrets.token_urlsafe(32)
        self.vault.set_secret('atp/audit', {'secret': new_audit_secret})

        logger.info("Secret rotation complete")
```

**Implementation Steps:**

1. Set up HashiCorp Vault (Docker/K8s)
2. Configure Vault authentication (AppRole, Kubernetes)
3. Create `VaultClient` wrapper
4. Implement `SecureConfig` class
5. Replace all `os.getenv()` calls with Vault lookups
6. Add secrets rotation service
7. Create Vault initialization scripts
8. Update deployment manifests with Vault Agent
9. Add comprehensive security tests

**Success Criteria:**
- [ ] Zero plaintext secrets in code/config
- [ ] All secrets retrieved from Vault
- [ ] Automatic secret rotation working
- [ ] Vault Agent integrated in K8s
- [ ] Security audit passes

**Estimated Time:** 4-5 days

---

### 2.2 Comprehensive Health Checks

**Objective:** Implement liveness, readiness, and startup probes

**Current Issues:**
- Only basic `/healthz` endpoint
- No distinction between liveness and readiness
- No dependency health checks

**Solution - Three-Tier Health System:**

```python
# health/checks.py
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Awaitable

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheckResult:
    status: HealthStatus
    message: str
    latency_ms: float
    metadata: dict = None

class HealthCheck(Protocol):
    async def check(self) -> HealthCheckResult: ...

# Specific health checks
class DatabaseHealthCheck:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def check(self) -> HealthCheckResult:
        start = time.time()
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SELECT 1")

            latency = (time.time() - start) * 1000

            if latency > 1000:  # > 1s is degraded
                return HealthCheckResult(
                    status=HealthStatus.DEGRADED,
                    message="Database slow",
                    latency_ms=latency
                )

            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Database OK",
                latency_ms=latency
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {e}",
                latency_ms=(time.time() - start) * 1000
            )

class RedisHealthCheck:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def check(self) -> HealthCheckResult:
        start = time.time()
        try:
            await self.redis.ping()
            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Redis OK",
                latency_ms=latency
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {e}",
                latency_ms=(time.time() - start) * 1000
            )

class AdapterHealthCheck:
    def __init__(self, adapter_registry):
        self.registry = adapter_registry

    async def check(self) -> HealthCheckResult:
        healthy_count = len(await self.registry.get_healthy_adapters())
        total_count = len(self.registry.get_all())

        if healthy_count == 0:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="No healthy adapters",
                latency_ms=0,
                metadata={"healthy": 0, "total": total_count}
            )
        elif healthy_count < total_count * 0.5:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"Only {healthy_count}/{total_count} adapters healthy",
                latency_ms=0,
                metadata={"healthy": healthy_count, "total": total_count}
            )
        else:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message=f"{healthy_count}/{total_count} adapters healthy",
                latency_ms=0,
                metadata={"healthy": healthy_count, "total": total_count}
            )

# Health check aggregator
class HealthCheckService:
    def __init__(self):
        self.liveness_checks: list[HealthCheck] = []
        self.readiness_checks: list[HealthCheck] = []
        self.startup_checks: list[HealthCheck] = []

    def add_liveness_check(self, check: HealthCheck):
        """Add liveness check (is process alive?)"""
        self.liveness_checks.append(check)

    def add_readiness_check(self, check: HealthCheck):
        """Add readiness check (can accept traffic?)"""
        self.readiness_checks.append(check)

    def add_startup_check(self, check: HealthCheck):
        """Add startup check (finished initializing?)"""
        self.startup_checks.append(check)

    async def check_liveness(self) -> tuple[HealthStatus, dict]:
        """Check if application is alive (should restart if fails)"""
        results = await asyncio.gather(
            *[check.check() for check in self.liveness_checks],
            return_exceptions=True
        )

        # Liveness should only check critical issues
        status = HealthStatus.HEALTHY
        details = {}

        for i, result in enumerate(results):
            check_name = self.liveness_checks[i].__class__.__name__
            if isinstance(result, Exception):
                status = HealthStatus.UNHEALTHY
                details[check_name] = {"error": str(result)}
            else:
                details[check_name] = {
                    "status": result.status.value,
                    "message": result.message
                }
                if result.status == HealthStatus.UNHEALTHY:
                    status = HealthStatus.UNHEALTHY

        return status, details

    async def check_readiness(self) -> tuple[HealthStatus, dict]:
        """Check if application can serve traffic"""
        results = await asyncio.gather(
            *[check.check() for check in self.readiness_checks],
            return_exceptions=True
        )

        status = HealthStatus.HEALTHY
        details = {}

        for i, result in enumerate(results):
            check_name = self.readiness_checks[i].__class__.__name__
            if isinstance(result, Exception):
                status = HealthStatus.UNHEALTHY
                details[check_name] = {"error": str(result)}
            else:
                details[check_name] = {
                    "status": result.status.value,
                    "message": result.message,
                    "latency_ms": result.latency_ms
                }
                if result.status == HealthStatus.UNHEALTHY:
                    status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and status != HealthStatus.UNHEALTHY:
                    status = HealthStatus.DEGRADED

        return status, details

# FastAPI endpoints
@app.get("/healthz")
async def health_check(
    health_service: HealthCheckService = Depends(get_health_service)
):
    """Basic health check"""
    return {"status": "ok"}

@app.get("/livez")
async def liveness_check(
    health_service: HealthCheckService = Depends(get_health_service)
):
    """Liveness probe - should restart if fails"""
    status, details = await health_service.check_liveness()

    if status == HealthStatus.UNHEALTHY:
        raise HTTPException(status_code=503, detail=details)

    return {"status": status.value, "checks": details}

@app.get("/readyz")
async def readiness_check(
    health_service: HealthCheckService = Depends(get_health_service)
):
    """Readiness probe - should remove from load balancer if fails"""
    status, details = await health_service.check_readiness()

    if status in [HealthStatus.UNHEALTHY, HealthStatus.DEGRADED]:
        raise HTTPException(status_code=503, detail=details)

    return {"status": status.value, "checks": details}

@app.get("/startupz")
async def startup_check(
    health_service: HealthCheckService = Depends(get_health_service)
):
    """Startup probe - application initialization complete"""
    status, details = await health_service.check_startup()

    if status != HealthStatus.HEALTHY:
        raise HTTPException(status_code=503, detail=details)

    return {"status": status.value, "checks": details}
```

**Kubernetes Integration:**

```yaml
# deploy/k8s/router-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atp-router
spec:
  template:
    spec:
      containers:
      - name: router
        image: atp-router:latest
        ports:
        - containerPort: 7443

        # Startup probe - wait for initialization
        startupProbe:
          httpGet:
            path: /startupz
            port: 7443
          failureThreshold: 30
          periodSeconds: 10

        # Liveness probe - restart if unhealthy
        livenessProbe:
          httpGet:
            path: /livez
            port: 7443
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        # Readiness probe - remove from LB if not ready
        readinessProbe:
          httpGet:
            path: /readyz
            port: 7443
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
```

**Implementation Steps:**

1. Create health check framework
2. Implement specific checks (DB, Redis, adapters)
3. Create health check aggregator
4. Add /livez, /readyz, /startupz endpoints
5. Update Kubernetes manifests
6. Add health check metrics
7. Create comprehensive health tests

**Success Criteria:**
- [ ] Three-tier health system (liveness/readiness/startup)
- [ ] All dependencies checked
- [ ] K8s probes configured correctly
- [ ] Metrics for health check latency
- [ ] Zero false positives in production

**Estimated Time:** 2-3 days

---

### 2.3 Per-Tenant Rate Limiting

**Objective:** Implement fine-grained rate limiting and quota management

**Current Issues:**
- Only global rate limiting
- No per-tenant quotas
- No cost-based limiting

**Solution - Multi-Level Rate Limiting:**

```python
# ratelimit/service.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import redis.asyncio as redis

@dataclass
class RateLimit:
    requests_per_second: int
    requests_per_minute: int
    requests_per_hour: int
    tokens_per_day: int
    cost_per_day_usd: float

@dataclass
class QuotaConfig:
    tenant_id: str
    tier: str  # "free", "pro", "enterprise"
    rate_limit: RateLimit
    burst_multiplier: float = 1.5

class RateLimitService:
    """Multi-level rate limiting with Redis"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        tenant_id: str,
        config: QuotaConfig
    ) -> tuple[bool, dict]:
        """Check if request is within rate limits"""

        # Check multiple windows
        checks = [
            ("rps", config.rate_limit.requests_per_second, 1),
            ("rpm", config.rate_limit.requests_per_minute, 60),
            ("rph", config.rate_limit.requests_per_hour, 3600),
        ]

        for window_name, limit, window_seconds in checks:
            allowed, remaining = await self._check_sliding_window(
                tenant_id,
                window_name,
                limit,
                window_seconds
            )

            if not allowed:
                return False, {
                    "allowed": False,
                    "window": window_name,
                    "limit": limit,
                    "remaining": 0,
                    "reset_at": (datetime.now() + timedelta(seconds=window_seconds)).isoformat()
                }

        # All checks passed
        return True, {
            "allowed": True,
            "remaining": remaining
        }

    async def _check_sliding_window(
        self,
        tenant_id: str,
        window_name: str,
        limit: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """Sliding window rate limit check"""
        key = f"ratelimit:{tenant_id}:{window_name}"
        now = time.time()
        window_start = now - window_seconds

        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current requests
        pipe.zcard(key)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Set expiry
        pipe.expire(key, window_seconds)

        results = await pipe.execute()
        current_count = results[1]

        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)

        return allowed, remaining

    async def check_token_quota(
        self,
        tenant_id: str,
        tokens: int,
        config: QuotaConfig
    ) -> tuple[bool, dict]:
        """Check token-based quota"""
        key = f"quota:tokens:{tenant_id}:daily"

        # Get current usage
        current = await self.redis.get(key)
        current_usage = int(current) if current else 0

        remaining = config.rate_limit.tokens_per_day - current_usage

        if current_usage + tokens > config.rate_limit.tokens_per_day:
            return False, {
                "allowed": False,
                "quota_type": "tokens",
                "limit": config.rate_limit.tokens_per_day,
                "current": current_usage,
                "remaining": remaining
            }

        # Increment usage
        pipe = self.redis.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, 86400)  # 24 hours
        await pipe.execute()

        return True, {
            "allowed": True,
            "current": current_usage + tokens,
            "remaining": remaining - tokens
        }

    async def check_cost_quota(
        self,
        tenant_id: str,
        cost_usd: float,
        config: QuotaConfig
    ) -> tuple[bool, dict]:
        """Check cost-based quota"""
        key = f"quota:cost:{tenant_id}:daily"

        # Use Redis hash for precise float tracking
        current = await self.redis.hget(key, "cost")
        current_cost = float(current) if current else 0.0

        remaining = config.rate_limit.cost_per_day_usd - current_cost

        if current_cost + cost_usd > config.rate_limit.cost_per_day_usd:
            return False, {
                "allowed": False,
                "quota_type": "cost",
                "limit_usd": config.rate_limit.cost_per_day_usd,
                "current_usd": current_cost,
                "remaining_usd": remaining
            }

        # Increment cost
        pipe = self.redis.pipeline()
        pipe.hincrbyfloat(key, "cost", cost_usd)
        pipe.expire(key, 86400)
        await pipe.execute()

        return True, {
            "allowed": True,
            "current_usd": current_cost + cost_usd,
            "remaining_usd": remaining - cost_usd
        }

# Middleware integration
class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        rate_limit_service: RateLimitService,
        config_loader: Callable[[str], QuotaConfig]
    ):
        self.app = app
        self.rate_limit = rate_limit_service
        self.config_loader = config_loader

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract tenant ID from headers/auth
        tenant_id = self._extract_tenant_id(scope)
        if not tenant_id:
            await self._send_error(send, 401, "Missing tenant ID")
            return

        # Load quota config
        config = await self.config_loader(tenant_id)

        # Check rate limit
        allowed, info = await self.rate_limit.check_rate_limit(tenant_id, config)

        if not allowed:
            await self._send_error(send, 429, info)
            return

        # Add rate limit headers
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-ratelimit-remaining", str(info["remaining"]).encode()),
                    (b"x-ratelimit-limit", str(config.rate_limit.requests_per_second).encode()),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
```

**Implementation Steps:**

1. Create rate limiting service with Redis
2. Implement sliding window algorithm
3. Add token and cost quota tracking
4. Create middleware integration
5. Add quota configuration management
6. Create admin endpoints for quota management
7. Add comprehensive rate limit tests
8. Add metrics for rate limit hits

**Success Criteria:**
- [ ] Per-tenant rate limiting working
- [ ] Multi-window checks (RPS, RPM, RPH)
- [ ] Token and cost quotas enforced
- [ ] Rate limit headers in responses
- [ ] Admin API for quota management
- [ ] Metrics dashboard for quota usage

**Estimated Time:** 3-4 days

---

## Phase 3: Integration & Performance (Week 3-4)

### 3.1 Database Connection Pooling

**Objective:** Add proper async database connection pooling

**Current Issues:**
- Direct database connections without pooling
- Potential connection exhaustion
- No connection reuse

**Solution - asyncpg Connection Pool:**

```python
# database/pool.py
import asyncpg
from typing import Optional
from contextlib import asynccontextmanager

class DatabasePool:
    """Async PostgreSQL connection pool"""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(
        self,
        dsn: str,
        min_size: int = 10,
        max_size: int = 20,
        command_timeout: float = 60.0
    ):
        """Initialize connection pool"""
        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
            server_settings={
                'application_name': 'atp-router',
                'jit': 'off'  # Disable JIT for predictable performance
            }
        )

        logger.info(
            "Database pool initialized",
            min_size=min_size,
            max_size=max_size
        )

    async def close(self):
        """Close all connections"""
        if self._pool:
            await self._pool.close()
            logger.info("Database pool closed")

    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool"""
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args):
        """Execute query with connection from pool"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Fetch results with connection from pool"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Fetch single row with connection from pool"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

# Repository pattern with connection pool
class ObservationRepository:
    def __init__(self, db_pool: DatabasePool):
        self.db = db_pool

    async def save(self, observation: dict):
        """Save observation to database"""
        await self.db.execute(
            """
            INSERT INTO observations (
                request_id, model, latency_ms, cost_usd,
                quality_score, tokens, timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            observation["request_id"],
            observation["model"],
            observation["latency_ms"],
            observation["cost_usd"],
            observation.get("quality_score"),
            observation.get("tokens"),
            datetime.now()
        )

    async def get_recent(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        """Get recent observations"""
        rows = await self.db.fetch(
            """
            SELECT * FROM observations
            ORDER BY timestamp DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset
        )
        return [dict(row) for row in rows]
```

**Implementation Steps:**

1. Add asyncpg dependency
2. Create DatabasePool class
3. Implement repository pattern
4. Replace direct DB calls with pooled connections
5. Add connection pool metrics
6. Configure pool size based on load testing
7. Add comprehensive integration tests

**Success Criteria:**
- [ ] Connection pooling implemented
- [ ] All DB operations use pool
- [ ] Pool metrics exposed
- [ ] Connection exhaustion tests pass
- [ ] Performance improved under load

**Estimated Time:** 2 days

---

### 3.2 Integrate Rust Router

**Objective:** Complete integration of high-performance Rust router

**Current State:**
- Rust router POC exists but not integrated
- Python router handles all traffic
- Performance bottleneck at high scale

**Integration Architecture:**

```
┌─────────────────────────────────────────────────┐
│          FastAPI Python Service                 │
│  ┌──────────────────────────────────────────┐  │
│  │   API Layer (HTTP/WebSocket endpoints)   │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────────┐  │
│  │      Router Coordinator                  │  │
│  │  (Decides: Python vs Rust routing)       │  │
│  └────┬─────────────────────────────┬───────┘  │
│       │                             │           │
│       ▼                             ▼           │
│  ┌────────────┐            ┌─────────────────┐ │
│  │  Python    │            │  Rust Router    │ │
│  │  Router    │            │  (FFI/gRPC)     │ │
│  │  (Legacy)  │            │  - Hot path     │ │
│  └────────────┘            │  - 10x faster   │ │
│                            └─────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Implementation using PyO3 (Rust ↔ Python FFI):**

```rust
// atp-router/src/lib.rs
use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

#[pyclass]
struct RustRouter {
    adapters: Vec<AdapterInfo>,
}

#[pymethods]
impl RustRouter {
    #[new]
    fn new() -> Self {
        RustRouter {
            adapters: Vec::new(),
        }
    }

    fn register_adapter(&mut self, adapter_id: String, capabilities: Vec<String>) {
        // Register adapter in Rust registry
        self.adapters.push(AdapterInfo {
            id: adapter_id,
            capabilities,
        });
    }

    fn select_model(
        &self,
        prompt: String,
        quality_target: f64,
        max_cost: f64
    ) -> PyResult<String> {
        // High-performance model selection in Rust
        let selected = self.ucb_select(&prompt, quality_target, max_cost);
        Ok(selected.id)
    }

    fn select_model_batch(
        &self,
        prompts: Vec<String>,
        quality_target: f64,
        max_cost: f64
    ) -> PyResult<Vec<String>> {
        // Batch selection for throughput
        let results: Vec<String> = prompts
            .par_iter()  // Parallel processing
            .map(|prompt| {
                self.ucb_select(prompt, quality_target, max_cost).id
            })
            .collect();
        Ok(results)
    }
}

#[pymodule]
fn atp_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<RustRouter>()?;
    Ok(())
}
```

**Python Integration:**

```python
# router/rust_integration.py
import atp_rust
from typing import Optional

class HybridRouter:
    """Router that delegates to Rust for hot paths"""

    def __init__(self):
        self.rust_router = atp_rust.RustRouter()
        self.python_router = PythonRouter()  # Existing router
        self.use_rust = os.getenv("USE_RUST_ROUTER", "1") == "1"

    async def select_model(
        self,
        prompt: str,
        quality_target: str,
        max_cost: float
    ) -> str:
        """Select model using Rust or Python router"""

        if self.use_rust and len(prompt) < 10000:  # Use Rust for normal requests
            try:
                # Synchronous Rust call (fast enough)
                model_id = self.rust_router.select_model(
                    prompt,
                    self._quality_to_score(quality_target),
                    max_cost
                )
                return model_id
            except Exception as e:
                logger.warning("Rust router failed, falling back to Python", error=str(e))
                # Fallback to Python

        # Use Python router for complex cases or fallback
        return await self.python_router.select_model(prompt, quality_target, max_cost)

    async def select_model_batch(
        self,
        prompts: list[str],
        quality_target: str,
        max_cost: float
    ) -> list[str]:
        """Batch model selection (always use Rust for performance)"""
        if self.use_rust:
            try:
                return self.rust_router.select_model_batch(
                    prompts,
                    self._quality_to_score(quality_target),
                    max_cost
                )
            except Exception:
                logger.warning("Rust batch failed, falling back to Python")

        # Python fallback
        return await asyncio.gather(*[
            self.python_router.select_model(p, quality_target, max_cost)
            for p in prompts
        ])
```

**Build Integration (Maturin):**

```toml
# Cargo.toml
[package]
name = "atp-rust"
version = "0.1.0"
edition = "2021"

[lib]
name = "atp_rust"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.20", features = ["extension-module"] }
rayon = "1.8"  # Parallel processing
serde = { version = "1.0", features = ["derive"] }
tokio = { version = "1.0", features = ["full"] }
```

```bash
# Build script
#!/bin/bash
# build_rust.sh

cd atp-router
maturin develop --release
cd ..

# Copy built .so to router_service
cp atp-router/target/wheels/*.so router_service/
```

**Implementation Steps:**

1. Complete Rust router implementation
2. Add PyO3 bindings
3. Create hybrid router coordinator
4. Add feature flag for gradual rollout
5. Benchmark Rust vs Python performance
6. Create integration tests
7. Add monitoring for Rust vs Python split
8. Document build process

**Success Criteria:**
- [ ] Rust router handles 80%+ of traffic
- [ ] 10x performance improvement on hot path
- [ ] Zero regression in functionality
- [ ] Graceful fallback to Python
- [ ] Comprehensive benchmarks

**Estimated Time:** 5-7 days

---

### 3.3 ML-Based PII Detection

**Objective:** Replace rule-based PII detection with ML model

**Current Issues:**
- Rule-based regex patterns miss edge cases
- No context-aware detection
- High false positive rate

**Solution - Transformer-Based NER:**

```python
# security/ml_pii_detector.py
from transformers import AutoTokenizer, AutoModelForTokenClassification
import torch
from typing import List, Tuple
import re

class MLPIIDetector:
    """ML-based PII detection using NER model"""

    def __init__(
        self,
        model_name: str = "dslim/bert-base-NER",
        device: str = "cpu"
    ):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForTokenClassification.from_pretrained(model_name)
        self.device = device
        self.model.to(device)
        self.model.eval()

        # PII entity types
        self.pii_labels = {
            "PER",  # Person names
            "LOC",  # Locations (can be addresses)
            "ORG",  # Organizations
            "MISC"  # Miscellaneous (catch-all)
        }

        # Additional regex patterns for high-confidence PII
        self.patterns = {
            "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            "phone": re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
            "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
            "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        }

    def detect(self, text: str) -> List[Tuple[str, int, int, str]]:
        """
        Detect PII in text

        Returns:
            List of (entity_text, start_pos, end_pos, entity_type)
        """
        pii_entities = []

        # 1. Regex-based detection (high confidence)
        for pii_type, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                pii_entities.append((
                    match.group(),
                    match.start(),
                    match.end(),
                    pii_type
                ))

        # 2. ML-based NER detection
        tokens = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**tokens)
            predictions = torch.argmax(outputs.logits, dim=2)

        # Convert predictions to entities
        predicted_labels = [
            self.model.config.id2label[p.item()]
            for p in predictions[0]
        ]

        # Extract entities from BIO tagging
        current_entity = None
        current_start = None

        for idx, label in enumerate(predicted_labels):
            if label.startswith("B-") and label[2:] in self.pii_labels:
                # Beginning of entity
                if current_entity:
                    # Save previous entity
                    entity_text = text[current_start:self._get_token_end(tokens, idx-1)]
                    pii_entities.append((
                        entity_text,
                        current_start,
                        self._get_token_end(tokens, idx-1),
                        current_entity
                    ))

                current_entity = label[2:]
                current_start = self._get_token_start(tokens, idx)

            elif label.startswith("I-") and current_entity:
                # Inside entity, continue
                continue

            elif current_entity:
                # End of entity
                entity_text = text[current_start:self._get_token_end(tokens, idx-1)]
                pii_entities.append((
                    entity_text,
                    current_start,
                    self._get_token_end(tokens, idx-1),
                    current_entity
                ))
                current_entity = None
                current_start = None

        # Remove duplicates (prioritize regex matches)
        pii_entities = self._deduplicate_entities(pii_entities)

        return pii_entities

    def redact(self, text: str, redaction_char: str = "*") -> Tuple[str, int]:
        """
        Redact PII from text

        Returns:
            (redacted_text, num_redactions)
        """
        entities = self.detect(text)

        if not entities:
            return text, 0

        # Sort by position (reverse) to maintain indices
        entities.sort(key=lambda x: x[1], reverse=True)

        redacted_text = text
        for entity_text, start, end, entity_type in entities:
            # Replace with [REDACTED:TYPE]
            replacement = f"[REDACTED:{entity_type.upper()}]"
            redacted_text = redacted_text[:start] + replacement + redacted_text[end:]

        return redacted_text, len(entities)

    def _deduplicate_entities(
        self,
        entities: List[Tuple[str, int, int, str]]
    ) -> List[Tuple[str, int, int, str]]:
        """Remove overlapping entities, prioritizing regex matches"""
        if not entities:
            return []

        # Sort by start position
        sorted_entities = sorted(entities, key=lambda x: x[1])

        deduplicated = [sorted_entities[0]]

        for entity in sorted_entities[1:]:
            last = deduplicated[-1]

            # Check for overlap
            if entity[1] < last[2]:
                # Overlapping - keep the one with higher confidence
                # (regex patterns have priority)
                if entity[3] in ["email", "ssn", "phone", "credit_card"]:
                    deduplicated[-1] = entity
            else:
                deduplicated.append(entity)

        return deduplicated

# Service integration
class PIIDetectionService:
    """Service wrapper for PII detection"""

    def __init__(self, use_ml: bool = True):
        self.use_ml = use_ml

        if use_ml:
            self.ml_detector = MLPIIDetector()
        else:
            # Fallback to rule-based
            from .pii import detect_pii as rule_based_detect
            self.rule_based_detect = rule_based_detect

    async def detect_and_redact(
        self,
        text: str
    ) -> Tuple[str, List[str]]:
        """
        Detect and redact PII

        Returns:
            (redacted_text, list_of_detected_types)
        """
        if self.use_ml:
            # Run ML detection in thread pool (CPU-bound)
            loop = asyncio.get_event_loop()
            redacted_text, num_redactions = await loop.run_in_executor(
                None,
                self.ml_detector.redact,
                text
            )

            # Get types
            entities = await loop.run_in_executor(
                None,
                self.ml_detector.detect,
                text
            )
            detected_types = list(set(e[3] for e in entities))

            return redacted_text, detected_types
        else:
            # Use rule-based fallback
            return self.rule_based_detect(text)
```

**Implementation Steps:**

1. Select and test NER models (BERT, RoBERTa, etc.)
2. Implement ML PII detector
3. Create hybrid detector (ML + regex)
4. Add model caching and optimization
5. Create evaluation dataset
6. Benchmark accuracy vs rule-based
7. Add feature flag for gradual rollout
8. Create comprehensive tests

**Success Criteria:**
- [ ] Higher accuracy than rule-based (F1 > 0.95)
- [ ] Lower false positive rate (< 1%)
- [ ] Acceptable latency (< 100ms p95)
- [ ] Comprehensive test coverage
- [ ] Production monitoring

**Estimated Time:** 4-5 days

---

## Phase 4: Testing & Documentation (Week 4)

### 4.1 Comprehensive Integration Tests

**Objective:** Achieve 90%+ test coverage with integration tests

**Test Architecture:**

```python
# tests/integration/test_e2e_routing.py
import pytest
import asyncio
from httpx import AsyncClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
async def test_infrastructure():
    """Spin up test infrastructure"""

    # Start containers
    postgres = PostgresContainer("postgres:15")
    redis = RedisContainer("redis:7")

    postgres.start()
    redis.start()

    yield {
        "postgres_url": postgres.get_connection_url(),
        "redis_url": f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}"
    }

    # Teardown
    postgres.stop()
    redis.stop()

@pytest.fixture
async def test_client(test_infrastructure):
    """Create test client with real dependencies"""

    # Configure app with test infrastructure
    os.environ["DATABASE_URL"] = test_infrastructure["postgres_url"]
    os.environ["REDIS_URL"] = test_infrastructure["redis_url"]

    from router_service.core.app import create_app
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

class TestEndToEndRouting:
    """End-to-end routing tests"""

    @pytest.mark.asyncio
    async def test_complete_routing_flow(self, test_client):
        """Test complete request flow from API to adapter"""

        # 1. Register adapters
        adapters = [
            {"id": "gpt-4", "cost_per_1k": 0.03, "quality": 0.9},
            {"id": "claude-3", "cost_per_1k": 0.015, "quality": 0.85},
            {"id": "gpt-3.5", "cost_per_1k": 0.002, "quality": 0.7},
        ]

        for adapter in adapters:
            response = await test_client.post(
                "/admin/adapters",
                json=adapter
            )
            assert response.status_code == 200

        # 2. Make routing request
        response = await test_client.post(
            "/v1/ask",
            json={
                "prompt": "Explain quantum computing",
                "quality": "balanced",
                "max_cost_usd": 0.05
            }
        )

        assert response.status_code == 200

        # 3. Verify routing decision
        data = response.json()
        assert "model_used" in data
        assert data["model_used"] in ["gpt-4", "claude-3", "gpt-3.5"]

        # 4. Verify observation logged
        obs_response = await test_client.get("/admin/observations?limit=1")
        observations = obs_response.json()

        assert len(observations) == 1
        assert observations[0]["model"] == data["model_used"]

    @pytest.mark.asyncio
    async def test_rate_limiting(self, test_client):
        """Test per-tenant rate limiting"""

        tenant_id = "test-tenant"

        # Configure rate limit: 5 requests per second
        await test_client.post(
            "/admin/quotas",
            json={
                "tenant_id": tenant_id,
                "rate_limit": {"rps": 5}
            }
        )

        # Make 10 requests rapidly
        responses = await asyncio.gather(*[
            test_client.post(
                "/v1/ask",
                json={"prompt": f"Request {i}"},
                headers={"X-Tenant-ID": tenant_id}
            )
            for i in range(10)
        ])

        # Should have 5 successes and 5 rate limits
        success_count = sum(1 for r in responses if r.status_code == 200)
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        assert success_count == 5
        assert rate_limited_count == 5

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, test_client):
        """Test graceful shutdown with active connections"""

        # Open WebSocket connection
        async with test_client.websocket_connect("/ws") as websocket:

            # Send request
            await websocket.send_json({
                "type": "ask",
                "prompt": "Long running task"
            })

            # Trigger shutdown in background
            shutdown_task = asyncio.create_task(
                test_client.app.state.shutdown_coordinator.shutdown()
            )

            # Should receive response before shutdown
            response = await websocket.receive_json()
            assert response["type"] == "response"

            # Wait for shutdown
            await shutdown_task

            # Connection should be closed gracefully
            with pytest.raises(WebSocketDisconnect):
                await websocket.receive_json()

    @pytest.mark.asyncio
    async def test_pii_redaction(self, test_client):
        """Test PII detection and redaction"""

        response = await test_client.post(
            "/v1/ask",
            json={
                "prompt": "My email is john.doe@example.com and SSN is 123-45-6789"
            }
        )

        assert response.status_code == 200

        # Verify PII was redacted in logs/observations
        obs_response = await test_client.get("/admin/observations?limit=1")
        observation = obs_response.json()[0]

        assert "john.doe@example.com" not in observation["prompt"]
        assert "123-45-6789" not in observation["prompt"]
        assert "[REDACTED:EMAIL]" in observation["prompt"]
        assert "[REDACTED:SSN]" in observation["prompt"]

# Performance tests
class TestPerformance:
    """Performance and load tests"""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_throughput(self, test_client):
        """Test sustained throughput"""

        duration_seconds = 30
        target_rps = 100

        async def make_request():
            return await test_client.post(
                "/v1/ask",
                json={"prompt": "Test prompt"}
            )

        start_time = time.time()
        total_requests = 0
        errors = 0

        while time.time() - start_time < duration_seconds:
            # Send batch of requests
            batch_size = 10
            results = await asyncio.gather(
                *[make_request() for _ in range(batch_size)],
                return_exceptions=True
            )

            total_requests += batch_size
            errors += sum(1 for r in results if isinstance(r, Exception))

            # Rate limiting
            await asyncio.sleep(batch_size / target_rps)

        elapsed = time.time() - start_time
        actual_rps = total_requests / elapsed
        error_rate = errors / total_requests

        assert actual_rps >= target_rps * 0.9  # Within 10% of target
        assert error_rate < 0.01  # < 1% errors

    @pytest.mark.asyncio
    async def test_latency_p95(self, test_client):
        """Test P95 latency under load"""

        latencies = []

        for _ in range(100):
            start = time.time()
            response = await test_client.post(
                "/v1/ask",
                json={"prompt": "Test prompt"}
            )
            latency = (time.time() - start) * 1000  # ms

            assert response.status_code == 200
            latencies.append(latency)

        latencies.sort()
        p50 = latencies[49]
        p95 = latencies[94]
        p99 = latencies[98]

        assert p50 < 100  # P50 < 100ms
        assert p95 < 500  # P95 < 500ms
        assert p99 < 1000  # P99 < 1s
```

**Implementation Steps:**

1. Set up test infrastructure (testcontainers)
2. Create comprehensive integration test suite
3. Add performance/load tests
4. Add chaos testing (failure injection)
5. Create test fixtures and factories
6. Add property-based tests (Hypothesis)
7. Set up CI pipeline for tests
8. Generate coverage reports

**Success Criteria:**
- [ ] 90%+ test coverage
- [ ] All critical paths tested
- [ ] Performance tests passing
- [ ] Chaos tests validating resilience
- [ ] CI running all tests

**Estimated Time:** 5-6 days

---

### 4.2 Documentation Update

**Objective:** Comprehensive documentation for new architecture

**Documentation Structure:**

```
docs/
├── architecture/
│   ├── overview.md
│   ├── service-decomposition.md
│   ├── dependency-injection.md
│   ├── graceful-shutdown.md
│   └── rust-integration.md
├── operations/
│   ├── deployment.md
│   ├── monitoring.md
│   ├── secrets-management.md
│   ├── health-checks.md
│   └── scaling.md
├── development/
│   ├── setup.md
│   ├── testing.md
│   ├── contributing.md
│   └── debugging.md
├── api/
│   ├── rest-api.md
│   ├── websocket-api.md
│   ├── admin-api.md
│   └── openapi.yaml
└── security/
    ├── authentication.md
    ├── authorization.md
    ├── pii-handling.md
    └── compliance.md
```

**Implementation Steps:**

1. Create architecture diagrams (C4 model)
2. Write API documentation with examples
3. Create deployment guides
4. Write operational runbooks
5. Create troubleshooting guides
6. Generate API documentation from OpenAPI
7. Add inline code documentation
8. Create video tutorials (optional)

**Success Criteria:**
- [ ] Complete architecture documentation
- [ ] API documentation with examples
- [ ] Deployment guides for all platforms
- [ ] Operational runbooks
- [ ] Contributing guide updated

**Estimated Time:** 3-4 days

---

## Phase 5: Deployment & Validation (Week 5-6)

### 5.1 Production Deployment Strategy

**Blue-Green Deployment:**

```yaml
# deploy/k8s/blue-green.yaml
---
# Blue deployment (current production)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atp-router-blue
  labels:
    app: atp-router
    version: blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: atp-router
      version: blue
  template:
    metadata:
      labels:
        app: atp-router
        version: blue
    spec:
      containers:
      - name: router
        image: atp-router:v2.0.0
        # ... container spec

---
# Green deployment (new version)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atp-router-green
  labels:
    app: atp-router
    version: green
spec:
  replicas: 3
  selector:
    matchLabels:
      app: atp-router
      version: green
  template:
    metadata:
      labels:
        app: atp-router
        version: green
    spec:
      containers:
      - name: router
        image: atp-router:v2.1.0  # New version
        # ... container spec

---
# Service (initially points to blue)
apiVersion: v1
kind: Service
metadata:
  name: atp-router
spec:
  selector:
    app: atp-router
    version: blue  # Switch to 'green' after validation
  ports:
  - port: 7443
    targetPort: 7443
```

**Deployment Checklist:**

```bash
#!/bin/bash
# deploy.sh - Blue-Green Deployment Script

set -e

NAMESPACE="atp-production"
NEW_VERSION=$1
OLD_VERSION=$2

echo "Starting blue-green deployment..."
echo "Old version (blue): $OLD_VERSION"
echo "New version (green): $NEW_VERSION"

# 1. Deploy green (new version)
echo "Deploying green version..."
kubectl apply -f deploy/k8s/green-deployment.yaml
kubectl set image deployment/atp-router-green router=atp-router:$NEW_VERSION -n $NAMESPACE

# 2. Wait for green to be ready
echo "Waiting for green deployment..."
kubectl rollout status deployment/atp-router-green -n $NAMESPACE --timeout=5m

# 3. Run smoke tests against green
echo "Running smoke tests..."
GREEN_IP=$(kubectl get svc atp-router-green -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
python tests/smoke_tests.py --host $GREEN_IP

# 4. Validate green health
echo "Validating green health..."
curl -f http://$GREEN_IP:7443/healthz || exit 1
curl -f http://$GREEN_IP:7443/readyz || exit 1

# 5. Switch traffic to green
echo "Switching traffic to green..."
kubectl patch svc atp-router -n $NAMESPACE -p '{"spec":{"selector":{"version":"green"}}}'

# 6. Monitor for issues (5 minutes)
echo "Monitoring green deployment..."
sleep 300

# 7. Check error rates
ERROR_RATE=$(curl -s http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status="500"}[5m]) | jq '.data.result[0].value[1]')
if (( $(echo "$ERROR_RATE > 0.01" | bc -l) )); then
    echo "ERROR: High error rate detected, rolling back!"
    kubectl patch svc atp-router -n $NAMESPACE -p '{"spec":{"selector":{"version":"blue"}}}'
    exit 1
fi

# 8. Scale down blue
echo "Scaling down blue deployment..."
kubectl scale deployment/atp-router-blue --replicas=1 -n $NAMESPACE

echo "Deployment successful!"
echo "Green is now serving production traffic"
echo "Blue deployment kept at 1 replica for quick rollback"
```

**Implementation Steps:**

1. Create blue-green deployment manifests
2. Write deployment scripts with validation
3. Set up monitoring dashboards
4. Create rollback procedures
5. Test deployment in staging
6. Document deployment process
7. Train team on procedures

**Success Criteria:**
- [ ] Zero-downtime deployments working
- [ ] Automated rollback on errors
- [ ] Comprehensive monitoring
- [ ] Documented procedures
- [ ] Team trained

**Estimated Time:** 3-4 days

---

## Success Metrics & Monitoring

### Key Performance Indicators (KPIs)

1. **Performance:**
   - P50 latency < 100ms
   - P95 latency < 500ms
   - P99 latency < 1000ms
   - Throughput > 1000 RPS per instance

2. **Reliability:**
   - Uptime > 99.9%
   - Error rate < 0.1%
   - Graceful shutdown success rate 100%

3. **Quality:**
   - Test coverage > 90%
   - Zero critical security vulnerabilities
   - Code review coverage 100%

4. **Operations:**
   - Deployment time < 10 minutes
   - Mean time to recovery (MTTR) < 5 minutes
   - Incident response time < 15 minutes

### Monitoring Dashboard

```yaml
# Grafana dashboard configuration
dashboard:
  title: "ATP Router - Production Overview"
  panels:
    - title: "Request Rate"
      type: graph
      metrics:
        - rate(http_requests_total[5m])

    - title: "Latency"
      type: graph
      metrics:
        - histogram_quantile(0.50, http_request_duration_seconds)
        - histogram_quantile(0.95, http_request_duration_seconds)
        - histogram_quantile(0.99, http_request_duration_seconds)

    - title: "Error Rate"
      type: graph
      metrics:
        - rate(http_requests_total{status=~"5.."}[5m])

    - title: "Active Connections"
      type: graph
      metrics:
        - websocket_connections_active

    - title: "Rate Limit Hits"
      type: graph
      metrics:
        - rate(rate_limit_hits_total[5m])

    - title: "Database Pool"
      type: graph
      metrics:
        - db_pool_connections_active
        - db_pool_connections_idle

    - title: "Rust vs Python Routing"
      type: pie
      metrics:
        - routing_backend{type="rust"}
        - routing_backend{type="python"}
```

---

## Risk Management

### High-Risk Items

1. **Rust Integration Complexity**
   - Risk: Integration issues, performance not as expected
   - Mitigation: Feature flag, gradual rollout, comprehensive benchmarking
   - Contingency: Keep Python router as fallback

2. **Database Migration**
   - Risk: Data loss, downtime during migration
   - Mitigation: Blue-green database deployment, comprehensive backups
   - Contingency: Rollback scripts, point-in-time recovery

3. **Breaking API Changes**
   - Risk: Client integrations break
   - Mitigation: API versioning, deprecation notices, backward compatibility
   - Contingency: Maintain v1 API alongside v2

### Medium-Risk Items

1. **Performance Regression**
   - Mitigation: Comprehensive benchmarking, canary deployments
   - Contingency: Feature flags to disable new features

2. **Test Coverage Gaps**
   - Mitigation: Code review focus on tests, coverage gates in CI
   - Contingency: Add tests before deployment

---

## Timeline & Resource Allocation

### Phase-by-Phase Breakdown

**Week 1: Architecture Refactoring**
- Days 1-5: Service decomposition
- Days 2-3: Graceful shutdown
- Days 3-4: Dependency injection

**Week 2: Security & Operations**
- Days 1-5: Secrets management (Vault)
- Days 2-3: Health check system
- Days 3-4: Rate limiting

**Week 3: Performance & Integration**
- Days 1-2: Database pooling
- Days 3-7: Rust integration
- Days 4-5: ML PII detection

**Week 4: Testing & Documentation**
- Days 1-6: Integration test suite
- Days 3-4: Documentation

**Week 5: Deployment Prep**
- Days 1-3: Blue-green setup
- Days 3-4: Staging deployment
- Day 5: Production readiness review

**Week 6: Production Deployment**
- Day 1: Production deployment
- Days 2-5: Monitoring and fine-tuning

### Resource Requirements

- **Senior Backend Engineer:** 1 FTE (architecture, integration)
- **DevOps Engineer:** 0.5 FTE (deployment, monitoring)
- **ML Engineer:** 0.5 FTE (PII detection)
- **QA Engineer:** 0.5 FTE (testing)
- **Technical Writer:** 0.25 FTE (documentation)

---

## Conclusion

This comprehensive enterprise overhaul plan transforms the ATP/AGP platform from a sophisticated POC into a production-ready, enterprise-grade LLM routing and orchestration system. By addressing architectural, security, operational, and integration challenges systematically, we'll achieve:

- **10x performance improvement** through Rust integration
- **Zero-downtime deployments** with graceful shutdown
- **Enterprise-grade security** with Vault integration
- **90%+ test coverage** with comprehensive integration tests
- **Production-ready operations** with full observability

The phased approach minimizes risk while delivering incremental value. Each phase builds on the previous, with clear success criteria and contingency plans.

**Next Steps:**
1. Review and approve this plan
2. Set up development environment
3. Begin Phase 1: Architecture Refactoring
4. Weekly check-ins to track progress
5. Adjust timeline based on learnings

---

**Document Control:**
- Version: 1.0
- Author: Senior Network AI Engineer
- Date: 2025-11-13
- Status: Active
- Next Review: Weekly during implementation
