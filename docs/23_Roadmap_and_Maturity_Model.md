# Roadmap & Capability Maturity Model

## Capability Ladders
Each ladder shows progressive maturity states; enterprise readiness requires reaching Tier 3+ in core ladders.

### 1. Routing & Optimization
| Tier | Description | Key Features |
|------|-------------|--------------|
| 0 | Static passthrough | Single model, no routing |
| 1 | Basic switch | Manual route rules, latency metrics |
| 2 | Bandit/Champion | Thompson/LinUCB, challenger promotion |
| 3 | Multi-objective | Cost+latency+quality scoring, regret tracking |
| 4 | Predictive | Demand forecasting, proactive scaling |

### 2. Governance & Policy
| Tier | Description | Features |
|------|-------------|----------|
| 0 | Ad hoc | Inline checks |
| 1 | Central policy | PDP service, ABAC |
| 2 | Tool perms & egress | Fine-grained adapter scopes |
| 3 | Compliance automation | Retention engine, DP ledger, audit hash chain |
| 4 | Autonomous | Policy simulation + predictive impact analysis |

### 3. Privacy & Compliance
| Tier | Description | Features |
|------|-------------|----------|
| 0 | None | Raw logs |
| 1 | Redaction | PII masking |
| 2 | DP budgets | Epsilon enforcement |
| 3 | DSR workflows | Subject index, export tooling |
| 4 | Evidence packs | Continuous compliance dashboards |

### 4. Observability & FinOps
| Tier | Description | Features |
|------|-------------|----------|
| 0 | Minimal logs | Ad hoc prints |
| 1 | Metrics & traces | OTEL, dashboards |
| 2 | Cost accounting | Token & $ per route |
| 3 | SLO automation | Burn rate alerts, auto-throttle |
| 4 | Optimization loop | Cost anomaly ML, savings attribution |

### 5. Resilience & Reliability
| Tier | Description | Features |
|------|-------------|----------|
| 0 | Best effort | Manual restarts |
| 1 | Health probes | Basic restart policies |
| 2 | Backpressure | AIMD windows, circuit breakers |
| 3 | Multi-region | Federation, failover tests |
| 4 | Chaos-hardened | Automated chaos & DR drills |

### 6. Ecosystem & Extensibility
| Tier | Description | Features |
|------|-------------|----------|
| 0 | Closed | No adapters |
| 1 | Pluggable | Adapter interface |
| 2 | Certification | Conformance tests, metadata |
| 3 | Marketplace | Revenue share, discovery |
| 4 | Network effects | Cross-tenant optimization insights |

## 12-Month Thematic Roadmap
| Quarter | Themes | Outcomes |
|---------|--------|----------|
| Q1 | Service extraction, auth, persistence | Router-core & PDP services GA |
| Q2 | Governance hardening, privacy, SLOs | DP ledger, audit hash chain, burn alerts |
| Q3 | Federation, marketplace beta, optimizer | Multi-region routing, adapter catalog |
| Q4 | Predictive scaling, evidence packs | Forecasting, compliance dashboards |

## Dependency Graph (Simplified)
- Multi-objective optimizer depends on: cost accounting + quality metrics + bandits.
- Federation depends on: stable routing core + policy versioning.
- Marketplace depends on: adapter certification + billing integration.
- Evidence packs depend on: audit ledger + DP ledger + retention engine.

## KPIs by Phase
| Phase | KPI Focus |
|-------|-----------|
| Foundation | Time to first route, baseline latency |
| Hardening | Policy coverage %, DP budget adherence |
| Scale | Savings %, federation convergence time |
| Optimization | Regret reduction %, anomaly MTTR |
| Ecosystem | Adapter attach rate, marketplace GMV |

## Risk Mitigation Actions
| Risk | Mitigation |
|------|-----------|
| Latency regression | Performance regression tests, p95 gates |
| Cost drift | Savings dashboard + alert thresholds |
| Policy misconfig | Dry-run sim mode + require approval |
| Data leak | Redaction QA set + periodic audits |
| Model quality drop | Drift alarms & rollback switch |

## Exit Criteria per Phase
| Phase | Exit Criteria |
|-------|--------------|
| Foundation | p95 < 1200ms, >99% uptime test env |
| Hardening | 100% policy enforcement, DP ledger live |
| Scale | Multi-region failover <60s RTO |
| Optimization | Regret <5% vs oracle baseline |
| Ecosystem | 20 certified adapters, 3 marketplace partners |

