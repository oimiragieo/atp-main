# Enterprise Architecture Blueprint

## 1. Overview
This document translates POC components into a production-grade, multi-region, multi-tenant architecture.

## 2. Service Topology
| Service | Responsibility | Scale Characteristic |
|---------|----------------|----------------------|
| ingress-gateway | AuthN/Z (OIDC+mTLS), rate/quotas, redaction | CPU-light / network IO |
| router-core | Routing algorithms, experiment orchestration | CPU-bound (bandits), low-latency |
| policy-pdp | ABAC, tool permissions, egress decisions | Latency sensitive (<5ms budget) |
| memory-fabric | KV + vector + CRDT session state | Memory & storage IO |
| adapter-runtime | Sandboxed model/tool adapters | Heterogeneous; GPU/CPU mix |
| accounting-svc | Token/call aggregation, pricing | Write-heavy bursts |
| audit-ledger | Hash chain, anchoring, retention/DSR workflows | Append-dominant |
| dp-ledger | Epsilon budget mgmt & alerts | Low throughput, high integrity |
| federation-coordinator | State delta sync, drift damping | Burst sync traffic |
| observability-pipeline | OTEL collector + enrichment | High throughput streaming |
| cost-optimizer | Multi-objective model selection training | Batch/cron + feature store |

## 3. Reference Request Path
1. Client -> Ingress (auth, QoS tagging, redaction)
2. Policy PDP (allow/deny + attribute enrichment)
3. Router Core (decision: model set; may spawn speculative parallel calls)
4. Adapter Runtime(s) (invoke models/tools)
5. Memory Fabric (read/write context, embeddings)
6. Aggregation (merge speculative / consensus, apply guardrails)
7. Accounting & Audit (emit cost + audit record)
8. Response streaming to client.

## 4. Data Persistence
| Data | Store | Rationale |
|------|-------|-----------|
| Policy definitions & attributes | Postgres (RLS) | ACID, versioning |
| Session window / CRDT docs | Redis + Durable snapshot (RDB/AOF) | Low latency + eventual snapshot |
| Vector embeddings | Specialized vector DB (pluggable) | Similarity search perf |
| Audit log hash chain | Append-only Postgres partition or object store log | Integrity, cheap retention |
| DP budgets | Postgres strict constraints | Consistency |
| Token/cost events | Kafka -> Druid/ClickHouse | Rollup analytics |
| Model quality metrics | Kafka -> Time-series DB (Prometheus/Mimir) | High ingest |

## 5. Security Layers
- Identity: OIDC access tokens (short TTL) exchanged for mTLS SPIFFE IDs within mesh.
- AuthZ: ABAC policies referencing tenant, data_classification, region, tool_scope.
- Secrets: Vault (dynamic DB creds, adapter API keys) + auto-rotation.
- Data Protection: Envelope encryption (per-tenant KEK) + row-level encryption for sensitive columns.
- Supply Chain: Image signing (cosign), SBOM attestation, dependency diff scanning in CI.

## 6. Multi-Tenancy Strategy
- Namespace isolation: TenantID prefix in logical key-space.
- RLS on Postgres tables; per-tenant encryption context.
- Soft limits (quotas) + hard rate limits; adaptive throttling when global saturation.

## 7. Federation & Regions
- Active/active clusters each run full stack except cost-optimizer (centralized) & audit anchoring.
- Gossip or signed delta publish (federation-coordinator) distributing model quality stats.
- Drift damping (exponential smoothing) prevents oscillations from noisy updates.
- Region policy filter ensures data locality compliance.

## 8. Reliability Patterns
| Concern | Mitigation |
|---------|-----------|
| Adapter hotspot latency | Adaptive concurrency + circuit breaker fallback |
| Backpressure overload | AIMD window + queue depth metrics gating ingress |
| Partial region outage | DNS or global load balancer + health-based failover |
| Thundering model retrain | Feature store snapshot isolation + canary training |
| Observability cost explosion | Dynamic tail sampling controller |

## 9. Observability & SLOs
- Unified trace span taxonomy: ingress, policy, routing_decision, adapter_call, memory_io.
- Derived metrics: regret_delta, savings_pct, dp_budget_remaining, policy_denials_rate.
- SLO classes: latency(route, percentile), availability(route), quality(regret), cost(savings).
- Burn-rate alerts (multi-window 5m/1h, 1h/24h) with auto-throttle hook.

## 10. Privacy & Compliance
- Inline PII redaction at ingress before persistence.
- DP budget ledger rejects emission once epsilon exhausted (alert + metric).
- DSR workflow: index audit entries by pseudonymous subject key.
- Retention engine tags data segments with TTL & classification; nightly GC job.

## 11. Experimentation Lifecycle
1. Register challenger adapter/model with metadata & guardrails.
2. Shadow traffic or percentage split via router-core.
3. Collect quality/cost metrics; compute statistical confidence.
4. Auto-promote when threshold met, record audit decision.
5. Rollback path preserved (config version pin).

## 12. Deployment Pipeline
- CI: lint, unit, contract test, fuzz (protocol), security scan, SBOM, image build & sign.
- CD: progressive (10% -> 50% -> 100%) with SLO guard; rollback on breach.
- Config changes versioned (GitOps). Policy changes require dual approval + dry-run diff.

## 13. Cost Optimization Loop
- Real-time token cost ingestion -> per-route savings computation.
- Feature store: (latency, quality_score, cost_per_1k_tokens) per model per route.
- Multi-objective scoring (weighted or Pareto filter) feeding bandit priors.
- Gain-share reporting for enterprise upsell.

## 14. Roadmap Alignment Matrix
| Capability | Phase | Prereqs |
|------------|-------|---------|
| ABAC + PDP service | 2 | Postgres, identity |
| Federation MVP | 3 | Stable routing core |
| DP ledger service | 2 | Policy engine, Postgres |
| Marketplace | 3 | Adapter conformance harness |
| Multi-objective optimizer | 3 | Quality metrics pipeline |
| On-prem operator | 4 | Service extraction complete |

## 15. Open Questions (To Validate)
- Do we standardize on gRPC for all internal calls (except ingress HTTP)?
- Which vector DBs to certify first (Pinecone, Weaviate, pgvector)?
- Where to anchor audit Merkle roots (public blockchain vs transparency log)?
- SLA goals per tier (latency, availability, recovery)?

## 16. Appendix: Sequence Notation Example
Client -> Ingress: POST /v1/completions
Ingress -> PDP: policy.check(request_attrs)
PDP -> Ingress: allow + enriched_attrs
Ingress -> Router: route.decide(enriched_attrs + context)
Router -> AdapterA: invoke()
Router -> AdapterB: invoke() (speculative)
AdapterA -> Router: partial(stream)
AdapterB -> Router: partial(stream)
Router: merge/early cut decision
Router -> MemoryFabric: store(context delta)
Router -> Accounting: emit(usage, pricing_ref)
Router -> Audit: append(hash_link)
Router -> Client: stream completion

