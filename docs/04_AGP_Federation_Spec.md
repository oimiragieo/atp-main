# Agent Gateway Protocol (AGP) — Federation Spec v0.1

> Inter‑router federation for ATP: routing, reachability, capacity, and policy exchange across multiple ATP routers and administrative domains.

**Status:** Draft (for discussion)

**Scope:** Control‑plane protocol between ATP routers. Defines message types, route objects, attributes, timers, state machines, security model, and data‑plane encapsulation for forwarding ATP frames across router domains.

**Non‑Goals:** Model inference APIs, single‑router ATP internals (see ATP v0.1/0.2), training/serving details.

---

## 1. Goals & Terminology

* **Federate ATP deployments** into a resilient mesh (multi‑region, multi‑cloud, multi‑tenant).
* **Advertise reachability** of agent namespaces (e.g., `reviewer.*`, `summarizer.local`) with **attributes**: QoS tiers, capacity windows, health metrics, cost, estimation predictability.
* **Enable policy‑driven path selection** (SLA, security groups, geofencing, cost ceilings) with loop prevention and route dampening.
* **Support budget‑aware forwarding** (token/\$ decrements) across multiple router hops.

**Key terms**

* **Router**: ATP router instance participating in AGP.
* **AD (Agent Domain)**: Administrative domain (like an AS in BGP). Integer `adn` (32‑bit).
* **Agent Prefix**: Namespace pattern for a set of agents (e.g., `reviewer.*`, `retriever.us.*`).
* **AGP Session**: Peering relationship between two routers.
* **RLH (Router Label Header)**: Data‑plane shim header used to encapsulate ATP frames for inter‑router forwarding (MPLS‑like).

---

## 2. Operating Modes

* **Intra‑Domain AGP (iAGP)**: within the same AD, typically full‑mesh or route‑reflector topology.
* **Inter‑Domain AGP (eAGP)**: across AD boundaries; stricter security/policy, default `NO_EXPORT` for sensitive prefixes.

Routers **MUST** support both.

---

## 3. Addressing & Identity

* **Router ID**: stable 128‑bit UUID.
* **ADN**: 32‑bit unsigned (allocated by operator or registry).
* **Peer Address**: mTLS endpoint (hostname\:port), may be private.

Routers authenticate with **mTLS** and **OIDC** tokens containing `router_id`, `adn`, and allowed communities.

---

## 4. Message Types (Control Plane)

All control messages are JSON over a persistent TLS/WS or HTTP/2 stream.

### 4.1 OPEN

```
{
  "type":"OPEN",
  "router_id":"uuid",
  "adn": 64512,
  "capabilities": {
    "agp_version": "1.0",
    "max_prefix": 131072,
    "rlh": true,
    "compression": ["deflate"],
    "auth": ["mtls","oidc"],
    "qos": ["gold","silver","bronze"],
    "tenancy": ["vrf"]
  }
}
```

### 4.2 KEEPALIVE

```
{"type":"KEEPALIVE","ts":1734550000}
```

### 4.3 UPDATE (Advertise/Withdraw)

```
{
  "type":"UPDATE",
  "announce": [{
    "prefix": "reviewer.*",
    "path": [64512, 65001],
    "next_hop": "router:uuid",
    "attrs": {
      "local_pref": 200,
      "med": 50,
      "communities": ["no-export?false","region:us-east","security:sg=sandboxed-fs"],
      "qos_supported": ["gold","silver"],
      "capacity": {"max_parallel": 128, "tokens_per_s": 2_000_000, "usd_per_s": 10.0},
      "health": {"p50_ms": 800, "p95_ms": 1400, "err_rate": 0.015},
      "cost": {"usd_per_1k_tokens": 0.004},
      "predictability": {"estimate_mape_7d": 0.12, "under_rate_7d": 0.07},
      "security_groups": ["sandboxed-fs","no-pii"],
      "regions": ["us-east-1"],
      "valid_until": 1734553600
    }
  }],
  "withdraw": ["summarizer.eu.*"]
}
```

