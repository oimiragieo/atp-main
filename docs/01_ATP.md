# Agent Transport Protocol (ATP) — Draft v0.1

**A network‑style protocol and reference architecture for concurrent, reliable, and cost‑aware communication among LLM sub‑agents.**

> Vision: Do for agent ecosystems what TCP/IP did for the early Internet—introduce sessions, sequencing, flow control, congestion avoidance, QoS, and multipath consensus so thousands of specialized agents can cooperate efficiently and safely.

---

## 0) Executive Summary

ATP standardizes how agents communicate **concurrently** and **reliably**, with the router acting like a **Layer‑3/4 switch** for agent messages. It introduces:

* **Frames** (ATP segments) with sequence numbers, flags, and checksums.
* **Streams** (like TCP connections) per task with **sliding windows** for tokens/\$ and concurrency.
* **Routing tables** (RIB/FIB) that map **task types → sub‑agents → models** with cost/latency/win‑rate metrics.
* **Fan‑out + Reassembly** with **consensus** strategies (union, quorum, champion/challenger).
* **Budgets as bandwidth**: tokens and dollars are flow‑controlled like congestion windows.
* **QoS classes** for preemption and fairness.
* **Security** (authn/authz, signatures, data‑scope labels) and **observability** (traces, costs, confidence).

---

## 1) Scope & Non‑Goals

**In‑scope:** Agent‑to‑router and router‑to‑agent communication; concurrent task orchestration; cost/token control; routing/consensus; capability discovery; interop between frameworks (LangChain, AutoGen, Qwen‑Agent, CrewAI, custom).

**Out‑of‑scope:** Low‑level transport reliability (we baseline on WebSocket/HTTP/2 or QUIC); training/fine‑tuning; model serving internals.

---

## 2) Design Principles

1. **Protocol‑first:** A typed, versioned wire format with extension points (TLVs).
2. **Deterministic core, pluggable policy:** Data plane is simple; control plane (routing/budgets) is configurable.
3. **Parallel by default:** Fan‑out to diverse experts; router reassembles and arbitrates.
4. **Progressive disclosure:** Cheap/local agents first; escalate only on uncertainty or risk.
5. **Cost is bandwidth:** Tokens/\$ are first‑class windowed resources.
6. **Safety & auditability:** Explicit data‑scope tags, provenance, and full traces.

---

## 3) Layered Model (Agent Network Stack)

* **L0 Environment** — Sandboxed tool execution (I/O, FS, net policies), redaction hooks.
* **L1 Identity & Capabilities** — Agent auth (mTLS/OIDC), capability advertisement, versioning.
* **L2 Sessions & Streams** — SYN/ACK/FIN, sequencing, fragmentation, retransmit, heartbeats.
* **L3 Routing & QoS** — Policy matching, fan‑out, budgets, sliding windows, congestion control.
* **L4 Consensus & Validation** — Evidence checking, agreement scoring, escalation triggers.
* **L5 Applications** — Code review, repo summarization, planning, retrieval QA, data analysis, etc.

---

## 4) Wire Protocol

### 4.1 Transport & Encoding

* **Baseline transport:** WebSocket over TLS 1.3. (HTTP/2 server push or QUIC is allowed.)
* **Encoding:** JSON frames v1 (UTF‑8). **Optional:** CBOR for compact binary.
* **Compression:** Per‑message deflate (negotiated at handshake).

### 4.2 Frame Structure (v1)

```jsonc
{
  "v": 1,
  "session_id": "sess_7c1f…",
  "stream_id": "task_4b9e…",
  "msg_seq": 12,
  "frag_seq": 0,
  "flags": ["SYN","MORE"], // SYN|ACK|FIN|RST|MORE|HB|CTRL
  "qos": "gold|silver|bronze",
  "ttl": 8,
  "window": { "max_parallel": 4, "max_tokens": 80000, "max_usd_micros": 500000 },
  "meta": {
    "task_type": "code_review",
    "languages": ["py","ts"],
    "risk": "medium",
    "data_scope": ["no_secrets","us_personal_data:forbidden"],
    "trace": { "parent_span": "spn_abcd…" }
  },
  "payload": {
    "type": "agent.result.partial|final|question|log|control",
    "content": "…",
    "confidence": 0.72,
    "cost_est": { "in_tokens": 3200, "out_tokens": 900, "usd": 0.012 },
    "checksum": "sha256:…"
  },
  "sig": "HMAC-SHA256(base64…)",
  "checksum": "sha256:…" // whole-frame checksum (excluding sig & checksum fields)
}
```

