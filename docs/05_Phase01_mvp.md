# ATP/AGP Router — Phase 1 Rust Scaffold (MVP)

A production‑minded Rust scaffold for the **Agent Transport Protocol (ATP)** data plane and the **Agent Gateway Protocol (AGP)** control plane. Tuned for high throughput, low latency, and safe extensibility via out‑of‑process adapters.

> Scope: ATP L1 (core sessions/frames/windows, fan‑out, reassembly, budget), plus stubs for AGP peering and policy. Includes OPA sidecar, VW bandit daemon hooks, OpenTelemetry, Distroless container, and K8s manifests.

---

## 0) Repository Layout

```
atp-router/
├─ Cargo.toml
├─ rust-toolchain.toml
├─ crates/
│  ├─ atp-schema/           # serde models for frames, windows, telemetry (v1.1)
│  ├─ atp-adapter-proto/    # gRPC definitions + tonic build for adapters
│  └─ atp-router/           # router core (binary)
├─ adapters/
│  └─ python/
│     └─ ollama_adapter/
│        ├─ server.py       # example adapter (estimate/stream)
│        ├─ requirements.txt
│        └─ Dockerfile
├─ opa/
│  ├─ policy.rego           # policy DSL enforcement
│  └─ data.example.json
├─ deploy/
│  ├─ k8s/
│  │  ├─ router-deploy.yaml
│  │  ├─ opa-configmap.yaml
│  │  ├─ spiffe-spire-notes.md
│  │  └─ service-monitor.yaml
│  ├─ docker/
│  │  └─ Dockerfile.router
│  └─ grafana/
│     └─ dashboards.json
├─ Makefile
└─ README.md
```

---

## 1) `crates/atp-schema` — Core Types (Serde)

**Cargo.toml**

```toml
[package]
name = "atp-schema"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_with = "3"
bytes = "1"
thiserror = "1"
```