### 4.4 ROUTE\_REFRESH

```
{"type":"ROUTE_REFRESH","scope":"all|prefix","prefix":"reviewer.*"}
```

### 4.5 ERROR

```
{"type":"ERROR","code":"EPOLICY","reason":"export denied by community: no-export"}
```

---

## 5. Route Object & Attributes

**Agent Prefix** (string) + **Attributes**:

* **Path (ADN list)**: path‑vector for loop prevention.
* **NEXT\_HOP**: egress router\_id for this route.
* **LOCAL\_PREF**: intra‑AD preference (higher wins).
* **MED**: inter‑AD hint (lower wins).
* **QoS Supported**: tiers supported by downstream agents.
* **Capacity**: `max_parallel`, `tokens_per_s`, `usd_per_s` (headroom for external traffic).
* **Health**: `p50_ms`, `p95_ms`, `err_rate`.
* **Cost**: nominal cost per unit (e.g., per 1k tokens) to help cost‑aware selection.
* **Predictability**: `estimate_mape_7d`, `under_rate_7d` carried from FIB runtime.
* **Security Groups**: required environment/security labels for routing.
* **Communities**: tags controlling export (`no-export`, `region:*`, `tenant:*`, `sensitive`, `private`).
* **Regions**: physical/geo hints for locality.
* **Valid‑Until**: soft TTL for attribute freshness.

Routers **SHOULD** age or damp routes that flap.

---

## 6. Path Selection Algorithm (Deterministic with ECMP)

Given candidate routes to a prefix, choose by:

1. **Policy Filter**: security\_groups, region, tenant VRF, cost ceilings.
2. **LOCAL\_PREF** (desc) within AD.
3. **Path Length** (asc) across ADs.
4. **QoS Fit**: must satisfy requested QoS.
5. **Health Score**: minimize (weighted p95\_ms, err\_rate).
6. **Cost Score**: minimize usd\_per\_1k.
7. **Predictability Bonus**: prefer lower `estimate_mape_7d` and `under_rate_7d`.
8. **ECMP** across equal top candidates (hash on `session_id` for stickiness).

Weights are configurable; default weights provided in Appendix A.

---

## 7. Timers & State Machine

* **Keepalive**: 10s (negotiable); 3x miss → session down.
* **Route Hold**: 90s.
* **Graceful Restart**: 30s; peers retain routes during restart if marked `graceful=true` in OPEN.
* **Dampening**: penalty on each flap; suppress if threshold exceeded; decay half‑life 15m.

**Peering FSM** (BGP‑inspired, simplified): `IDLE → CONNECT → OPEN_SENT → OPEN_CONFIRMED → ESTABLISHED`. On ERROR or timer expiry → `IDLE`.

---

## 8. Security & Policy

* **mTLS** required; cert maps to `router_id` and `adn`.
* **OIDC token** (short‑lived) includes communities, tenant VRFs allowed.
* **Policy DSL** to control import/export:

```yaml
policies:
  export:
    - match: {prefix: "reviewer.*", communities_any: ["region:us-*"]}
      set: {community_add: ["no-export:false"]}
    - match: {prefix: "summarizer.local"}
      deny: true
  import:
    - match: {communities_any: ["sensitive"]}
      action: {strip: ["sensitive"], local_pref: 50}
```

* **Route Leaks**: `no-export` MUST be honored. Inter‑AD re‑advertisement requires community not to include `no-export`.
* **Tenancy/VRF**: routes carry `vrf_id`; selection only within same VRF unless explicit gateway policies.

---

## 9. Data‑Plane Encapsulation (RLH)

Inter‑router forwarding of ATP frames uses **Router Label Header (RLH)** stacked on top of the ATP frame.

