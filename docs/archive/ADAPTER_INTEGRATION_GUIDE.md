# ATP Adapter Integration Guide

**Purpose**: Step-by-step guide for integrating real LLM adapters into the ATP router's main request flow

**Last Updated**: 2025-11-18
**Status**: Integration in progress
**Estimated Effort**: 2-3 days for core integration

---

## Table of Contents

1. [Current State Overview](#current-state-overview)
2. [Integration Architecture](#integration-architecture)
3. [Prerequisites](#prerequisites)
4. [Step-by-Step Integration Guide](#step-by-step-integration-guide)
5. [Code Examples](#code-examples)
6. [Testing Approach](#testing-approach)
7. [Deployment Considerations](#deployment-considerations)
8. [Rollback Plan](#rollback-plan)

---

## Current State Overview

### What Currently Happens

**File**: `router_service/service.py:1408-1449`

```python
# Current implementation (SYNTHETIC)
while generated < target_tokens:
    chunk = min(12, target_tokens - generated)
    generated += chunk
    await asyncio.sleep(chunk / primary_speed)
    phrase = "lorem" if generated < target_tokens else "done"  # ❌ Synthetic!
    async for out in emit(primary.name, phrase):
        yield out
```

**Issues**:
- No real adapter calls
- Generates "lorem" placeholder text
- Random quality scores: `random.uniform(0.7, 0.9)`
- Fake cost calculations

### What Should Happen

```python
# Desired implementation (REAL)
async for chunk in adapter_client.Stream(prompt, model_id):
    # Real LLM response chunks
    yield chunk
```

### Architecture Components

| Component | Status | Notes |
|-----------|--------|-------|
| **AdapterRegistry** | ✅ Built | `router_service/adapter_registry.py` |
| **gRPC Protocol** | ✅ Defined | `tools/adapter_pb2.py`, `adapter_pb2_grpc.py` |
| **Anthropic Adapter** | ✅ Production-Ready | `adapters/python/anthropic_adapter/server.py` |
| **OpenAI Adapter** | ✅ Production-Ready | `adapters/python/openai_adapter/server.py` |
| **Router Integration** | ❌ **Missing** | Needs implementation in `service.py` |

---

## Integration Architecture

### gRPC Adapter Service Protocol

Defined in `adapter.proto`, adapters expose three methods:

#### 1. **Estimate** - Cost/token estimation
```protobuf
message EstimateRequest {
    string stream_id = 1;
    string task_type = 2;
    string prompt_json = 3;
}

message EstimateResponse {
    uint64 in_tokens = 1;
    uint64 out_tokens = 2;
    uint64 usd_micros = 3;          // Cost in USD micros (1 USD = 1,000,000 micros)
    uint64 p95_tokens = 4;
    uint64 p95_usd_micros = 5;
    double variance_tokens = 6;
    double variance_usd = 7;
    double confidence = 8;
}
```

#### 2. **Stream** - Real-time inference (streaming)
```protobuf
message StreamRequest {
    string stream_id = 1;
    string prompt_json = 2;
}

message StreamChunk {
    string type = 1;                // "text", "tool_call", "done"
    string content_json = 2;        // JSON-encoded content
    double confidence = 3;
    uint64 partial_in_tokens = 4;
    uint64 partial_out_tokens = 5;
    uint64 partial_usd_micros = 6;
    bool more = 7;                  // true if more chunks coming
}
```

#### 3. **Health** - Health check
```protobuf
message HealthRequest {}

message HealthResponse {
    double p95_ms = 1;
    double error_rate = 2;
}
```

### Adapter Registry System

**File**: `router_service/adapter_registry.py`

```python
class AdapterCapability:
    adapter_id: str
    adapter_type: str
    capabilities: list[str]
    models: list[str]
    max_tokens: int | None
    cost_per_token_micros: int | None
    health_endpoint: str | None
    # ... performance metrics

class AdapterRegistry:
    def register_capability(self, capability_data: dict) -> bool
    def get_adapter(self, adapter_id: str) -> AdapterCapability | None
    def get_adapters_by_type(self, adapter_type: str) -> list[AdapterCapability]
    def heartbeat(self, adapter_id: str) -> bool
    def cleanup_stale_adapters(self, timeout_seconds: int = 300) -> int
```

### Production Adapter Example (Anthropic)

**File**: `adapters/python/anthropic_adapter/server.py`

Key features:
- Real Anthropic API integration (`anthropic` Python SDK)
- Streaming support with `AsyncIterator[adapter_pb2.StreamChunk]`
- Token counting and cost calculation
- Error handling and retries
- gRPC server implementation

---

## Prerequisites

### 1. Environment Setup

Ensure these environment variables are set:

```bash
# Required for router
ROUTER_ADMIN_API_KEY=your-admin-key-32-chars-minimum

# Required for production adapters
ANTHROPIC_API_KEY=sk-ant-...    # For Anthropic adapter
OPENAI_API_KEY=sk-...           # For OpenAI adapter

# Optional: Adapter endpoints (if not using docker-compose)
ANTHROPIC_ADAPTER_URL=localhost:7073
OPENAI_ADAPTER_URL=localhost:7074
```

### 2. Start Adapter Services

```bash
# Using docker-compose (recommended)
docker compose up anthropic_adapter -d
docker compose up openai_adapter -d

# Verify adapters are running
curl http://localhost:7073/health  # Anthropic
curl http://localhost:7074/health  # OpenAI
```

### 3. Adapter Registration

Adapters can self-register on startup or be manually registered:

```python
from router_service.adapter_registry import get_adapter_registry

registry = get_adapter_registry()

# Example: Register Anthropic adapter
registry.register_capability({
    "adapter_id": "anthropic-1",
    "adapter_type": "anthropic",
    "capabilities": ["text-generation", "streaming", "function-calling"],
    "models": [
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307"
    ],
    "max_tokens": 4096,
    "cost_per_token_micros": 3000,  # $0.003 per 1K tokens (input)
    "health_endpoint": "http://localhost:7073/health",
    "version": "1.0.0"
})
```

---

## Step-by-Step Integration Guide

### Phase 1: Adapter Client Infrastructure

#### Step 1.1: Create Adapter Client Module

**File**: `router_service/adapters/client.py` (NEW)

```python
"""gRPC client for communicating with adapters."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import grpc
from tools import adapter_pb2, adapter_pb2_grpc

logger = logging.getLogger(__name__)


class AdapterClient:
    """gRPC client for adapter communication."""

    def __init__(self, adapter_endpoint: str, timeout: float = 30.0):
        """Initialize adapter client.

        Args:
            adapter_endpoint: gRPC endpoint (e.g., "localhost:7073")
            timeout: Request timeout in seconds
        """
        self.endpoint = adapter_endpoint
        self.timeout = timeout
        self._channel: grpc.aio.Channel | None = None
        self._stub: adapter_pb2_grpc.AdapterServiceStub | None = None

    async def connect(self) -> None:
        """Establish gRPC connection."""
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.endpoint)
            self._stub = adapter_pb2_grpc.AdapterServiceStub(self._channel)
            logger.info(f"Connected to adapter at {self.endpoint}")

    async def close(self) -> None:
        """Close gRPC connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def estimate(
        self,
        prompt: str,
        task_type: str = "completion",
        stream_id: str | None = None
    ) -> dict[str, Any]:
        """Get cost/token estimate for a prompt.

        Args:
            prompt: User prompt
            task_type: Type of task (completion, chat, etc.)
            stream_id: Optional stream ID

        Returns:
            Dictionary with estimation results
        """
        await self.connect()

        request = adapter_pb2.EstimateRequest(
            stream_id=stream_id or "",
            task_type=task_type,
            prompt_json=prompt
        )

        try:
            response = await self._stub.Estimate(request, timeout=self.timeout)
            return {
                "in_tokens": response.in_tokens,
                "out_tokens": response.out_tokens,
                "usd_micros": response.usd_micros,
                "p95_tokens": response.p95_tokens,
                "p95_usd_micros": response.p95_usd_micros,
                "confidence": response.confidence,
            }
        except grpc.RpcError as e:
            logger.error(f"Estimate RPC failed: {e.code()} - {e.details()}")
            raise

    async def stream(
        self,
        prompt: str,
        stream_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream inference results.

        Args:
            prompt: User prompt
            stream_id: Optional stream ID

        Yields:
            Dictionary chunks with content and metadata
        """
        await self.connect()

        request = adapter_pb2.StreamRequest(
            stream_id=stream_id or "",
            prompt_json=prompt
        )

        try:
            async for chunk in self._stub.Stream(request, timeout=self.timeout):
                yield {
                    "type": chunk.type,
                    "content_json": chunk.content_json,
                    "confidence": chunk.confidence,
                    "partial_in_tokens": chunk.partial_in_tokens,
                    "partial_out_tokens": chunk.partial_out_tokens,
                    "partial_usd_micros": chunk.partial_usd_micros,
                    "more": chunk.more,
                }
        except grpc.RpcError as e:
            logger.error(f"Stream RPC failed: {e.code()} - {e.details()}")
            raise

    async def health(self) -> dict[str, Any]:
        """Check adapter health.

        Returns:
            Dictionary with health metrics
        """
        await self.connect()

        request = adapter_pb2.HealthRequest()

        try:
            response = await self._stub.Health(request, timeout=5.0)
            return {
                "p95_ms": response.p95_ms,
                "error_rate": response.error_rate,
            }
        except grpc.RpcError as e:
            logger.error(f"Health RPC failed: {e.code()} - {e.details()}")
            raise


class AdapterClientPool:
    """Pool of adapter clients for load balancing."""

    def __init__(self):
        self._clients: dict[str, AdapterClient] = {}

    def get_client(self, adapter_endpoint: str) -> AdapterClient:
        """Get or create client for endpoint."""
        if adapter_endpoint not in self._clients:
            self._clients[adapter_endpoint] = AdapterClient(adapter_endpoint)
        return self._clients[adapter_endpoint]

    async def close_all(self) -> None:
        """Close all clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
```

#### Step 1.2: Add Configuration

**File**: `router_service/config.py` (UPDATE)

Add adapter configuration:

```python
@dataclass
class Settings:
    # ... existing fields ...

    # Adapter configuration
    adapter_endpoints: dict[str, str] = field(default_factory=lambda: {
        "anthropic": os.getenv("ANTHROPIC_ADAPTER_URL", "localhost:7073"),
        "openai": os.getenv("OPENAI_ADAPTER_URL", "localhost:7074"),
    })

    adapter_timeout: float = float(os.getenv("ADAPTER_TIMEOUT", "30.0"))
    adapter_health_check_interval: int = int(os.getenv("ADAPTER_HEALTH_CHECK_INTERVAL", "60"))
```

### Phase 2: Integrate into Model Selection

#### Step 2.1: Load Real Model Catalog from Adapters

**File**: `router_service/routing_constants.py` (UPDATE)

```python
"""Shared constants for routing functionality."""

from dataclasses import dataclass
from router_service.adapter_registry import get_adapter_registry


@dataclass
class Candidate:
    name: str
    cost_per_1k_tokens: float
    quality_pred: float  # 0-1
    latency_p95: int  # ms
    region: str = "us-west"  # Default region
    adapter_type: str = ""  # NEW: Track which adapter provides this model
    adapter_endpoint: str = ""  # NEW: Adapter endpoint


def load_catalog_from_adapters() -> list[Candidate]:
    """Load model catalog dynamically from registered adapters.

    Returns:
        List of candidates from all registered adapters
    """
    registry = get_adapter_registry()
    catalog = []

    for adapter in registry.get_all_adapters():
        if not adapter.is_healthy():
            continue  # Skip unhealthy adapters

        for model_id in adapter.models:
            candidate = Candidate(
                name=model_id,
                cost_per_1k_tokens=(adapter.cost_per_token_micros or 1000) / 1_000_000.0,
                quality_pred=0.80,  # Default, can be learned
                latency_p95=int(adapter.p95_latency_ms or 1000),
                region="us-west",  # Can be from adapter metadata
                adapter_type=adapter.adapter_type,
                adapter_endpoint=adapter.health_endpoint or "",
            )
            catalog.append(candidate)

    if not catalog:
        # Fallback to static catalog if no adapters registered
        catalog = STATIC_CATALOG

    return catalog


# Static fallback catalog (for testing/development)
STATIC_CATALOG = [
    Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
    Candidate("exp-model", 0.8, 0.78, 950, "us-east"),
    Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
    Candidate("premium-model", 2.0, 0.90, 1400, "asia-east"),
]

# Dynamic catalog (loaded from adapters)
CATALOG = load_catalog_from_adapters()

QUALITY_THRESH = {"fast": 0.60, "balanced": 0.75, "high": 0.85}
```

### Phase 3: Replace Synthetic Generation with Real Adapter Calls

**File**: `router_service/service.py:1408-1449` (CRITICAL UPDATE)

#### Step 3.1: Import Adapter Client

Add to imports at top of file:

```python
from router_service.adapters.client import AdapterClient, AdapterClientPool
import json
```

#### Step 3.2: Initialize Adapter Pool

Add to service initialization:

```python
# Global adapter client pool
_adapter_pool = AdapterClientPool()


@app.on_event("shutdown")
async def shutdown_adapters():
    """Cleanup adapter connections on shutdown."""
    await _adapter_pool.close_all()
```

#### Step 3.3: Replace Synthetic Loop

Replace lines 1408-1449 with:

```python
# Get adapter endpoint for selected model
adapter_endpoint = None
if hasattr(primary, 'adapter_endpoint') and primary.adapter_endpoint:
    # Extract endpoint from health_endpoint (e.g., "http://localhost:7073/health" -> "localhost:7073")
    import re
    match = re.search(r'([a-zA-Z0-9.-]+:\d+)', primary.adapter_endpoint)
    if match:
        adapter_endpoint = match.group(1)

if not adapter_endpoint:
    # Fallback to configuration
    adapter_type = getattr(primary, 'adapter_type', 'anthropic')
    adapter_endpoint = settings.adapter_endpoints.get(adapter_type, "localhost:7073")

# Get adapter client
adapter_client = _adapter_pool.get_client(adapter_endpoint)

# Prepare prompt JSON
prompt_json = json.dumps({
    "messages": [{"role": "user", "content": prompt_in}],
    "model": primary.name,
    "max_tokens": target_tokens,
    "temperature": 0.7,
})

# Stream from real adapter
generated_tokens = 0
adapter_cost_micros = 0
try:
    async for chunk in adapter_client.stream(prompt_json, stream_id=sess_id):
        chunk_type = chunk["type"]
        content = json.loads(chunk["content_json"]) if chunk["content_json"] else {}

        if chunk_type == "text":
            text_content = content.get("text", "")
            text_parts.append(text_content)

            # Emit to client
            async for out in emit(primary.name, text_content):
                yield out

        # Track tokens and cost
        generated_tokens += chunk["partial_out_tokens"]
        adapter_cost_micros += chunk["partial_usd_micros"]

        # Check for completion
        if not chunk["more"]:
            break

        # Client disconnection check
        try:
            if await request.is_disconnected():
                logger.info(f"Client disconnected: {sess_id}")
                break
        except Exception as err:
            logger.debug(f"Disconnect check failed: {err}")

except Exception as e:
    logger.error(f"Adapter stream failed: {e}", exc_info=True)
    # Emit error to client
    yield json.dumps({"type": "error", "error": str(e)}) + "\n"
    # Fall back to synthetic response or raise
    raise

# Calculate final metrics
quality = _evaluate_quality(" ".join(text_parts)) if settings.quality_eval_mode != "off" else 0.85
total = time.time() - start
duration_ms = total * 1000.0
_record_latency(duration_ms)
_ctr_req.inc()
_ctr_duration_sum.inc(int(round(duration_ms)))
if _hist_latency:
    _hist_latency.observe(duration_ms)

# Cost from adapter (convert micros to USD)
cost_usd = adapter_cost_micros / 1_000_000.0

# Calculate savings (compare to baseline)
baseline = (generated_tokens / 1000.0) * 2.0  # $2 per 1K tokens baseline
savings = (baseline - cost_usd) / baseline * 100 if baseline > 0 else 0.0
```

---

## Code Examples

### Example 1: Full Request Flow with Adapter

```python
@app.post("/v1/ask")
async def ask(req: AskRequest, request: Request) -> StreamingResponse:
    """Handle AI completion request with real adapter integration."""

    # 1. Model selection (existing logic - works!)
    plan, regret_analysis, routing_metadata = choose(
        req.quality,
        req.latency_slo_ms,
        CATALOG,  # Now loaded from adapters!
        "A"
    )

    primary = plan[0] if plan else CATALOG[0]

    # 2. Get adapter client
    adapter_endpoint = extract_endpoint(primary.adapter_endpoint)
    client = _adapter_pool.get_client(adapter_endpoint)

    # 3. Stream from adapter
    async def generate():
        async for chunk in client.stream(prompt_json):
            if chunk["type"] == "text":
                yield format_chunk(chunk)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Example 2: Adapter Health Monitoring

```python
async def monitor_adapter_health():
    """Background task to monitor adapter health."""
    registry = get_adapter_registry()

    while True:
        for adapter in registry.get_all_adapters():
            try:
                client = _adapter_pool.get_client(adapter.health_endpoint)
                health = await client.health()

                # Update registry with health metrics
                registry.update_health_telemetry(adapter.adapter_id, {
                    "p95_latency_ms": health["p95_ms"],
                    "error_rate": health["error_rate"],
                })
            except Exception as e:
                logger.warning(f"Health check failed for {adapter.adapter_id}: {e}")

        # Cleanup stale adapters
        registry.cleanup_stale_adapters(timeout_seconds=300)

        await asyncio.sleep(60)  # Check every minute


# Start monitoring on app startup
@app.on_event("startup")
async def start_monitoring():
    asyncio.create_task(monitor_adapter_health())
```

---

## Testing Approach

### Unit Tests

**File**: `tests/test_adapter_integration.py` (NEW)

```python
import pytest
from router_service.adapters.client import AdapterClient


@pytest.mark.asyncio
async def test_adapter_stream():
    """Test streaming from Anthropic adapter."""
    client = AdapterClient("localhost:7073")

    chunks = []
    async for chunk in client.stream("Hello, Claude!"):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any(chunk["type"] == "text" for chunk in chunks)


@pytest.mark.asyncio
async def test_adapter_estimate():
    """Test cost estimation."""
    client = AdapterClient("localhost:7073")

    estimate = await client.estimate("Write a short story")

    assert estimate["in_tokens"] > 0
    assert estimate["out_tokens"] > 0
    assert estimate["usd_micros"] > 0
```

### Integration Tests

**File**: `tests/integration/test_end_to_end_adapter.py` (NEW)

```python
import pytest
from fastapi.testclient import TestClient
from router_service.service import app


def test_ask_endpoint_with_real_adapter():
    """Test /v1/ask with real Anthropic adapter."""
    client = TestClient(app)

    response = client.post("/v1/ask", json={
        "prompt": "What is 2+2?",
        "quality": "balanced"
    })

    assert response.status_code == 200

    # Parse streamed response
    text = ""
    for line in response.iter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:])
            if data["type"] == "chunk":
                text += data["text"]

    # Response should NOT be "lorem"
    assert "lorem" not in text.lower()
    # Response should contain actual content
    assert len(text) > 10
```

### Load Testing

```bash
# Use locust or similar tool
pip install locust

# Create locustfile.py
locust -f tests/load/locustfile.py --host http://localhost:7443
```

---

## Deployment Considerations

### 1. Feature Flag

Add feature flag to enable/disable adapter integration:

```python
# config.py
use_real_adapters: bool = os.getenv("USE_REAL_ADAPTERS", "0") == "1"

# service.py
if settings.use_real_adapters:
    # Use adapter client
    async for chunk in adapter_client.stream(...):
        yield chunk
else:
    # Use synthetic (fallback for testing)
    yield synthetic_response()
```

### 2. Gradual Rollout

```python
# service.py
import random

# Roll out to percentage of traffic
rollout_percentage = int(os.getenv("ADAPTER_ROLLOUT_PERCENT", "0"))
use_adapter = random.randint(1, 100) <= rollout_percentage

if use_adapter:
    # Real adapter
else:
    # Synthetic
```

### 3. Monitoring

Add metrics:

```python
from metrics.registry import REGISTRY

adapter_requests = REGISTRY.counter("adapter_requests_total", ["adapter_type", "status"])
adapter_latency = REGISTRY.histogram("adapter_latency_seconds", ["adapter_type"])
adapter_errors = REGISTRY.counter("adapter_errors_total", ["adapter_type", "error_code"])
```

### 4. Circuit Breaker

Implement circuit breaker to fall back to synthetic mode if adapters fail:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = 0
        self.is_open = False

    async def call(self, func, *args, **kwargs):
        if self.is_open:
            if time.time() - self.last_failure_time > self.timeout:
                self.is_open = False
                self.failure_count = 0
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.is_open = True
            raise
```

---

## Rollback Plan

### If Integration Fails

1. **Immediate**: Set `USE_REAL_ADAPTERS=0`
2. **Quick**: Revert service.py to commit before integration
3. **Deploy**: Redeploy with synthetic mode

```bash
# Emergency rollback
export USE_REAL_ADAPTERS=0
docker compose restart router

# Or revert code
git revert <integration-commit-hash>
git push origin main
docker compose up router -d --build
```

### Gradual Rollback

```bash
# Reduce rollout percentage
export ADAPTER_ROLLOUT_PERCENT=0
# Gradually: 100% -> 50% -> 25% -> 0%
```

---

## Next Steps

1. **Implement Phase 1**: Create AdapterClient infrastructure
2. **Implement Phase 2**: Update model catalog loading
3. **Implement Phase 3**: Replace synthetic generation
4. **Add Tests**: Unit, integration, and E2E tests
5. **Feature Flag Rollout**: Start at 10%, monitor, increase gradually
6. **Monitor**: Watch metrics, error rates, latency
7. **Optimize**: Profile and optimize performance
8. **Document**: Update all documentation

---

## Reference

- **Adapter Protocol**: `tools/adapter_pb2.py`
- **Registry**: `router_service/adapter_registry.py`
- **Anthropic Adapter**: `adapters/python/anthropic_adapter/server.py`
- **OpenAI Adapter**: `adapters/python/openai_adapter/server.py`
- **Current Implementation**: `router_service/service.py:1408-1449`
- **Audit Report**: `CODEBASE_AUDIT_REPORT.md`

---

**Status**: Ready for implementation
**Estimated Timeline**: 2-3 days for core integration + testing
**Risk Level**: Medium (rollback plan in place)
