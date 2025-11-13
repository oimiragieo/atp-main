# ATP/AGP Proof of Concept Bundle

![Coverage](https://img.shields.io/badge/coverage-84%25-brightgreen)

## Installation

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for development)
- Rust 1.70+ (for router development)
- Node.js 18+ (for client development)

### Quick Start (Docker)
```bash
# 1) Clone the repository
git clone <repository-url>
cd atp-main

# 2) Build & run everything
docker compose build
docker compose up -d

# 3) Sanity checks
python client/health_check.py        # checks /healthz on router + memory gateway
python client/memory_put_get.py      # puts/gets/searches an object
```

### Development Setup
```bash
# Install Python dependencies
pip install -r requirements-dev.txt

# Install Rust dependencies (for router)
cd atp-router
cargo build

# Start services individually
docker compose up memory-gateway -d
docker compose up router -d
```

## Usage

### Health Checks
```bash
# Check all services
python client/health_check.py

# Individual service health
curl http://localhost:7443/healthz  # Router
curl http://localhost:8080/healthz  # Memory Gateway
```

### Memory Operations
```bash

# MCP CLI usage
- **Grafana**: http://localhost:3000 (admin/admin)
- **Router Metrics**: http://localhost:7443/metrics

## Deployment

### Docker Compose (Recommended)
```bash
# Production deployment
docker compose -f docker-compose.yml up -d

# With custom environment
ROUTER_RPS_LIMIT=100 docker compose up -d
```

 
### Kubernetes
 
```bash
# Deploy to Kubernetes
kubectl apply -f deploy/kubernetes/

# Check deployment status
kubectl get pods
kubectl get services
```

 
### Environment Variables
 
```bash
# Router Configuration
ROUTER_RPS_LIMIT=100              # Rate limit (requests per second)
ROUTER_MAX_PROMPT_CHARS=6000      # Maximum prompt length
ROUTER_ENABLE_TRACING=1           # Enable OpenTelemetry tracing
ROUTER_OTLP_ENDPOINT=http://otel-collector:4317

# Memory Gateway
MEMORY_QUOTA_MB=1024              # Memory quota per tenant
MEMORY_TTL_SECONDS=3600           # Default TTL for stored objects

# Adapters
OLLAMA_BASE_URL=http://ollama:11434  # Ollama server URL
PERSONA_MODEL_ENDPOINT=http://persona-model:8080
```

 
### Scaling
 
```bash
# Scale router instances
docker compose up -d --scale router=3

# Scale adapters
docker compose up -d --scale ollama_adapter=2
docker compose up -d --scale persona_adapter=2
```

 
## What’s here
 
- `docs/` — specs & guides (ATP, AGP, Personas, State Diagrams, Security, MCP, SMF, Docker POC).
- `atp-router/` — Rust workspace (router scaffold + adapter protos + schema).
- `atp-router/adapters/python/` — example persona/ollama adapters (toy stubs).
- `services/memory-gateway/` — POC FastAPI KV store with simple search.
- `observability/` — Prometheus scrape config.
- `docker-compose.yml` — spins router + adapters + memory + prometheus.
- `router_service/` — Python router PoC with:
  - Weighted fair scheduler (starvation-aware) + AIMD flow control
  - Pluggable in-memory / Redis state backends
  - Bandit model selection (UCB / Thompson)
  - Streaming ask endpoint (Server-Sent style JSON lines)
  - Tracing spans (when enabled): ask, fair.acquire, fair.select, bandit.select, aimd.feedback
  - Error taxonomy POC: exceptions map to stable error codes (`router_service/error_mapping.py`);

    `marshal_exception()` yields structured payloads and increments per-code counters (`error_code_<code>_total`).
 
## Tracing

Tracing is optional. Enable with environment variable `ROUTER_ENABLE_TRACING=1`.

Two modes exist:
 
- Real OpenTelemetry: default if `opentelemetry` packages are installed. Exports to OTLP endpoint defined by `ROUTER_OTLP_ENDPOINT` (default `http://localhost:4317`). Set `ROUTER_DISABLE_OTLP_EXPORT=1` to suppress network export while still recording spans internally for tests.
- Dummy in-process tracer: used automatically if OTel deps missing or force with `ROUTER_TEST_TRACING_MODE=dummy`. Spans are stored in-memory (`router_service.tracing.SPAN_RECORDS`) with attributes for lightweight assertions.