```
+-------------------+
|  RLH v1           |
|  dst_router_id    | 128b
|  egress_agent_id  | 64b  (hash of agent handle)
|  qos              | 8b   (gold/silver/bronze)
|  ttl              | 8b
|  budget_tokens    | 64b  (remaining tokens)
|  budget_usd_micros| 64b  (remaining $)
|  flags            | 16b  (RESUME, FRAG, ECN)
|  hmac             | 128b
+-------------------+
|  ATP Frame        |
+-------------------+
```

Rules:

* **Push** RLH at ingress; **pop** at egress to the final router advertising the agent prefix.
* Per‑hop **budget decrement**: routers **MUST** decrement `budget_*` by their estimated forwarding overhead, and fail the packet if budget exhausted.
* **TTL** prevents loops. If TTL=0 → drop and generate ERROR to sender.
* **ECN** flag used to signal congestion; upstream routers reduce sending rate (AIMD).

Transport can be QUIC tunnels or WS/TCP; RLH is embedded in the outer message envelope.

---

## 10. Capacity & Congestion Propagation

* **Capacity Advertising**: downstream routers publish capacity headroom (`tokens_per_s`, `usd_per_s`). Upstream computes safe sending rates per prefix.
* **ECN Feedback**: routers set RLH.ECN on queuing pressure; upstream halves send rate for that prefix, with additive increase on recovery.
* **Backpressure Interop**: AGP integrates with ATP `control.status` from agents. A router may convert cluster‑internal BUSY/PAUSE to reduced capacity in AGP UPDATEs.

---

## 11. Failure Handling & Resilience

* **Graceful Restart**: peers mark `graceful=true`; retain routes during restart window; withdraw on timeout.
* **Fast Withdraw**: on critical failure, send UPDATE with `withdraw: [prefixes]` immediately.
* **Blackholing Protection**: if RLH TTL expires repeatedly or budget goes negative for a path, suppress that route (dampening) and raise alert.

---

## 12. Observability & Accounting

* **Per‑prefix metrics**: throughput, p50/p95 latency, err\_rate, ECN rate, drops.
* **Billing records**: per‑hop usage (tokens/\$ decremented) signed by each router; reconciled end‑to‑end.
  * **Schema**: `BillingRecord(tenant, adapter, prefix, in_tokens, out_tokens, usd_micros, timestamp, sequence)`
  * **Signatures**: HMAC-SHA256 with key rotation support using existing GAP-040 infrastructure
  * **Sequence**: Per-tenant monotonic sequence numbers for ordering and gap detection
  * **Metrics**: `billing_records_emitted_total` counter for monitoring
* **Tracing**: propagate `trace.parent_span` across routers; attach `router_id` to spans.

---

## 13. Reference Config Examples

### 13.1 Peering Config

```yaml
peers:
  - name: east-core
    router_id: 1a1b-…
    adn: 64512
    endpoint: wss://east-core.atp.local:7443
    keepalive_s: 10
    hold_s: 90
    graceful_restart_s: 30
    import_policies: ["default-import"]
    export_policies: ["default-export"]
```

### 13.2 Policy: Region & Security

```yaml
policies:
  default-export:
    - match: {communities_any: ["security:sg=sandboxed-fs"], regions_any: ["us-*"]}
      set: {local_pref: 200}
    - match: {communities_any: ["sensitive","private"]}
      deny: true

  default-import:
    - match: {qos_supported_all: ["gold"]}
      set: {local_pref: 250}
    - match: {err_rate_gt: 0.05}
      set: {local_pref: 50}
```

---

## 14. Conformance Levels

* **AGP‑L1 (Core):** OPEN/KEEPALIVE/UPDATE/WITHDRAW, path‑vector, loop prevention, timers.
* **AGP‑L2 (Capacity):** capacity/health/cost attributes, ECN, dampening, graceful restart.
* **AGP‑L3 (Secure & Multi‑tenant):** mTLS+OIDC, VRF, communities, policy DSL, RLH budget propagation, signed billing.

