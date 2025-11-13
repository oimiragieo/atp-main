# 30 — Enterprise TODO Roadmap (Execution Blueprint)

Legend:  ☐ = not started, △ = in progress, ✔ = done (POC) / will update as implemented.
Effort: S (<3d), M (3–10d), L (10–25d), XL (>25d) assuming 2–3 engineers.

## Phase 0 (Baseline POCs) — COMPLETE (Reference Only)
✔ Core POC features (routing, policy, observability, federation, DP, etc.) — captured in `TODO.md`.

---
## Phase 1: Service Extraction & Core Productionization (Weeks 1–6)
Goal: Move from scripts to durable services with contracts & basic security.

### 1.1 Service Carving
- ☐ Extract `router_service` into production package (uvicorn/gunicorn, config layering) (M)
- ☐ Introduce `policy-pdp` microservice with in-memory rule engine + hot reload (M)
- ☐ Memory Fabric service (FastAPI + Redis persistence adapter abstraction) (M)
- ☐ Accounting ingestion service (stream → Postgres or ClickHouse) (M)
- ☐ Audit ledger service (append-only API + hash chaining + anchor schedule) (M)

### 1.2 APIs & Contracts
- ☐ Define OpenAPI v1 for `/v1/ask`, `/v1/policy/check`, `/v1/memory/*` (S)
- ☐ Versioning & deprecation policy doc (S)
- ☐ JSON Schemas for frames/tool descriptors (S)

### 1.3 Persistence & Config
- ☐ Postgres schema: conversations, turns, integrations, policies, budgets (M)
- ☐ Redis deployment for hot session windows (S)
- ☐ Config system (env → typed settings → override file) (S)

### 1.4 Security & Auth
- ☐ OIDC integration (Auth0/Keycloak placeholder) (M)
- ☐ mTLS service mesh bootstrap (SPIFFE IDs) (M)
- ☐ Vault abstraction (CRUD secrets; rotate placeholder) (S)
- ☐ Basic rate limiting (token bucket per tenant) (S)

### 1.5 Observability Foundation
- ☐ Unified logging (structured JSON: trace_id, tenant, route) (S)
- ☐ OTEL instrumentation for new services (S)
- ☐ Base SLO definitions doc (latency, availability) (S)

### 1.6 Delivery & Ops
- ☐ Dockerfiles hardened (non-root, distroless where possible) (S)
- ☐ Initial Helm charts for carved services (M)
- ☐ Terraform baseline: VPC, Postgres, Redis, Secrets, Ingress (M)
- ☐ CI pipeline: lint, test, SBOM, image sign (S)

Exit Criteria Phase 1:
Latency p95 < 1200ms /v1/ask (single region), >99% uptime test env, all services health endpoints, basic auth & rate limiting enforced.

---
## Phase 2: Governance, Privacy & Cost Foundations (Weeks 6–12)
Goal: Production-grade governance + initial cost visibility & privacy enforcement.

### 2.1 Policy & Permissions
- ☐ ABAC attributes store (tenant, role, data_classification) (S)
- ☐ Tool permission scopes enforced in PDP (M)
- ☐ Policy dry-run & diff endpoint (S)

### 2.2 Privacy
- ☐ Redaction engine integrated at ingress (stream mode) (S)
- ☐ Differential Privacy ledger service (epsilon budgets per metric) (M)
- ☐ Data residency filtering (region-based adapter allowlist) (S)

### 2.3 Cost & Billing
- ☐ Token + $ attribution ingestion (router → accounting topic) (S)
- ☐ Baseline vs actual savings calculator (per turn) (S)
- ☐ Daily rollups job (savings_snapshot) (S)
- ☐ Billing export (CSV + API) (S)

### 2.4 Audit & Compliance
- ☐ Hash chain anchoring (periodic Merkle root publish) (M)
- ☐ DSR export endpoint (M)
- ☐ Retention enforcement job (TTL by classification) (S)