### 4.3 Control Payloads

* **CAPABILITIES** — agent → router advertisement (skills, max ctx, tools, safety domains).
* **WINDOW\_UPDATE** — router → agent changes window (parallel/tokens/\$).
* **BUDGET\_UPDATE** — client/router adjusts remaining budget.
* **ROUTE\_UPDATE** — router publishes FIB deltas to downstream switches.
* **ERROR** — structured error with code, reason, retry/backoff hints.

### 4.4 Flags & Semantics

* **SYN**: open stream; include CAPABILITIES or task meta.
* **ACK**: acknowledge `msg_seq` (router emits implicit ACK frames or piggybacks on WINDOW\_UPDATE).
* **MORE**: more fragments for current `msg_seq` to come.
* **FIN**: close stream cleanly; flush buffers, emit final metrics.
* **RST**: abort stream; include ERROR.
* **HB**: heartbeat/keepalive.

### 4.5 Ordering & Fragmentation

* `msg_seq` is strictly increasing per stream; `frag_seq` indexes fragments of the same message.
* Router reassembles contiguous `frag_seq=0..N` until a fragment arrives **without** `MORE`.
* Late/duplicate fragments are dropped; retransmission may be requested via ERROR with `code=ESEQ_RETRY`.
* Whole-frame `checksum` MUST be recomputed after any payload mutation; payload-level checksum enables partial verification prior to full decode.

---

## 5) Flow Control & Congestion Management

### 5.1 Windows (triplet)

* **Concurrency window**: max in‑flight sub‑agent calls.
* **Token window**: estimated total tokens allowed (in+out) outstanding.
* **Budget window**: remaining USD allowed outstanding.

### 5.2 Estimation

* Each agent **MUST** provide `estimate(tokens_in, tokens_out, usd)` per message prior to send (preflight). Router rejects sends that exceed the advertised window.

### 5.3 Dynamics

* **Additive Increase / Multiplicative Decrease (AIMD)** on ACK/timeout.
* **Bronze preemption** under pressure; **gold** has reserved minima.
* **Circuit breakers**: open on repeated 5xx/timeouts; exponential backoff per agent.

### 5.4 WINDOW\_UPDATE cadence

* Router issues **WINDOW\_UPDATE** every `N ms` or when ≥20% window delta occurs.

---

## 6) Routing & Policy

### 6.1 Registries

**RIB** (control plane) holds declarative policy; **FIB** (data plane) is computed with live metrics.

```yaml
models:
  qwen2.5-7b: { provider: ollama, ctx: 32k, cost: 0, speed: fast, strengths: [summarize, classify, quick_review] }
  llama3.1-8b: { provider: ollama, ctx: 32k, cost: 0, speed: fast, strengths: [summarize, draft, extract] }
  gemini-pro:  { provider: google, ctx: 2M,  cost: 3.0, speed: medium, strengths: [long_context, code_review, reasoning] }
  gpt5:        { provider: openai,  ctx: 1M,  cost: 4.0, speed: medium, strengths: [complex_refactor, test_gen, planning] }

agents:
  summarizer.local: { layer: L2, model: qwen2.5-7b, qos: bronze, p95_ms: 350, win30d: 0.61 }
  reviewer.gemini:  { layer: L3, model: gemini-pro,   qos: gold,   p95_ms: 1200, win30d: 0.82 }
  reviewer.gpt5:    { layer: L3, model: gpt5,         qos: gold,   p95_ms: 1400, win30d: 0.86 }

policies:
  - match: { task_type: code_review, diff_loc: ">150" }
    fanout: [summarizer.local, reviewer.gemini]
    escalation: { on: ["low_conf","test_fail","disagree_high"], to: reviewer.gpt5 }
    budget: { usd: 2.50, tokens: 800000 }
  - match: { task_type: summarize_repo }
    fanout: [summarizer.local]
    budget: { usd: 0.10, tokens: 60000 }
```