Routers **SHOULD** implement L1/L2; L3 for enterprise.

---

## 15. Interop with ATP

* **Control plane** (AGP) is orthogonal to **data plane** (ATP). AGP selects next‑hops for agent prefixes; ATP continues to manage session/stream semantics, windows, consensus.
* **Encapsulation**: RLH carries budgets and QoS across router hops; ATP frames remain unchanged.
* **Security**: tool\_permissions/security\_groups in ATP `meta` are enforced via AGP policy filters.

---

## 16. Open Questions (v0.2+)

1. Signed **route attestations** from agent owners to prevent spoofed reachability.
2. **Aggregated metrics privacy**: k‑anonymity or DP for cross‑AD health sharing.
3. **Label stack depth** for multi‑hop policies (RLH chaining vs. single‑label).
4. Handling **per‑tenant budgets** across federated paths (hierarchical quotas).

---

## Appendix A — Default Weights

```yaml
weights:
  local_pref: 0.30
  path_len:   0.20
  health:     0.20   # composite of p95_ms + err_rate
  cost:       0.15
  predict:    0.10
  qos_fit:    0.05
```

## Appendix B — JSON Schemas (snippets)

```json
{"$id":"agp.open.v1","type":"object","required":["type","router_id","adn","capabilities"],"properties":{"type":{"const":"OPEN"},"router_id":{"type":"string"},"adn":{"type":"integer"},"capabilities":{"type":"object"}}}
```

```json
{"$id":"agp.update.v1","type":"object","required":["type"],"properties":{"type":{"const":"UPDATE"},"announce":{"type":"array","items":{"type":"object","required":["prefix","attrs"],"properties":{"prefix":{"type":"string"},"path":{"type":"array","items":{"type":"integer"}},"next_hop":{"type":"string"},"attrs":{"type":"object"}}}},"withdraw":{"type":"array","items":{"type":"string"}}}}
```

---

**End of AGP v0.1 draft.**

---

# v0.2 Addendum — Convergence, Config Safety, Budget Overhead, and Route Attestations

This addendum addresses fast‑changing metrics, configuration/debuggability, per‑hop budget overhead modeling, and cryptographic route authenticity. It introduces new attributes, timers, roles, and operational tooling.

## 1) Convergence & Freshness of Attributes

### 1.1 Metric Freshness Fields (UPDATE.attrs)

Add the following fields to `UPDATE.announce[i].attrs`:

```jsonc
{
  "metrics_timestamp": 1734550123,    // unix seconds when health/capacity was sampled
  "metrics_half_life_s": 30,          // EWMA decay horizon used by the sender
  "metrics_sample_size": 2048,        // number of recent requests behind p95/err_rate
  "stability_class": "fast|slow"     // hint: latency/err=fast, cost/capacity=slow
}
```

**Selection rule:** Health components are multiplied by a **freshness factor** `F = exp(-Δt / τ)`, where `Δt = now - metrics_timestamp` and `τ = metrics_half_life_s`. Routes with stale metrics are penalized; if `Δt > hold_s`, treat metrics as **stale** and prefer alternatives.

**Implementation:** The freshness factor is applied in the route selection algorithm's `_calculate_route_score()` method, where health scores are divided by the freshness factor (higher freshness = lower score = better route).

### 1.2 EWMA + Hysteresis at the Source

Routers SHOULD publish health with **EWMA smoothing** and **hysteresis** (only advertise when the smoothed p95 moves by >X% for Y seconds). Recommended defaults: `X=10%`, `Y=5s` for fast metrics.

**Implementation:** Hysteresis configuration is available via `HysteresisConfig` class with validation for change thresholds and stabilization periods.

### 1.3 Dual Timers

