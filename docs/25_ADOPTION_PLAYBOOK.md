# Adoption Playbook

## 1. Phased Rollout Strategy
| Phase | Scope | Success Metric |
|-------|-------|----------------|
| Pilot (Weeks 1-2) | Shadow routing for 1-2 critical flows | Latency parity (<5% delta) |
| Limited Prod (Weeks 3-6) | 10-20% traffic, cost accounting live | >10% savings (projected) |
| Broad Adoption (Weeks 7-12) | 70%+ traffic, policy enforcement | 100% policy coverage |
| Optimization (Quarter 2) | Multi-objective routing, SLO auto-throttle | >15% realized savings |
| Scale (Quarter 3) | Multi-region federation | <60s failover RTO |

## 2. Pre-Pilot Checklist
- Map target endpoints & baseline metrics (latency, error, cost per 1K tokens).
- Classify data domains & PII fields.
- Define initial policies (ABAC attributes, egress rules, tool scopes).
- Identify champion vs challenger model pairs.
- Ensure observability pipeline (OTEL collector) reachable.

## 3. Instrumentation Requirements
| Component | Needed Signals |
|-----------|----------------|
| Ingress | request_id, tenant_id, auth method, redaction stats |
| Router | chosen_route, candidate_set, decision_latency, regret_estimate |
| Adapter | model_name, tokens_in/out, latency_ms, errors |
| Policy | policy_id, decision=allow/deny, reason, attributes_used |
| DP Ledger | metric_id, epsilon_spent, remaining_budget |

## 4. Shadow Routing Play
1. Mirror production requests to ATP (no user-visible response).
2. Record routing decisions & predicted savings vs production baseline.
3. Validate: no PII leakage post-redaction; latency overhead budget.
4. Approve progression when <5% p95 overhead and projected savings >8%.

## 5. Traffic Shift Algorithm
- Start 5% → measure (latency, errors, savings) for N=10k requests.
- If within guardrails (latency +<7%, error diff <0.5%, savings >=10%) increase to 20%.
- Continue geometric increase (20→40→70→100%) when prior window stable.
- Auto-pause escalation if any guardrail breached.

## 6. Policy Hardening Steps
| Step | Action | Outcome |
|------|--------|---------|
| 1 | Dry-run policies (log only) | Validate coverage |
| 2 | Enforce critical deny rules | Block high-risk egress |
| 3 | Incrementally enforce remaining | Achieve 100% coverage |
| 4 | Add DP budgets | Protect aggregate metrics |
| 5 | Retention automation | Ensure data lifecycle compliance |

## 7. Experiment Management
- Register challenger with metadata: expected_latency_delta, expected_quality_gain.
- Use sequential probability ratio test or fixed-horizon A/B depending on traffic volume.
- Auto-promote when confidence >95% & guardrails pass.
- Maintain rollback pin to previous champion.

## 8. Success Dashboards (Initial Panels)
- Savings over time (% & absolute $).
- Routing regret trend.
- Policy decision breakdown (allow/deny/error).
- DP budget utilization per metric.
- Adapter latency & error heatmap.
- Federation convergence lag (if multi-region).

## 9. Operational Runbooks (Abbrev.)
| Incident | Detection | Immediate Action | Follow-up |
|----------|-----------|------------------|-----------|
| Latency spike | SLO burn alert | Engage autoscale & throttle | Profile + optimize hot path |
| Policy denial surge | Policy denials > threshold | Check recent policy change | Add test, adjust rule |
| Savings regression | Savings < floor 24h | Inspect routing weights drift | Recompute priors |
| DP budget exhaustion | Remaining <10% | Evaluate metric priority | Reallocate or increase epsilon |
| Adapter error burst | Error rate >5% | Circuit break adapter | Engage provider / fallback |

## 10. Exit Criteria for Full Production
- 30 days stable operations (no Sev1/Sev2 attributed to ATP).
- Savings >= target (e.g., 15%).
- 100% policy enforcement & zero unredacted PII findings in audits.
- All core KPIs within SLO (latency, availability, error rate).

## 11. Change Management
- All policy & routing config changes: PR + dual approver.
- Weekly experiment review: active challengers, pending promotions, anomalies.
- Monthly governance audit: sample 1% of logs for redaction & policy integrity.

## 12. Training & Enablement
| Audience | Artifact |
|----------|----------|
| Developers | Adapter dev guide, routing cookbook |
| SRE | Runbooks, SLO dashboards, chaos drill schedule |
| Security | Policy authoring, audit query guide |
| Product | Experiment results digest |
| Finance | Savings & cost attribution dashboard |

## 13. Common Pitfalls
| Pitfall | Mitigation |
|---------|-----------|
| Over-aggressive experiments | Guardrails & staged rollout |
| Policy sprawl | Namespacing + lint rules |
| Observability cost blowup | Tail sampling controller |
| Unclear savings attribution | Baseline snapshot & immutable reference |
| DP over-budget | Budget planning & monitoring panel |

## 14. Continuous Improvement Loop
Collect metrics → Analyze (regret, savings, denials) → Hypothesize (policy tweak, new challenger) → Experiment → Promote/Rollback → Document → Feed KPIs.