### 6.2 Selection Algorithm (weighted ECMP)

Score candidates by capability fit × historical win‑rate × cost × latency × context fit. Choose top‑K for fan‑out, respecting QoS and windows. Use **contextual bandits** to adapt weights online.

---

## 7) Consensus & Validation

### 7.1 Scorers

* **Evidence scorer**: requires citations (file\:line, tests, code blocks). Penalize hallucinations.
* **Agreement scorer**: compute overlap among agent findings (Jaccard/ROUGE on spans & rationales).
* **Cost scorer**: penalize expensive contributors unless severity is high.

### 7.2 Strategies

* **Union with tie‑break**: include all high‑severity issues; tie‑break by win‑rate.
* **Two‑phase commit**: critical changes require second agent ACK before commit.
* **Champion/Challenger**: pick cheapest acceptable; escalate upon low‑confidence or disagreements.

### 7.3 Output Schema (router → client)

```jsonc
{
  "result": {
    "findings": [
      {"id":"F-101","severity":"high","file":"auth/jwt.py","span":"45-80","claim":"Missing audience check","confidence":0.86,
       "provenance":["reviewer.gemini#12","summarizer.local#7"],
       "patch":"…","tests":["test_jwt_aud"]}
    ],
    "consensus": {
      "strategy":"union_tiebreak",
      "agreement":0.71,
      "uncertainties":["X509 flow"]
    }
  },
  "telemetry": {"tokens": 48210, "usd": 0.91, "latency_ms": 1320}
}
```

---

## 8) Session Lifecycle

1. **Open (SYN)**: client announces task meta + initial window; agents may send CAPABILITIES.
2. **Handshake (SYN‑ACK)**: router confirms window/QoS; optional compression/encoding negotiation.
3. **Fan‑out**: router dispatches to next‑hops; tracks in‑flight calls.
4. **Streaming**: agents stream PARTIAL frames with `MORE`; router ACKs and reassembles.
5. **Consensus**: when sufficient evidence arrives, router consolidates.
6. **Escalation**: triggered by rules (low\_conf, test\_fail, disagreement).
7. **Close (FIN)**: router emits FINAL result and metrics; both sides free state.

**Resumption:** idempotency keys allow re‑opening a stream after transient failures; duplicates are dropped.

---

## 9) QoS & Scheduling

* **Gold:** user‑visible, latency critical; reserved windows; preempt bronze.
* **Silver:** normal tasks; weighted fair queuing.
* **Bronze:** shadow/experiments; may be dropped during congestion.

**Preemption:** router may send RST to bronze streams with `code=EPREEMPT` when SLAs threaten gold.

---

## 10) Error Model

| Code         | Meaning                              | Router action           | Client hint                       |
| ------------ | ------------------------------------ | ----------------------- | --------------------------------- |
| `EPROTO`     | Bad frame/schema/version             | RST                     | Update SDK/spec                   |
| `ESEQ_RETRY` | Missing/late fragment                | Request retransmit      | Backoff + resend                  |
| `EWINDOW`    | Window exceeded (tokens/\$/parallel) | NACK + WINDOW\_UPDATE   | Reduce or await window            |
| `EBUDGET`    | Budget exhausted                     | FIN                     | Increase budget                   |
| `ETIMEOUT`   | Agent timeout                        | Retries + AIMD decrease | Increase timeout or replace agent |
| `EAGENTDOWN` | Next‑hop unhealthy                   | Circuit break, reroute  | Failover agent                    |
| `ESEC`       | Data‑scope violation                 | RST, audit              | Fix policy/labels                 |
| `ECONSENSUS` | No quorum                            | Escalate                | Provide more context              |

---

## 11) Security & Trust

