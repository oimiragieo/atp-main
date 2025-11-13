# Policy Escalation (POC)

This POC demonstrates a simple escalation policy based on low confidence and
model disagreement signals.

- Engine: `router_service/policy_engine.py`
- Tests: `tests/test_policy_engine_poc.py`
- Metrics:
  - `escalations_total_low_conf`
  - `escalations_total_disagreement`
- Tracing: span `policy.evaluate` with attributes:
  - `policy.escalate` (bool)
  - `policy.reason` (low_conf | disagreement)

Example
```
from router_service.policy_engine import Policy, Context
pol = Policy(low_conf_threshold=0.6, escalate_on_disagreement=True)
dec = pol.evaluate(Context(confidence=0.45, disagreement=False))
if dec.escalate:
    # route to challenger/verifier
    pass
```

Future
- Add richer DSL, reason-weighted thresholds, and per-tenant overrides.
- Integrate with routing to select challenger/verifier models.