**src/lib.rs**

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Window {
    pub max_parallel: u32,
    pub max_tokens: u64,
    pub max_usd_micros: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEst {
    pub in_tokens: u64,
    pub out_tokens: u64,
    pub usd_micros: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Payload {
    pub r#type: String,              // agent.result.partial|final|provisional|question|log|control.status|tool.request|tool.result
    pub content: serde_json::Value,  // freeform JSON
    pub confidence: Option<f32>,
    pub cost_est: Option<CostEst>,
    pub checksum: Option<String>,
    pub expiry_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    pub task_type: Option<String>,
    pub languages: Option<Vec<String>>,
    pub risk: Option<String>,
    pub data_scope: Option<Vec<String>>,
    pub trace: Option<serde_json::Value>,
    pub tool_permissions: Option<Vec<String>>,
    pub environment_id: Option<String>,
    pub security_groups: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Frame {
    pub v: u8,
    pub session_id: String,
    pub stream_id: String,
    pub msg_seq: u64,
    pub frag_seq: u32,
    pub flags: Vec<String>,          // SYN|ACK|FIN|RST|MORE|HB|CTRL
    pub qos: String,                 // gold|silver|bronze
    pub ttl: u8,
    pub window: Window,
    pub meta: Meta,
    pub payload: Payload,
    pub sig: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExplainRoute {
    pub prefix: String,
    pub candidates: Vec<serde_json::Value>,
}
```

---

## 2) `crates/atp-adapter-proto` — gRPC for Adapters (tonic/prost)

**Cargo.toml**

```toml
[package]
name = "atp-adapter-proto"
version = "0.1.0"
edition = "2021"

[dependencies]
tonic = { version = "0.11", features = ["transport"] }
prost = "0.13"
prost-types = "0.13"
serde = { version = "1", features = ["derive"] }

[build-dependencies]
prost-build = "0.13"
tonic-build = "0.11"
```

**build.rs**

```rust
fn main() { tonic_build::configure().compile(&["proto/adapter.proto"], &["proto"]).unwrap(); }
```

**proto/adapter.proto**

```proto
syntax = "proto3";
package atp.adapter.v1;

message EstimateRequest { string stream_id = 1; string task_type = 2; string prompt_json = 3; }
message EstimateResponse {
  uint64 in_tokens = 1; uint64 out_tokens = 2; uint64 usd_micros = 3;
  uint64 p95_tokens = 4; uint64 p95_usd_micros = 5; double variance_tokens = 6; double variance_usd = 7;
  double confidence = 8; string tool_cost_breakdown_json = 9; repeated string assumptions = 10;
}

message StreamRequest { string stream_id = 1; string prompt_json = 2; }
message StreamChunk {
  string type = 1; string content_json = 2; double confidence = 3;
  uint64 partial_in_tokens = 4; uint64 partial_out_tokens = 5; uint64 partial_usd_micros = 6;
  bool more = 7;
}

message HealthRequest {}
message HealthResponse { double p95_ms = 1; double error_rate = 2; }

service AdapterService {
  rpc Estimate(EstimateRequest) returns (EstimateResponse);
  rpc Stream(StreamRequest) returns (stream StreamChunk);
  rpc Health(HealthRequest) returns (HealthResponse);
}
```

---

## 3) `crates/atp-router` — Router Core (binary)

**Cargo.toml**

```toml
[package]
name = "atp-router"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = { version = "0.7", features = ["ws", "http2"] }
hyper = { version = "1", features = ["http2"] }
tokio = { version = "1", features = ["rt-multi-thread","macros","net","signal","sync","io-util","time"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter","registry"] }
opentelemetry = { version = "0.22" }
opentelemetry-otlp = { version = "0.16", features = ["tonic"] }
metrics = "0.22"
metrics-exporter-prometheus = "0.14"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
bytes = "1"
thiserror = "1"
parking_lot = "0.12"
dashmap = "6"
anyhow = "1"
tokio-stream = "0.1"
prost = "0.13"
tonic = { version = "0.11", features = ["transport"] }
prost-types = "0.13"
atp-schema = { path = "../atp-schema" }
atp-adapter-proto = { path = "../atp-adapter-proto" }
```

**src/main.rs** (skeleton)

```rust
use axum::{routing::get, Router};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main(flavor = "multi_thread", worker_threads =  num_cpus::get())]
async fn main() -> anyhow::Result<()> {
    // Tracing/OTel
    let env_filter = std::env::var("RUST_LOG").unwrap_or_else(|_| "info,atp_router=debug".into());
    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .with(tracing_subscriber::EnvFilter::new(env_filter))
        .init();

    let app = Router::new()
        .route("/healthz", get(|| async { "ok" }))
        .route("/metrics", get(metrics_handler))
        .route("/ws", get(ws_upgrade))
        .route("/agp/explain", get(explain_route));

    let addr = std::net::SocketAddr::from(([0,0,0,0], 7443));
    tracing::info!(%addr, "router listening");
    axum::serve(tokio::net::TcpListener::bind(addr).await?, app).await?;
    Ok(())
}

async fn metrics_handler() -> String { metrics_exporter_prometheus::PrometheusBuilder::new().build().render() }
async fn ws_upgrade() -> &'static str { "ws endpoint (stub)" }
async fn explain_route() -> String { "[]".into() }
```

**src/session.rs** (outline)

```rust
use std::sync::Arc;
use dashmap::DashMap;
use atp_schema::{Frame, Window};

#[derive(Clone)]
pub struct SessionState {
    pub window: Window,
    pub inflight: u32,
    pub tokens: u64,
    pub usd_micros: u64,
}

#[derive(Default, Clone)]
pub struct Sessions { inner: Arc<DashMap<String, SessionState>> }

impl Sessions {
    pub fn admit(&self, stream_id: &str, est_tokens: u64, est_usd: u64) -> bool { /* triplet window checks */ true }
    pub fn on_send(&self, stream_id: &str, est_tokens: u64, est_usd: u64) { /* update counters */ }
    pub fn on_ack(&self, stream_id: &str, est_tokens: u64, est_usd: u64) { /* reduce inflight */ }
}
```

**src/reassembler.rs** (outline)

```rust
use std::collections::BTreeMap;
use std::sync::Arc;
use dashmap::DashMap;
use atp_schema::Frame;

#[derive(Default, Clone)]
pub struct Reassembler { inner: Arc<DashMap<String, BTreeMap<u64, BTreeMap<u32, Frame>>>> }
```

**src/dispatcher.rs** (outline)

```rust
use atp_adapter_proto::atp::adapter::v1::{adapter_service_client::AdapterServiceClient, StreamRequest};
use tonic::transport::Channel;

pub struct AdapterClient { inner: AdapterServiceClient<Channel> }
```

---

## 4) OPA Policy (rego) — Security & Routing Constraints

**opa/policy.rego**

```rego
package atp.policy

default allow = false

# Enforce tool permissions and security groups on route selection
allow {
  input.meta.tool_permissions[_] == "fs.read"
  input.meta.security_groups[_] == "sandboxed-fs"
}

# AGP import/export: block sensitive communities
deny_export[msg] {
  some c
  input.update.attrs.communities[c] == "sensitive"
  msg := {"code":"EPOLICY","reason":"sensitive community"}
}
```

---

## 5) Python Adapter (Ollama) — Minimal Example

**adapters/python/ollama\_adapter/requirements.txt**

```
grpcio==1.64.0
grpcio-tools==1.64.0
protobuf==5.27.2
uvloop==0.20.0
orjson==3.10.7
```

**adapters/python/ollama\_adapter/server.py** (skeleton)

```python
import asyncio, json, grpc
from concurrent import futures
from atp.adapter.v1 import adapter_pb2, adapter_pb2_grpc

class Adapter(adapter_pb2_grpc.AdapterServiceServicer):
    async def Estimate(self, req, ctx):
        # toy estimator; replace with real token counting
        n = len(req.prompt_json) // 4
        return adapter_pb2.EstimateResponse(in_tokens=n, out_tokens=n//5, usd_micros=0, confidence=0.7)

    async def Stream(self, req, ctx):
        for i in range(3):
            chunk = adapter_pb2.StreamChunk(type="agent.result.partial", content_json=json.dumps({"chunk": i}), confidence=0.6, partial_in_tokens=500, partial_out_tokens=50, partial_usd_micros=0, more=True)
            yield chunk
        yield adapter_pb2.StreamChunk(type="agent.result.final", content_json=json.dumps({"ok": True}), confidence=0.8, more=False)

    async def Health(self, req, ctx):
        return adapter_pb2.HealthResponse(p95_ms=900, error_rate=0.01)

async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(Adapter(), server)
    server.add_insecure_port('[::]:7070')
    await server.start(); await server.wait_for_termination()

if __name__ == '__main__': asyncio.run(serve())
```

**adapters/python/ollama\_adapter/Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 7070
CMD ["python","server.py"]
```

---

## 6) Distroless Router Image

**deploy/docker/Dockerfile.router**

```dockerfile
# Build
FROM rust:1.79 as builder
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    cargo build -p atp-router --release

# Runtime: Distroless
FROM gcr.io/distroless/cc-debian12:nonroot
WORKDIR /app
COPY --from=builder /src/target/release/atp-router /app/atp-router
EXPOSE 7443
USER nonroot
ENTRYPOINT ["/app/atp-router"]
```

---

## 7) Kubernetes Manifests (Router + OPA Sidecar)

**deploy/k8s/router-deploy.yaml**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: atp-router }
spec:
  replicas: 2
  selector: { matchLabels: { app: atp-router } }
  template:
    metadata: { labels: { app: atp-router } }
    spec:
      containers:
      - name: router
        image: ghcr.io/yourorg/atp-router:latest
        ports: [{ containerPort: 7443 }]
        env:
        - { name: RUST_LOG, value: "info,atp_router=debug" }
        - { name: OTEL_EXPORTER_OTLP_ENDPOINT, value: "http://otel-collector:4317" }
      - name: opa
        image: openpolicyagent/opa:0.63.0-istio
        args: ["run","--server","--set=decision_logs.console=true","/policy/policy.rego"]
        volumeMounts: [{ name: opa-policy, mountPath: /policy }]
      volumes:
      - name: opa-policy
        configMap: { name: opa-policy }
---
apiVersion: v1
kind: Service
metadata: { name: atp-router }
spec:
  selector: { app: atp-router }
  ports: [{ name: https, port: 7443, targetPort: 7443 }]
```

**deploy/k8s/opa-configmap.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: opa-policy }
data:
  policy.rego: |
    package atp.policy
    default allow = false
    allow { input.meta.security_groups[_] == "sandboxed-fs" }
```

---

## 8) Observability Wiring

* Expose `/metrics` (Prometheus). Add a `ServiceMonitor` if using Prometheus Operator.
* Use `tracing` + OTLP exporter for traces; set env `OTEL_EXPORTER_OTLP_ENDPOINT`.

**deploy/k8s/service-monitor.yaml** (snippet)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata: { name: atp-router }
spec:
  selector: { matchLabels: { app: atp-router } }
  endpoints: [{ port: https, path: /metrics, interval: 15s }]
```

---

## 9) Makefile (DX)

```makefile
.PHONY: build run docker
build:
	cargo build -p atp-router -r
run:
	RUST_LOG=info cargo run -p atp-router
image:
	docker build -f deploy/docker/Dockerfile.router -t ghcr.io/yourorg/atp-router:latest .
```

---

## 10) Performance Notes

* Use Tokio **multi-thread** runtime; pin threads with `taskset` or `K8s CPUManager` **static** policy for determinism.
* Prefer **Bytes/BytesMut** for zero‑copy buffers; reuse slabs for frame parsing.
* Consider **HTTP/2** for persistent multiplexing; evaluate **QUIC (quinn)** once stable in your environment.
* Tune Linux: `net.core.somaxconn`, `tcp_tw_reuse`, `rmem_max`, `wmem_max`; set container **ulimits** (`nofile`).
* In K8s, prefer **Cilium** CNI with eBPF for fast datapath.

---

## 11) Next Steps

1. Flesh out `/ws` streaming with ATP frame codec + reassembly.
2. Implement budget window admission and acking.
3. Integrate OPA check in dispatcher before fan‑out.
4. Wire a real adapter via gRPC (Ollama demo).
5. Add provisional consensus skeleton.
6. Add `/agp/explain` mock that surfaces policy + scoring breakdown.

*This scaffold is intentionally minimal yet production‑minded. Extend incrementally with AGP peering, bandits, signed attestations (ARPKI), and backpressure once the fast path is stable.*