* **AuthN**: mTLS or OIDC (JWT) between router and agents.
* **AuthZ**: per‑agent scopes (tools, data categories, max budgets, QoS tiers).
* **Signatures**: HMAC on frames; nonces to prevent replay.
* **Data‑scope tags**: `data_scope` labels enforce redaction and residency.
* **Audit**: immutable event log (session open/close, window changes, escalations, errors).

Threat model covers prompt injection, data exfiltration, over‑billing, poisoned consensus. Mitigations include tool sandboxing, content filters, cost guards, and provenance checks.

---

## 12) Observability

* **Traces**: `session_id`, `stream_id`, `agent`, `model`, `msg_seq`, `latency_ms`, `tokens_in/out`, `usd`, `confidence`, `route_path`, `window_state`.
* **Metrics**: cost per task, P50/P95 latency, escalation rate, consensus agreement, win‑rates, cache hit‑rate.
* **Logs**: structured JSON with redaction; correlate to CI/CD or git SHAs for code tasks.

---

## 13) Reference Router (Open Source) — Modules

* **Ingress (WS/HTTP2)** → frame codec (JSON/CBOR) → auth middleware.
* **Session Manager** → handshake, windows, heartbeats, retransmit queue.
* **Policy Engine** → RIB parse, FIB build (weights from metrics store).
* **Dispatcher** → fan‑out, parallelism control, retries, circuit breakers.
* **Reassembler** → per stream/message buffers, checksums, ACK/NACK.
* **Consensus Engine** → scorers, strategies, escalation triggers.
* **Budget Governor** → tokens/\$ counters, WINDOW\_UPDATE cadence.
* **Adapters** → Ollama, Gemini, OpenAI, local tools.
* **Observability** → traces/metrics/logs exporters (OTel).
* **Persistence** → cache (content‑addressed), policy store, audit log.

**Repo layout (proposal):**

```
atp/
  proto/              # JSON Schemas, CBOR maps, OpenAPI for control endpoints
  router/
    core/             # sessions, frames, windows, reassembly
    policy/           # RIB/FIB, bandits, QoS scheduler
    consensus/        # scorers & strategies
    adapters/         # ollama.py, gemini.py, gpt5.py, tools/
    observability/    # tracing, metrics
    security/         # authn, hmac, redaction
    cli/
  sdk/
    python/
    typescript/
    go/
  examples/
    code_review/
    repo_summary/
    retrieval_qa/
  tests/
    conformance/
    golden_tasks/
```

---

## 14) Provider Adapter Interface

**Python sketch:**

```python
class ProviderAdapter:
    name: str
    def capabilities(self) -> dict: ...  # ctx, tools, strengths
    def estimate(self, prompt: dict) -> dict: ...  # {in_tokens, out_tokens, usd}
    async def stream(self, prompt: dict):
        # yield fragments {type, content, confidence, partial_cost}
        yield
    def health(self) -> dict: ...  # p95_ms, error_rate
```

Adapters **MUST** implement `estimate` and `stream` (chunked output). Router wraps with timeouts and backoff.

---

## 15) Policy Examples

### 15.1 Code Review (Diff‑based)

* **Fan‑out:** summarizer.local (cheap outline) + reviewer.gemini (deep review).
* **Escalate:** reviewer.gpt5 if ⟨low\_confidence OR test\_fail OR disagreement⟩.
* **Windows:** start `max_parallel=2`, `tokens=120k`, `usd=1.25`; allow additive increase if ACKs early.

### 15.2 Repo Summarization

* Single local summarizer; escalate to planner (gemini/gpt5) only if *ambiguity high*.

### 15.3 Retrieval QA

* Retriever (embedding search) + local synthesizer. If answers conflict or cite weak docs, escalate to gemini/gpt5 for synthesis only with document snippets.

---

## 16) End‑to‑End Flow (ASCII)

```
Client → Router: SYN (task, budget) ─────────────────────────────►
Router → Client: SYN‑ACK (window) ◄──────────────────────────────
Router ⇄ summarizer.local:    PARTIAL/MORE … ACK … FINAL …
Router ⇄ reviewer.gemini:      PARTIAL/MORE … ACK … FINAL …
[Consensus + Optional Escalation to reviewer.gpt5]
Router → Client: FINAL (consensus result, telemetry)
Client ↔ Router: FIN/ACK
```

