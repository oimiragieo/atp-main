# Adaptive Router Autonomy & Model Lifecycle

Version: 1.0  
Status: Draft (POC implementation reflected)

## Overview
The adaptive router incrementally learns which Small Language Models (SLMs) to prioritize per task cluster using:
- Heuristic initial plan (cheapest acceptable + escalation)
- UCB (Upper Confidence Bound) scoring over success/cost ratio
- Shadow evaluation of experimental models
- Automated promotion / demotion based on cost performance thresholds
- Persistence of model status and usage statistics

## Core Flow
1. Request classified -> cluster_hint (heuristic classifier).
2. Candidate plan built (excluding shadow models from primary selection).
3. UCB reorders plan (if stats exist for cluster) to pick empirical primary.
4. Streaming response emitted (plan frame + chunks + final frame).
5. Observation recorded (schema_versioned) + stats persisted (SQLite).
6. Background (and one synchronous seed) shadow evaluations executed for any shadow models.
7. Promotion / demotion logic applied with hysteresis.

## Observation Schema (Version 1)
Required keys (primary final observation):
`ts, prompt_hash, cluster_hint, model_plan, primary_model, latency_s, tokens_in, tokens_out, cost_usd, phase`
Additional fields include: `ucb_primary, savings_pct, energy_kwh, co2e_grams, quality_score, schema_version`.
Shadow eval observations add: `shadow_model, shadow_of, shadow_quality, shadow_latency_s, shadow_cost_usd`.
Lifecycle events: `promotion`, `demotion` include comparative cost fields.

## Metrics Export
Prometheus-style endpoint `/metrics` includes:
- Aggregate: `atp_router_total_calls`, `..._avg_cost_usd`, `..._avg_latency_seconds`, `..._avg_savings_pct`, energy.
- Per model/cluster: `atp_router_model_calls{}`, `..._model_success{}`, `..._model_escalations{}`, `..._model_avg_cost_usd{}`.
- Regret: `atp_router_cost_regret_vs_premium`.
- UCB: `atp_router_ucb_score{}`, `..._ucb_exploit{}`, `..._ucb_explore{}` for default cluster.
- Lifecycle counters: `atp_router_promotions_total`, `atp_router_demotions_total`.
- Schema & thresholds: `atp_router_obs_schema_version`, threshold gauges (`atp_router_threshold_*`).

## Promotion / Demotion Logic
Environment-configurable thresholds:
- `PROMOTE_MIN_CALLS` (default 5)
- `PROMOTE_COST_IMPROVE` (default 0.9 -> shadow avg cost < primary * 0.9)
- `DEMOTE_MIN_CALLS` (default 6)
- `DEMOTE_COST_REGRESS` (default 1.25 -> active avg cost > cheapest active * 1.25)
- `PROMO_DEMO_HYSTERESIS_SEC` (default 5s) cool-down after last lifecycle action for a model.

Promotion triggers when shadow model meets min calls and cost improvement threshold vs current primary. Demotion uses cheapest active model baseline to detect sustained cost regression.

## Endpoints Summary
| Endpoint | Purpose |
|----------|---------|
| `/v1/ask` | Streaming query routing with adaptive selection |
| `/metrics` | Prometheus metrics including UCB & lifecycle |
| `/admin/observations` | Recent observation samples |
| `/admin/shadow_stats` | Current shadow models metadata |
| `/admin/model_status` | All models with status + counters |
| `/admin/cluster_stats` | In-memory simple per-model counters |
| `/healthz` | Liveness probe |

## Persistence
- SQLite file `router_stats.sqlite` for per-cluster model stats (calls, success, cost_sum, latency_sum).
- Daily JSONL observation files `slm_observations-YYYY-MM-DD.jsonl`.
- `model_registry.json` updated in-place (atomic replace) on promotion/demotion (excluding re-computed manifest_hash which is regenerated on load).

## UCB Scoring
Score = `(success_rate / avg_cost) + explore_factor * sqrt(log(total_calls)/calls)`.
Exploit term favors higher success / lower cost. Explore term decays with more calls. Unseen candidates may be prioritized early.