Key spans & attributes:
 
- ask: overall request lifecycle (future expansion)
- fair.acquire: attribute `fair.fast_path` indicates immediate grant
- fair.select: `fair.granted_session`, `fair.wait_ms` (max observed wait so far)
- bandit.select: `bandit.choice`, `bandit.strategy`
- aimd.feedback: `aimd.session`, `aimd.before`, `aimd.after`, `aimd.latency_ms`, `aimd.ok`

Testing spans: run `pytest -q tests/test_tracing_spans.py` with `ROUTER_ENABLE_TRACING=1` (dummy tracer forced inside test).
  - Admin RBAC with key rotation & audit log (create/delete keys produce audit events)
  - PII scrubbing, observation logging, lifecycle promotion/demotion logic

## Adapter Capability Advertisement

Adapters can advertise their capabilities to the ATP Router via WebSocket frames. This enables dynamic discovery and registration of adapter capabilities.

 
### Python SDK Usage
 
```python
from tools.atp_sdk import ATPWebSocketClient, SDKConfig

config = SDKConfig(
    base_url="http://localhost:8000",
    ws_url="ws://localhost:8000",
    tenant_id="my-tenant"
)

client = ATPWebSocketClient(config)
await client.connect()

# Advertise adapter capabilities
capability_frame = client.frame_builder.build_capability_frame(
    stream_id="capability-advertisement",
    adapter_id="my-ollama-adapter",
    adapter_type="ollama",
    capabilities=["text-generation", "embedding"],
    models=["llama2:7b", "codellama:13b"],
    max_tokens=4096,
    version="1.0.0"
)

await client.send_frame(capability_frame)
```

### Go SDK Usage
```go
config := atpsdk.SDKConfig{
    BaseURL:   "http://localhost:8000",
    WSURL:     "ws://localhost:8000",
client := atpsdk.NewATPClient(config)
err := client.Connect()
if err != nil {
    log.Fatal(err)
## Examples

- Admin Aggregator (read-only monitoring backend): see `admin_aggregator/README.md`
- Next.js POC dashboard: `client/nextjs_poc/pages/admin.js` (set `NEXT_PUBLIC_AGGREGATOR_URL`)
}

capability := atpsdk.CapabilityAdvertisement{
    AdapterID:    "my-ollama-adapter",
    AdapterType:  "ollama",
    Capabilities: []string{"text-generation", "embedding"},
    Models:       []string{"llama2:7b", "codellama:13b"},
    MaxTokens:    &[]int{4096}[0],
    Version:      &[]string{"1.0.0"}[0],
}

err = client.AdvertiseCapabilities(context.Background(), capability)
```

### Metrics
- `adapters_registered`: Gauge tracking the number of currently registered adapters

## Health Status Reporting
```python
# Report adapter health and telemetry
health_frame = client.frame_builder.build_health_frame(
    stream_id="health-report",
    adapter_id="my-ollama-adapter",
    status="healthy",
    p95_latency_ms=150.5,
    p50_latency_ms=95.2,
    error_rate=0.02,
    requests_per_second=10.5,
    memory_usage_mb=512.8,
    cpu_usage_percent=45.2,
    uptime_seconds=3600,
    version="1.0.0"
)

await client.send_frame(health_frame)
```

### Go SDK Usage
```go
// Report health status
health := atpsdk.HealthStatus{
    AdapterID:        "my-ollama-adapter",
    Status:           "healthy",
    P95LatencyMS:     floatPtr(150.5),
    ErrorRate:        floatPtr(0.02),
    RequestsPerSecond: floatPtr(10.5),
    MemoryUsageMB:    floatPtr(512.8),
    CPUUsagePercent:  floatPtr(45.2),
    UptimeSeconds:    intPtr(3600),
    Version:          stringPtr("1.0.0"),
}

err := client.ReportHealth(context.Background(), health)
```

## Model Context Protocol (MCP) Integration

ATP Router supports the Model Context Protocol (MCP) for standardized tool discovery and invocation. Connect via WebSocket to `/mcp` endpoint.

### MCP WebSocket Usage