---

## 17) Compliance Levels

* **Level 1 (Core):** sessions, sequencing, windows, fan‑out, reassembly, FINAL, ERROR.
* **Level 2 (Secure):** authn/authz, signatures, data‑scope tags, audit, QoS.
* **Level 3 (Advanced):** consensus strategies, bandit routing, circuit breakers, resumption, CBOR.

Conformance tests assert wire compatibility and behavioral guarantees per level.

---

## 18) Conformance & Evaluation Harness

* **Golden tasks**: curated diffs, bugs, RAG questions with answers/patches.
* **Metrics**: issue recall\@N, precision, cost/task, P50/P95 latency, escalation rate, agreement.
* **Shadow routing**: dual‑run cheap vs. expensive to estimate regret and tune bandits.

---

## 19) Security Review & Threat Model (abridged)

* **Prompt injection** → sanitize tool I/O; constrain tool scopes; defensive prompting; require evidence.
* **Exfiltration** → data‑scope enforcement; redaction; allowlist egress; provenance checks.
* **Billing abuse** → windows, budgets, per‑agent caps, signed usage summaries.
* **Consensus poisoning** → require independent sources; penalize correlated errors; 2PC for critical changes.

---

## 20) Standardization Path (OAT‑WG)

1. **Publish v0.1 Draft** (this doc) under **Apache‑2.0**.
2. **Reference Router** (OSS) with Python SDK; TypeScript SDK next.
3. **Interop Demos**: bridges for LangChain, AutoGen, Qwen‑Agent, CrewAI.
4. **Spec Hardening**: run conformance plugfests; collect errata.
5. **v1.0**: freeze wire format; publish formal JSON Schemas + CBOR map.
6. **Governance**: Open Agent Transport Working Group (OAT‑WG), public meetings, RFC process.

---

## 21) Implementation Roadmap (90 Days)

**Week 0‑2**

* Frame codec (JSON), WS server, session manager, windows.
* Ollama adapter; Gemini & OpenAI adapters behind a shared interface.
* Simple policy engine; static RIB → FIB.

**Week 3‑5**

* Reassembler + consensus (union + tie‑break);
* Budget governor; WINDOW\_UPDATE cadence; QoS scheduler.
* Observability: OTLP traces, metrics, logs.

**Week 6‑8**

* Circuit breakers, bandit routing, resumption, audit log.
* Conformance tests; golden tasks for code review and RAG.

**Week 9‑12**

* Security hardening (mTLS/OIDC, HMAC, redaction);
* CBOR codec; TS SDK; plugin registry; interop bridges.

---

## 22) Developer UX — APIs

**Router control API (OpenAPI excerpt):**

```yaml
POST /v1/streams
  body: {task, budget, qos}
  resp: {session_id, stream_id, window}
POST /v1/streams/{id}/frames     # optional HTTP fallback to WS
GET  /v1/streams/{id}/events     # SSE for events
POST /v1/policies/reload         # hot reload RIB
GET  /v1/metrics                 # Prometheus/OTel scrape
```

**SDK (Python) — sending frames:**

```python
async with atp.Client(url, token) as c:
    sid, st = await c.open_stream(task=meta, budget={"usd":1.5,"tokens":300_000})
    async for event in c.events(st):
        if event.type == "FINAL":
            return event.payload
```

---

## 23) Example Policies (Copy‑Paste Ready)

### 23.1 Budget‑Sensitive Code Review

```yaml
policies:
  - match: { task_type: code_review, diff_loc: ">200", repo_risk: "high" }
    fanout: [summarizer.local, reviewer.gemini]
    escalation: { on: ["low_conf","test_fail"], to: reviewer.gpt5 }
    budget: { usd: 3.00, tokens: 1_200_000 }
  - match: { task_type: code_review, diff_loc: "<=200" }
    fanout: [summarizer.local]
    escalation: { on: ["low_conf"], to: reviewer.gemini }
    budget: { usd: 0.25, tokens: 120_000 }
```