* **Liveness** (KEEPALIVE): 10s default (detects peer failure).
* **Health Refresh**: fast ticker 2–5s for fast metrics; 30–60s for slow metrics.
  Routers SHOULD dampen oscillations via **route flap dampening** on prefixes whose health toggles state >N times per minute (default N=6).

**Implementation:** Flap dampening is implemented in `RouteDampeningTracker` with configurable thresholds, penalty accumulation, and automatic suppression when thresholds are exceeded.

## 2) Configuration Complexity & Debuggability

### 2.1 Policy Linter & Dry‑Run

Introduce `agpctl lint <policy_file>` to statically validate AGP policy YAML files for syntax errors, missing required fields, and best practices. The linter checks:

- Policy structure (rules array, effect validation)
- Rule validation (match patterns, forbidden data scopes)
- Type safety and pattern matching

Use `agpctl whatif <policy_file> --tenant <name> --task-type <type> --data-scope <scope>` to simulate policy decisions with detailed trace output showing which rules matched and why.

### 2.2 Route Explainability API

Implemented `GET /agp/explain?prefix=…&tenant=…&task_type=…&data_scope=…` endpoint that evaluates AGP policy rules against the provided context and returns:

- **Decision**: Allow/deny based on policy evaluation
- **Rule Evaluation Trace**: Detailed breakdown of each rule evaluation with match reasons
- **Context**: The evaluation context used for policy matching
- **Reject Reasons**: Specific reasons why routes would be rejected (forbidden data scopes, pattern mismatches)

The endpoint integrates with the existing policy simulation engine and provides observability into AGP federation policy decisions.

### 2.3 Tracing Utilities

* **agp trace** (traceroute‑like): emits the current next‑hop chain with RLH TTL decrements.
  - **CLI**: `python tools/agptrace.py <route_table.yaml> <prefix> [--start-router <router>] [--max-hops <n>] [--ttl <n>]`
  - **API**: `GET /agp/trace?prefix=<prefix>&start_router=<router>&max_hops=<n>&ttl=<n>`
  - **Features**: Loop detection, TTL expiry simulation, path visualization with AS path and local preference
  - **Output**: Hop-by-hop analysis showing router transitions, TTL decrements, and forwarding decisions
* **Route Snapshots**: `agpctl snapshot` captures RIB/FIB for diffing and rollback.
  - **CLI**: `python tools/agpsnapshot.py <route_table.yaml> <command> [args]`
  - **Commands**: `take <name>`, `list`, `diff <snap1> <snap2>`, `restore <name>`
  - **Features**: Full route table serialization, dampening state preservation, diff computation
  - **API**: Integrated into AGPRouteTable with `take_snapshot()`, `restore_from_snapshot()`, `diff_snapshots()`

## 3) Intra‑Domain Scale — Route Reflector (RR)

### 3.1 RR Role

Define a formal **Route Reflector** role for iAGP. An RR maintains full peering with clients and reflects UPDATEs, reducing full‑mesh requirements.

**New OPEN capability:** `"rr": { "cluster_id": "uuid", "client": true|false }`

**New attributes (UPDATE.attrs):**

```jsonc
{
  "originator_id": "router:uuid",   // first advertiser inside the cluster
  "cluster_list": ["cluster:uuid"]  // loop prevention across RRs
}
```

RRs MUST drop UPDATEs that would create loops (originator\_id equals self or cluster\_id seen in cluster\_list).

**Implementation Notes (GAP-109A):**
- **originator_id validation**: Routes are rejected if `originator_id == router_id`
- **cluster_list validation**: Routes are rejected if the router's cluster_id appears in `cluster_list`
- **cluster_id derivation**: For router_id format "router:cluster", cluster_id is the part after the first ":"
- **Metrics**: `agp_loops_prevented_total` counter tracks prevented loop routes
- **Testing**: Comprehensive test coverage for both loop prevention conditions

## 4) Default Budget Overhead Model (RLH)

### 4.1 Baseline Decrement