### 2.5 Marketplace Groundwork
- ☐ Adapter metadata schema + registration endpoint (S)
- ☐ Conformance test harness container (M)

### 2.6 Observability & SLOs
- ☐ Error budget burn calculator integrated (S)
- ☐ Cost & savings Grafana dashboards (S)
- ☐ Policy denial & redaction metrics (S)

Exit Criteria Phase 2:
100% policy enforcement coverage; DP budgets applied to at least one metric set; savings dashboard live; audit chain verifiable.

---
## Phase 3: Optimization & Experimentation (Weeks 12–20)
Goal: Advanced routing, experimentation lifecycle & quality signals.

### 3.1 Routing Evolution
- ☐ Multi-objective scoring (cost, latency, quality) (M)
- ☐ Contextual bandits with feature store (L)
- ☐ Regret tracking & reporting (S)
- ☐ Speculative inference early-cut logic (M)

### 3.2 Experiments
- ☐ Experiment controller service (state machine: shadow → challenger → promoted) (M)
- ☐ Statistical confidence module (fixed horizon + sequential) (M)
- ☐ Auto-promotion + rollback guardrails (S)

### 3.3 Quality Proxy Signals
- ☐ Lexical diversity & stagnation detector (S)
- ☐ Retrieval coverage scoring (M)
- ☐ Lightweight hallucination heuristic (dictionary / contradictions) (M)

### 3.4 Optimizer Loop
- ☐ Feature store schema (cost, latency, quality per model/route) (S)
- ☐ Training job (batch update priors) (M)
- ☐ Deployment of updated priors via config push (S)

### 3.5 Marketplace Alpha
- ☐ Publish certified adapters list endpoint (S)
- ☐ Usage metering tags per adapter (S)
- ☐ Revenue sharing calculation (baseline placeholder) (M)

Exit Criteria Phase 3:
Automated experiment promotions; multi-objective routing reduces cost ≥15% vs baseline; regret <10%; marketplace alpha listing.

---
## Phase 4: Scale, Federation & Resilience (Weeks 20–30)
Goal: Multi-region deployment, robust resilience & backpressure.

### 4.1 Federation
- ☐ Federation coordinator service (signed deltas) (L)
- ☐ Drift damping algorithm (S)
- ☐ Region policy propagation (S)

### 4.2 Resilience
- ☐ Backpressure controller (AIMD + queue depth) (M)
- ☐ Circuit breaker dashboard & auto-disable failing adapters (S)
- ☐ Chaos test suite nightly pipeline (M)
- ☐ Failover simulation harness (RTO/RPO measurement) (M)

### 4.3 Performance
- ☐ QUIC transport path gated by feature flag (M)
- ☐ Edge prefilter (prompt compression / small distilled model) prototype (M)
- ☐ Token streaming optimization (zero-copy frames) (M)

### 4.4 Observability Scale
- ☐ Adaptive tail sampling based on error budget burn (M)
- ☐ High-cardinality guard rail enforcement in metrics exporter (S)

Exit Criteria Phase 4:
Active/active multi-region, failover <60s, sustained throughput target met, adaptive sampling active.

---
## Phase 5: Ecosystem, Privacy Depth & Enterprise Packs (Weeks 30–42)
Goal: Monetizable ecosystem & deep compliance.

### 5.1 Marketplace GA
- ☐ Adapter submission workflow (upload & automated conformance) (M)
- ☐ Billing integration for usage-based rev share (M)
- ☐ Search & filter UI in portal (S)

### 5.2 Privacy & Compliance Expansion
- ☐ Evidence pack generator (SOC2/GDPR mapping) (M)
- ☐ DP budget auto-reallocation suggestions (M)
- ☐ On-demand redaction QA sampler (S)

### 5.3 Advanced Governance
- ☐ Policy simulation sandbox (what-if impact metrics) (M)
- ☐ Tool permission change approval workflow (S)
- ☐ Policy drift detector (changes vs runtime usage) (M)