### 23.2 Retrieval QA with Document Grounding

```yaml
policies:
  - match: { task_type: retrieval_qa }
    fanout: [retriever.local, synthesizer.local]
    escalation: { on: ["weak_citations","disagreement"], to: synthesizer.gemini }
    budget: { usd: 0.50, tokens: 200_000 }
```

---

## 24) Appendix — Minimal Reference Code (Python)

```python
# atp/frame.py
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import json, hmac, hashlib

@dataclass
class Frame:
    v: int
    session_id: str
    stream_id: str
    msg_seq: int
    frag_seq: int
    flags: List[str]
    qos: str
    ttl: int
    window: Dict[str, int]
    meta: Dict[str, Any]
    payload: Dict[str, Any]
    sig: Optional[str] = None

    def encode(self, key: bytes|None=None) -> bytes:
        # Stable JSON encoding
        body = {k: getattr(self,k) for k in (
            "v","session_id","stream_id","msg_seq","frag_seq","flags",
            "qos","ttl","window","meta","payload"
        )}
        raw = json.dumps(body, separators=(",",":"), ensure_ascii=False).encode()
        if key:
            mac = hmac.new(key, raw, hashlib.sha256).hexdigest()
            body["sig"] = mac
            raw = json.dumps(body, separators=(",",":"), ensure_ascii=False).encode()
        return raw
```

```python
# router/core/reassemble.py
from collections import defaultdict

class Reassembler:
    def __init__(self):
        self.buffers = defaultdict(lambda: defaultdict(dict))  # stream -> msg -> {frag: Frame}

    def add(self, f):
        b = self.buffers[f.stream_id][f.msg_seq]
        b[f.frag_seq] = f
        return self._complete(b)

    def _complete(self, b):
        i = 0
        while i in b:
            if "MORE" in b[i].flags: return False
            i += 1
        return i > 0

    def reassemble(self, stream_id, msg_seq):
        frags = self.buffers[stream_id].pop(msg_seq)
        parts = [frags[i].payload for i in sorted(frags)]
        return parts
```

```python
# router/core/window.py
class Window:
    def __init__(self, par=2, toks=120_000, usd=0.75):
        self.max_parallel, self.max_tokens, self.max_usd = par, toks, usd
        self.inflight, self.toks, self.usd = 0, 0, 0.0
    def admit(self, est_toks, est_usd):
        return (self.inflight < self.max_parallel and
                self.toks + est_toks <= self.max_tokens and
                self.usd + est_usd <= self.max_usd)
    def on_send(self, est_toks, est_usd):
        self.inflight += 1; self.toks += est_toks; self.usd += est_usd
    def on_ack(self, est_toks, est_usd):
        self.inflight = max(0, self.inflight-1)
```

```python
# router/adapters/ollama.py (sketch)
class OllamaAdapter(ProviderAdapter):
    name = "ollama.qwen2.5-7b"
    def capabilities(self):
        return {"ctx": 32_000, "strengths": ["summarize","classify"]}
    def estimate(self, prompt):
        n = len(json.dumps(prompt)) // 4  # toy estimator
        return {"in_tokens": n, "out_tokens": int(n*0.2), "usd": 0}
    async def stream(self, prompt):
        # yield token chunks as PARTIAL payloads
        yield {"type":"agent.result.partial","content":"…","confidence":0.55,"partial_cost":{"in":1000,"out":100}}
```

---

## 25) Licensing & Branding

* **License:** Apache‑2.0 (permits wide commercial adoption).
* **Branding:** "Agent Transport Protocol (ATP)" and "Open Agent Transport Working Group (OAT‑WG)".

---

## 26) Call for Collaboration

* Implementers: adapters for Ollama, Gemini, GPT‑5, local tools (linters, tests).
* Framework authors: bridges for LangChain, AutoGen, Qwen‑Agent, CrewAI.
* Researchers: consensus strategies, bandit routing, safety scoring.

*This draft is intended to be iterated quickly. Let’s make ATP the lingua franca for reliable, scalable multi‑agent systems.*