## Shadow Evaluation
Each request triggers:
- Background thread per shadow model producing a stochastic quality/latency/cost sample.
- A synchronous seeded shadow_eval observation for deterministic testability.

## Hysteresis
Prevents rapid oscillation: actions ignored if a model had a lifecycle change within the configured cool-down window.

## Known Limitations / Future Work
- Success currently stubbed (tool_success always True); integrate real quality / format validators.
- Cluster classification heuristic only (no embedding-based clustering yet).
- UCB scores only for default cluster in metrics.
- No Thompson sampling or contextual bandit features integrated yet.
- Observation persistence lacks rotation/compression policy.
- No security filtering / PII scrubbing applied to prompts in this POC.
- Promotion reason string still hard-coded (update to reflect parameterized thresholds).

## Roadmap Next Enhancements
1. Contextual feature vectors for UCB (latency SLO, prompt length buckets).
2. Thompson Sampling variant for comparison.
3. Per-cluster UCB metrics aggregation.
4. Quality / safety scoring hooks (format_ok + external evaluator integration).
5. Demotion reason taxonomy (cost, latency, success rate, safety regression).
6. JSON Schema formalization & OpenAPI docs for admin endpoints.
7. Persistent lifecycle history log (append-only). 

---
POC implemented features provide a foundation for autonomous cost-aware SLM routing with transparent observability and lifecycle governance.

---

## Model Registry Specification (GAP-343)

### Overview
The model registry provides a centralized catalog of all models available to the ATP router, including their capabilities, safety grades, performance characteristics, and lifecycle status.

### Registry Schema

#### Required Fields
- `model`: Unique identifier for the model (string)
- `safety_grade`: Safety classification A-D (A=highest safety, D=lowest)
- `status`: Lifecycle state - "active", "shadow", "fallback", "deprecated"

#### Optional Fields
- `params_b`: Model parameter count in billions (float)
- `context_len`: Maximum context length in tokens (integer)
- `license`: Software license (string)
- `capabilities`: Array of supported task types (array of strings)
- `provider`: External provider name (string)
- `est_latency_ms`: Estimated latency in milliseconds (integer)
- `est_cost_per_1k_tokens_usd`: Estimated cost per 1000 tokens in USD (float)
- `tags`: Additional classification tags (array of strings)

### Manifest Hash & Integrity

#### Hash Computation
Each registry entry includes a `manifest_hash` computed as:
```python
hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
```

#### Signature Verification
- Hash is computed excluding the `manifest_hash` field itself
- Verification ensures manifest integrity and tamper detection
- Hash is recomputed on each registry load

### Safety Grade Policy

#### Grade Hierarchy
- **A**: Highest safety - permits all use cases
- **B**: High safety - permits B, C, D requirements
- **C**: Medium safety - permits C, D requirements  
- **D**: Basic safety - permits D requirements only

#### Policy Enforcement
```python
def policy_permit(model_rec, required_safety):
    grades = {"A": 4, "B": 3, "C": 2, "D": 1}
    current = grades.get(model_rec.get("safety_grade", "D"), 0)
    required = grades.get(required_safety, 0)
    return current >= required
```

### Lifecycle States

#### State Definitions
- **active**: Primary models used for routing
- **shadow**: Evaluation models receiving traffic samples
- **fallback**: Backup models for high-availability
- **deprecated**: Models being phased out

#### State Transitions
- Manual or automated promotion/demotion based on performance
- Hysteresis prevents rapid oscillation
- Atomic registry updates with backup/rollback

### Metrics

#### Registry Metrics
- `atp_models_registered_total`: Gauge of total models in registry
- Updated on registry load/reload

#### Integration Points
- Router service loads registry at startup
- Specialist selection uses registry for capability matching
- Shadow evaluation respects lifecycle states
- Cost estimation uses registry pricing data

