# FAQ & Glossary

## FAQ
**Q: What does ATP actually do?**  
It acts as an AI control plane: every model/tool request flows through routing, governance, and observability layers that optimize cost & quality while enforcing policy and privacy.

**Q: How is this different from a prompt management tool?**  
Prompt tools manage content; ATP manages execution decisions (which model, where, under which constraints) plus compliance & cost.

**Q: Does ATP store my data?**  
Short-lived context is in the memory fabric (KV/vector); retention & encryption policies govern persistence. PII is redacted before longer-term storage.

**Q: How are privacy guarantees enforced?**  
Inline PII redaction, differential privacy budgets for analytics metrics, and policy gating prevent disallowed egress.

**Q: Can I plug in any model provider?**  
Yes—via adapter interfaces. Certified adapters pass conformance (schema, error modes, telemetry) and can surface in a marketplace.

**Q: What if a model becomes slow or expensive?**  
Bandit + multi-objective routing shifts traffic toward cheaper or faster alternatives while preserving quality thresholds.

**Q: How do I know if I’m saving money?**  
Cost accounting tracks per-route baseline vs actual (savings %) and reports aggregated token & dollar deltas.

**Q: Is federation required?**  
No, single-region works; federation enables global latency reduction, failover, and data locality compliance.

**Q: What happens when DP budget is exhausted?**  
Further protected metric emissions are denied or noised out-of-band; alerts fire for operator action.

**Q: How do experiments avoid harming users?**  
Challenger models start in shadow or small % traffic; promotion only after statistical confidence & guardrail checks.

## Glossary (Supplemental)
- Adapter Certification: Process verifying adapter meets contract (latency, error, telemetry) before broad use.
- Audit Hash Chain: Each log entry includes a hash of previous, forming tamper evidence.
- Champion/Challenger: Experimental framework for safely replacing a baseline model.
- Control Plane: Layer managing policy, routing, and governance decisions for data plane requests.
- Data Plane: Actual execution path invoking models and tools.
- Differential Privacy (DP): Guarantees limiting information leakage about individuals in aggregate metrics.
- Drift Damping: Technique smoothing fluctuating metric updates in federated state.
- Egress Policy: Rules controlling which external endpoints data can be sent to.
- Error Budget: Allowable unreliability before halting risky changes.
- LinUCB: Contextual bandit algorithm balancing exploration/exploitation.
- Marketplace: Catalog of certified adapters/models/tools with metadata & pricing.
- Multi-Objective Routing: Selection optimizing across latency, cost, and quality simultaneously.
- Regret: Performance gap between chosen and optimal decision.
- SLO Burn Rate: Speed at which error budget is consumed.
- Speculative Inference: Launching parallel candidates and early-cutting losers to reduce tail latency.
- Tool Permissioning: Fine-grained control over which adapters an agent or tenant may call.