```javascript
// Connect to MCP endpoint
const ws = new WebSocket('ws://localhost:8000/mcp');

// List available tools
ws.send(JSON.stringify({ type: 'listTools' }));

// Call a tool
ws.send(JSON.stringify({
  type: 'callTool',
  id: 'call-123',
  tool: {
    name: 'route.complete',
    arguments: {
      prompt: 'Explain quantum computing simply',
      quality_target: 'balanced',
      max_cost_usd: 0.05,
      latency_slo_ms: 2000
    }
  }
}));
```

### MCP Tool: route.complete

The primary tool exposed via MCP is `route.complete`, which provides adaptive completion with cost/quality optimization.

**Parameters:**
- `prompt` (string, required): The text prompt to complete
- `quality_target` (string, optional): "fast", "balanced", or "high" (default: "balanced")
- `max_cost_usd` (number, optional): Maximum cost budget in USD (default: 0.05)
- `latency_slo_ms` (integer, optional): Latency service level objective in milliseconds (default: 2000)

**Response:**
```json
{
  "type": "toolOutput",
  "toolCallId": "call-123",
  "content": [
    {
      "type": "text",
      "text": "Completion processed via gpt-4: Explain quantum computing simply..."
    }
  ],
  "dp_metrics_emitted": true
}
```

### Dynamic Tool Generation (GAP-126)

The MCP endpoint dynamically generates tool descriptors from the adapter registry:

#### Tool Discovery
```javascript
// List all available tools (dynamically generated from adapter registry)
ws.send(JSON.stringify({ type: 'listTools' }));

// Response includes:
// - route.complete: Adaptive routing using all healthy adapters
// - adapter.{adapter_id}: Direct access to specific adapters (one per healthy adapter)
```

#### Generated Tool Types

1. **route.complete** (Always Available)
   - Uses ATP's intelligent routing logic
   - Supports adapter_type filtering
   - Balances cost, quality, and latency

2. **adapter.{id}** (Adapter-Specific)
   - Direct access to individual adapters
   - Includes adapter-specific parameters (models, token limits)
   - Only generated for healthy adapters

#### Adapter-Specific Tool Example
```javascript
// Call a specific adapter directly
ws.send(JSON.stringify({
  type: 'callTool',
  id: 'call-123',
  tool: {
    name: 'adapter.ollama-adapter',
    arguments: {
      prompt: 'Explain quantum computing',
      model: 'llama2:7b',
      max_tokens: 1024
    }
  }
}));
```

#### Metrics
- `tools_exposed_total`: Gauge tracking total number of exposed MCP tools
- Updated automatically when tools are generated

### Streaming Partial toolOutput Events (GAP-127)

The MCP endpoint supports streaming partial toolOutput events for real-time tool result delivery. This enables progressive rendering of long-form content and better user experience for interactive applications.

#### Streaming Architecture

**Sequence & Cumulative Tokens:**
- Each streaming message includes a `sequence` number (1-based, incremental)
- `cumulative_tokens` tracks total tokens emitted so far
- Messages maintain strict ordering guarantees

**Message Types:**
1. **Partial Messages** (`is_partial: true`)
   - Contain incremental content chunks
   - Include sequence and cumulative token counts
   - Enable progressive UI updates

2. **Final Message** (`final: true`)
   - Contains complete response metadata
   - Includes performance metrics (latency, cost, model used)
   - Signals completion of streaming sequence

#### Streaming Example

```javascript
// Call tool with streaming enabled
ws.send(JSON.stringify({
  type: 'callTool',
  id: 'streaming-call-123',
  tool: {
    name: 'route.complete',
    arguments: {
      prompt: 'Write a detailed explanation of machine learning',
      quality_target: 'high'
    }
  }
}));

// Receive streaming responses
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'toolOutput') {
    if (msg.is_partial) {
      // Handle partial content
      console.log(`Partial ${msg.sequence}:`, msg.content[0].text);
      console.log(`Tokens so far: ${msg.cumulative_tokens}`);
    } else if (msg.final) {
      // Handle final message with metadata
      console.log('Final response:', msg.content[0].text);
      console.log('Performance:', msg.metadata);
    }
  }
};
```

#### Streaming Message Format

**Partial Message:**
```json
{
  "type": "toolOutput",
  "toolCallId": "streaming-call-123",
  "content": [{"type": "text", "text": "Machine learning is..."}],
  "sequence": 1,
  "cumulative_tokens": 15,
  "is_partial": true,
  "dp_metrics_emitted": true
}
```