### File Format
Registry stored as JSON array in `router_service/model_registry.json`:
```json
[
  {
    "model": "example-model",
    "safety_grade": "A",
    "status": "active",
    "capabilities": ["summarize", "classify"],
    "params_b": 1.5,
    "context_len": 8192
  }
]
```

### Security Considerations
- Registry file should have restricted permissions
- Manifest hashes prevent unauthorized modifications
- External provider credentials stored separately
- Safety grades enforce usage policies

---

## Model Custody & Provenance Logging (GAP-348)

### Overview
Model custody logging provides tamper-evident audit trails for model lifecycle events, ensuring compliance and enabling forensic analysis of model operations.

### Custody Events

#### Event Types
- **build**: Model training/compilation events
- **scan**: Security/vulnerability scanning
- **sign**: Cryptographic signing operations
- **deploy**: Model deployment to production
- **promote**: Status changes (shadow → active, etc.)
- **registry_update**: Registry modification events

#### Event Structure
```json
{
  "event_type": "build",
  "model_id": "customer_support_v1",
  "timestamp": 1757204705,
  "details": {
    "build_config": {
      "framework": "pytorch",
      "version": "2.0"
    }
  }
}
```

### Audit Chain Integration

#### Hash Chaining
Each custody event is appended to an audit log with HMAC-SHA256 protection:
```python
# Event format in log
{
  "event": {...},
  "prev": "previous_hash_hex",
  "hmac": "hmac_signature_hex", 
  "hash": "current_hash_hex"
}
```

#### Tamper Detection
- **Chain Verification**: Validates hash links between events
- **HMAC Validation**: Ensures events haven't been modified
- **Timestamp Ordering**: Detects out-of-sequence events

### API Functions

#### Logging Events
```python
from router_service.model_manifest import log_model_build, log_model_scan

# Log build event
log_model_build("my-model", {"framework": "pytorch"})

# Log scan event  
log_model_scan("my-model", {"vulnerabilities": 0})
```

#### Verification & Query
```python
from router_service.model_manifest import verify_model_custody_log, get_custody_events

# Verify log integrity
is_valid = verify_model_custody_log()

# Get all custody events
events = get_custody_events()

# Get events for specific model
model_events = get_custody_events("my-model")
```

### Metrics

#### Custody Metrics
- `model_custody_events_total`: Counter of logged custody events
- Updated on each successful event logging

### Integration Points

#### Registry Operations
- Automatic logging when registry is saved
- Captures model additions, updates, deletions

#### PEFT Pipeline
- Build events logged during fine-tuning
- Scan events for security validation
- Sign events for provenance tracking

#### Router Service
- Deploy events on model activation
- Promotion events on status changes
- Registry updates trigger custody logging

### Security Model

#### Cryptographic Protection
- HMAC-SHA256 for event integrity
- SHA256 hash chaining for sequence protection
- Timestamp validation for temporal ordering

#### Access Control
- Custody log requires appropriate permissions
- Secret key management for HMAC operations
- Log file protection against unauthorized access

### Compliance & Audit

#### Regulatory Compliance
- SOX, PCI-DSS, GDPR compliance logging
- Tamper-evident audit trails
- Cryptographic proof of event ordering

#### Forensic Analysis
- Complete model lifecycle traceability
- Who, what, when, where tracking
- Incident investigation support

### File Locations

#### Custody Log
- **Path**: `router_service/model_custody.log`
- **Format**: JSON Lines with hash chaining
- **Permissions**: Restricted to service account

#### Configuration
- **Secret Key**: Managed via secure key store
- **Retention**: Configurable log rotation
- **Backup**: Integrated with system backup procedures

### Best Practices

#### Operational Security
- Regular log integrity verification
- Secure key rotation procedures
- Log monitoring and alerting

#### Performance Considerations
- Asynchronous logging to avoid blocking
- Log rotation to manage file sizes
- Compression for long-term storage

#### Monitoring & Alerting
- Alert on custody log verification failures
- Monitor custody event rates
- Track unusual event patterns

---
Generated: 2025-09-06