Until calibrated, routers MUST support a simple, conservative model:

```
Δtokens = α * payload_tokens + β     (default α=0.01, β=10)
Δusd    = γ * payload_usd    + δ     (default γ=0.02, δ=0.00001)
```

Where `payload_tokens`/`payload_usd` are the ATP frame’s pre‑known estimates for this hop. Routers advertise the model in OPEN:

```jsonc
{"overhead_model": {"version":"1","alpha":0.01,"beta":10,"gamma":0.02,"delta":0.00001}}
```

### 4.2 Calibration & Telemetry

Routers SHALL record actual per‑hop overhead and publish calibration stats in periodic UPDATEs:

```jsonc
{"overhead_mape_7d": 0.09, "overhead_p95_factor": 1.2}
```

Path selection penalizes routers with high overhead MAPE. Operators MAY opt into a **dynamic** model bounded by `(α_min, α_max)` etc., adjusted via PID control with dampening.

## 5) Signed Route Attestations (ARPKI)

### 5.1 Objects & Flow

Introduce **Agent Route PKI (ARPKI)**, analogous to RPKI:

* **ROA‑A (Route Origin Authorization — Agent)**: issued by an **Agent Owner CA**, binds `{agent_prefix, owner_id, valid_from, valid_to}`.
* **RTR‑Cert (Router Certificate)**: binds `{router_id, adn, privileges}`.
* **AGP UPDATE** carries `"attestation": {"roa_a": "…", "sig": "…", "chain": ["owner_ca", "intermediate", …]}`.

Routers MUST verify that the announcer is authorized to originate the prefix; invalid or expired attestations → reject UPDATE and raise `ERROR: EATTEST`.

### 5.2 Revocation & Freshness

Support **CRL/OCSP‑like** endpoints for ROA‑A and RTR‑Cert. `attestation.valid_until` is included and compared against `now()` with leeway ≤ 60s.

## 6) Selection Algorithm Updates

* Add **freshness multiplier** for health (`F = exp(-Δt/τ)`), and prefer larger `metrics_sample_size` when health scores tie.
* Prefer routes whose **overhead\_mape\_7d** is lower when RLH budget is tight.
* Consider **stability\_class**: prefer `slow` routes for long‑lived streams unless health significantly favors a `fast` route.

## 7) Operational Defaults & Safety Nets

* **Hold‑Down on Health Degradation:** require degradation to persist for `persist_s` (default 8s) before withdrawing.
* **Grace Period after Recovery:** suppress re‑announcement for `grace_s` (default 5s) after recovery.
* **Safe Mode:** if policy fails to load, fall back to last‑known‑good snapshot and emit `ERROR: ECFG`.

### Implementation: Hold-Down & Grace Periods

**Configuration:**
- `persist_s`: Hold-down duration (default 8s) - routes must remain degraded for this period before withdrawal
- `grace_s`: Grace period duration (default 5s) - routes are suppressed after recovery for this period

**State Tracking:**
- Per-prefix hold-down state with `hold_down_until` timestamp
- Per-prefix grace period state with `grace_period_until` timestamp
- Automatic timer expiration and cleanup

**Integration:**
- Health-based route updates use `update_routes_health_based()` and `withdraw_routes_health_based()`
- Metrics: `hold_down_events_total` counter tracks delayed operations
- Works alongside existing flap dampening and hysteresis features

**Behavior:**
- Health degradation starts hold-down timer, preventing immediate withdrawal
- Health recovery starts grace period timer, preventing immediate re-advertisement
- Timers are mutually exclusive (recovery clears hold-down, degradation clears grace period)

### Implementation: Safe Mode Fallback

**Configuration:**
- `enabled`: Whether safe mode is enabled (default true)
- `snapshot_path`: Path to last-known-good snapshot file (default `/var/lib/atp/snapshots/last_known_good.json`)
- `max_retries`: Maximum policy load retry attempts (default 3)
- `retry_delay_seconds`: Delay between retries (default 5s)