**Final Message:**
```json
{
  "type": "toolOutput",
  "toolCallId": "streaming-call-123",
  "content": [{"type": "text", "text": "...complete explanation."}],
  "sequence": 5,
  "cumulative_tokens": 247,
  "final": true,
  "dp_metrics_emitted": true,
  "metadata": {
    "model_used": "gpt-4",
    "latency_ms": 1250,
    "cost_estimate": 0.023,
    "quality_target": "high",
    "adapter_id": "openai-adapter"
  }
}
```

#### Streaming for Adapter-Specific Tools

Adapter-specific tools (`adapter.{id}`) also support streaming with additional metadata:

```json
{
  "type": "toolOutput",
  "toolCallId": "adapter-call-456",
  "content": [{"type": "text", "text": "Adapter response chunk..."}],
  "sequence": 2,
  "cumulative_tokens": 45,
  "final": true,
  "dp_metrics_emitted": true,
  "metadata": {
    "adapter_id": "ollama-adapter",
    "model_used": "llama2:13b",
    "latency_ms": 890,
    "direct_call": true
  }
}
```

#### Streaming Metrics
- `mcp_partial_frames_total`: Counter tracking total streaming frames emitted
- Incremented for each partial message sent
- Useful for monitoring streaming usage patterns

### Champion/Challenger Experiment Metadata (GAP-129)

The ATP Router supports champion/challenger experimentation for A/B testing different models. When enabled, experiment metadata is automatically included in streaming responses to track which models are being tested.

#### Experiment Architecture

**Champion Selection:**
- Primary model is selected based on cost/quality optimization
- Challenger is selected from available models with quality gain at reasonable cost premium
- Challenger selection criteria: ≥2% quality improvement, ≤50% cost increase

**Metadata Exposure:**
- Experiment information is included in the `roles` array of plan responses
- Challenger model is marked with `role: "challenger"`
- Primary model retains `role: "primary"`

#### Experiment Example

```javascript
// Enable challenger experiments
process.env.ENABLE_CHALLENGER = "1";

// Make request - experiment metadata automatically included
const response = await fetch('/v1/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt: "Explain machine learning",
    quality: "balanced"
  })
});

// Parse streaming response
for await (const chunk of response.body) {
  const msg = JSON.parse(chunk);
  
  if (msg.type === "plan") {
    console.log("Experiment roles:", msg.roles);
    // Output: [
    //   {"role": "primary", "model": "gpt-4"},
    //   {"role": "challenger", "model": "claude-3"},
    //   {"role": "fallback", "model": "gpt-3.5-turbo"}
    // ]
  }
}
```

#### Experiment Response Format

**Plan Message with Experiment Metadata:**
```json
{
  "type": "plan",
  "candidates": [
    {
      "model": "gpt-4",
      "cost_per_1k": 0.03,
      "quality_pred": 0.80,
      "latency_p95": 1500
    },
    {
      "model": "claude-3",
      "cost_per_1k": 0.015,
      "quality_pred": 0.85,
      "latency_p95": 1200
    }
  ],
  "cluster_hint": "us-east-1",
  "prompt_hash": "abc123",
  "reason": "cheapest acceptable then escalation (bandit)",
  "roles": [
    {"role": "primary", "model": "gpt-4"},
    {"role": "challenger", "model": "claude-3"},
    {"role": "fallback", "model": "gpt-3.5-turbo"}
  ]
}
```

#### Experiment Metrics
- `experiment_frames_total`: Counter tracking total experiment frames emitted
- Incremented when challenger information is included in responses
- Useful for monitoring experiment participation rates

#### Configuration
- Enable with environment variable: `ENABLE_CHALLENGER=1`
- Automatic challenger selection based on quality/cost heuristics
- No configuration required - works out of the box

## Next steps
- Implement ATP /ws streaming codec + sessions/windows/consensus.
- Wire the router to call adapters over gRPC and the memory-gateway via HTTP/gRPC.
- Add OPA, SPIFFE mTLS, vector/graph/artifact tiers, and CI/CD.
 - Add tracing tests & richer span attributes (queue depth, window size deltas)
 - Redis integration test path + failover simulation
 - Harden admin key persistence (encryption at rest)