### 5.4 Enterprise Portal Enhancements
- ☐ Savings benchmark comparisons (industry anonymized) (M)
- ☐ Cost forecast & variance alerts (M)
- ☐ Per-tenant budget enforcement UI (S)

Exit Criteria Phase 5:
Marketplace generating adapter traffic; compliance packs downloadable; advanced governance tools live.

---
## Phase 6: Advanced Optimization & Edge (Weeks 42–54)
Goal: Differentiated performance & predictive intelligence.

### 6.1 Predictive & Proactive
- ☐ Demand forecasting (ARIMA / simple ML) adjusts pre-warm & concurrency (M)
- ☐ Predictive latency model feeding pre-emptive escalation (M)
- ☐ Dynamic weight tuning via reinforcement signals (L)

### 6.2 Edge & Hybrid
- ☐ Edge node packaging (WASM container) (L)
- ☐ Partial execution fallback orchestration (S)

### 6.3 Security & Supply Chain
- ☐ Sigstore signing integration full (S)
- ☐ SBOM attestation pipeline (S)
- ☐ Runtime integrity monitoring (eBPF / Falco baseline) (M)

Exit Criteria Phase 6:
Predictive routing reduces p95 tail >10%; edge prototype live; signed releases and runtime integrity alerts functioning.

---
## Cross-Cutting Workstreams
### A. Documentation & DevRel
- ☐ API reference auto-gen (S)
- ☐ Quickstart guides (agent, integration, marketplace) (S)
- ☐ Architecture blueprints kept in sync (CI drift check) (M)

### B. Testing Strategy
- ☐ Contract tests (router ↔ adapters) (S)
- ☐ Performance regression suite (M)
- ☐ Security tests (fuzz + SSRF/injection simulations) (M)
- ☐ Chaos & failover scheduled jobs (M)

### C. Analytics & Metrics
- ☐ Central metrics catalog (S)
- ☐ KPI dashboard (savings, regret, denial, latency) (S)
- ☐ Anomaly detection (EWMA + seasonal) (M)

### D. Reliability
- ☐ Runbooks (incident types) (S)
- ☐ Postmortem template & automation (S)
- ☐ Error budget policy doc (S)

### E. Security & Compliance Ops
- ☐ Threat model (STRIDE table) (S)
- ☐ Pen-test remediation tracker (S)
- ☐ Quarterly key rotation runbook (S)

---
## Metrics / KPIs per Phase
| Phase | KPI Focus | Target |
|-------|-----------|--------|
| 1 | Latency p95, uptime | p95 <1200ms, >99% |
| 2 | Policy coverage, savings | 100% enforcement, >10% savings |
| 3 | Regret, promotion speed | Regret <10%, promotion <7d |
| 4 | Failover RTO, throughput | RTO <60s, X req/s target |
| 5 | Marketplace adoption | ≥5 certified adapters, revenue share running |
| 6 | Tail latency reduction | >10% p95 improvement |

---
## Risk Register (Top Ongoing)
| Risk | Phase Impact | Mitigation |
|------|--------------|-----------|
| Latency creep | 1–4 | Perf budget reviews, regression tests |
| Policy misconfig | 2–5 | Dry-run + diff + approvals |
| Cost drift | 2–6 | Savings dashboard + anomaly alerts |
| Data leak | 2–5 | Redaction QA + egress allowlist |
| Model quality drop | 3–6 | Drift alarms + fallback weights |

---
## Backlog / Future (Not Yet Scheduled)
- Adaptive DP epsilon allocation marketplace
- Hardware acceleration (GPU batching router-side)
- Federated learning of routing priors (privacy preserving)
- Sub-request multi-turn reasoning orchestrator
- Request-level carbon intensity tracking & routing

---
## How to Use This File
1. During planning, mark tasks △ or ✔.
2. Link Jira/Epics referencing the exact line.
3. Update exit criteria status at phase closeout.
4. Keep Phase N+1 at least two weeks groomed ahead.

---
End of Enterprise TODO.