**State Tracking:**
- `safe_mode_active`: Boolean flag indicating if safe mode is currently active
- Automatic snapshot saving on successful configuration loads
- Snapshot restoration on configuration failures

**Integration:**
- Safe mode fallback triggered when configuration parsing fails
- Metrics: `safe_mode_entries_total` counter tracks safe mode activations
- ERROR: ECFG emitted when entering safe mode
- Last-known-good snapshot automatically maintained

**Behavior:**
- Configuration load failures trigger safe mode entry
- Last-known-good snapshot loaded from configured path
- Route table restored to previous known-good state
- Safe mode remains active until new valid configuration loaded
- Automatic snapshot saving on successful configuration validation

## 8) Schema Diffs (v1.1 → v1.2)

* `UPDATE.attrs += metrics_timestamp, metrics_half_life_s, metrics_sample_size, stability_class, originator_id, cluster_list`
* `OPEN.capabilities += rr.cluster_id, rr.client, overhead_model`
* `UPDATE += attestation {roa_a, sig, chain}`

**Wire compatibility:** Unknown fields MUST be ignored by older peers; advertise `agp_version` in OPEN.

### Implementation: Version Negotiation & Unknown Field Handling

**OPEN Message Processing:**
- `AGPOpenMessage` class handles OPEN message parsing and validation
- Version negotiation via `negotiate_version()` method
- Compatible versions share same major version number
- Incompatible versions raise `ValidationError`

**Unknown Field Handling:**
- `from_dict()` methods ignore unknown fields for backward compatibility
- UPDATE messages with unknown fields are processed normally
- Unknown capabilities in OPEN messages are preserved but ignored
- Metrics: `incompatible_updates_total` tracks parsing failures due to unknown fields

**Version Compatibility:**
- Major version changes require explicit negotiation
- Minor/patch versions are backward compatible
- Default version is "1.0" when not specified
- Version negotiation chooses minimum compatible version

---

## 6. Persona Federation Extension (GAP-116C)

### Overview

Persona federation enables cross-router sharing of persona reputation statistics to improve global routing decisions and maintain consistency across the ATP network.

### Message Types

**PersonaStatsUpdate (NEW):**
```json
{
  "type": "persona_stats_update",
  "persona_id": "string",
  "reputation_score": 0.85,
  "reliability_score": 0.92,
  "sample_count": 50,
  "last_updated": 1640995200,
  "router_origin": "router-uuid",
  "constraints": {"region": "us-west"},
  "sequence_number": 1,
  "signature": "hmac-sha256-hex"
}
```

### Conflict Resolution

**Sequence-based Resolution:**
- Higher sequence numbers from same router supersede lower ones
- Stale sequences (lower than current) are rejected

**Reputation-based Merging:**
- When reputation difference > 0.3 from recent average, trigger weighted merge
- Sample count used as merge weights
- Merged statistics marked with `router_origin: "federated_merge"`

**Time-based Filtering:**
- Statistics older than 1 hour are ignored for conflict resolution
- Recent statistics (last hour) used for reputation averaging

### Security Model

**HMAC Signing:**
- Each router signs persona statistics with its private key
- Signature covers: persona_id, scores, sample_count, timestamp, router_origin, sequence_number
- Verification required before accepting federated statistics

**Router Authentication:**
- Router identity verified via mTLS certificates
- Router public keys distributed via secure channel
- Invalid signatures result in rejection

### Metrics

**federated_persona_updates_total:** Counter incremented on successful ingestion of federated persona statistics (accept or merge actions).

### Implementation Notes

- Persona federation operates independently of route federation
- Statistics are stored locally and consolidated on-demand
- Failed validations are logged but don't interrupt federation
- Merge operations preserve sample count weighting for accuracy

---

End of v0.2 addendum.
