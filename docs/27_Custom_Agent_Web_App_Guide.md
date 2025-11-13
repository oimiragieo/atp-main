# Custom Agent + Web App Guide

Goal: Build a user-facing web interface where users ask questions; backend (ATP control plane) picks the cheapest model that still meets a quality / latency bar.

---
## 1. Ultra-Simple Story (Tell It Like a User Journey)
1. User opens your web UI, types a question.
2. Browser sends it to your backend `/v1/ask`.
3. Backend calls ATP once with request metadata (tenant, prompt, desired quality).
4. ATP decides: try cheap model first; if answer confidence low -> escalate to stronger model.
5. ATP streams partial tokens back; backend forwards to browser via WebSocket / SSE.
6. ATP logs cost & quality metrics; you display token & cost counters live.

---
## 2. Frontend Architecture (Minimal Viable)
| Piece | Choice | Notes |
|-------|--------|-------|
| Framework | React / Next.js | Built-in streaming (app router) optional |
| Transport to backend | WebSocket (preferred) or HTTP + SSE | Enables partial tokens |
| State mgmt | Local component + simple cache keyed by conversation | Avoid heavy libs early |
| Auth | Session cookie or short-lived JWT from your IdP | Attach to /v1/ask calls |

Minimal message shape sent to backend:
```json
{
  "conversation_id": "c123",
  "turn_id": "t456",
  "prompt": "Explain zero-knowledge proofs simply",
  "quality": "balanced",      // fast | balanced | high
  "max_cost_usd": 0.02,
  "latency_slo_ms": 1800
}
```

---
## 3. Backend (Your API Layer) Responsibilities
| Responsibility | Action |
|----------------|-------|
| Auth & tenancy | Verify token → derive tenant_id & roles |
| Redaction (optional) | Pre-sanitize obvious PII before outbound |
| Call ATP | POST `/v1/route` or open `/ws` stream |
| Stream fanout | Forward chunks to browser; append to conversation store |
| Caching (optional) | Hash prompt+context → reuse answer window |
| Cost telemetry | Tally cumulative tokens & $ (from ATP metadata) |

---
## 4. ATP Request Model (Suggested)
```json
{
  "tenant": "acme",
  "prompt": "...",
  "context_refs": ["doc:policy/123"],
  "quality_target": "balanced",
  "latency_slo_ms": 1800,
  "cost_ceiling_usd": 0.02,
  "experiment": true,
  "session": {"id":"c123","turn":"t456"}
}
```

Response (final frame fields):
```json
{
  "text": "...final answer...",
  "model_used": "openai:gpt-3.5-turbo",
  "tokens_in": 120,
  "tokens_out": 220,
  "cost_usd": 0.0094,
  "savings_pct": 38.2,
  "escalation_count": 1,
  "quality_score": 0.84
}
```

---
## 5. Cheapest Acceptable Routing Strategy
We want: minimize cost subject to quality >= threshold and latency <= SLO.

Algorithm (two-tier hybrid):
1. Candidate set sorted by (estimated_cost) ascending.
2. For each candidate:
   - Predict quality Q_est and latency L_est (ATP maintains rolling stats).
   - If Q_est >= Q_min and L_est <= L_SLO: execute.
   - If streaming & confidence model yields low early confidence (e.g., perplexity proxy or classifier says "uncertain") before N tokens, escalate to next candidate in parallel (speculative) and whichever completes first with Q >= threshold wins.
3. If no candidate meets constraints directly, choose best (highest quality) within cost ceiling fallback or return graceful degrade message.

Pseudo-code:
```python
def choose_model(candidates, q_min, l_slo):
    for c in sorted(candidates, key=lambda m: m.cost_est):
        if c.quality_pred >= q_min and c.latency_p95 <= l_slo:
            return c
    # fallback: highest quality under cost ceiling else last
    viable = [c for c in candidates if c.cost_est <= min(x.cost_est for x in candidates)*3]
    return max(viable, key=lambda m: m.quality_pred)
```

Escalation trigger example: low lexical diversity or classifier < confidence threshold after first 40 output tokens.

---
## 6. Confidence / Quality Signals (Lightweight)
| Signal | How | Cost |
|--------|-----|------|
| Response length growth | token_count / time | Free |
| Lexical diversity | unique_tokens/total | Cheap |
| Heuristic classifier | tiny local model scoring partial answer | Low |
| Retrieval overlap (if RAG) | % of answer tokens in retrieved docs | Medium |

If combined score < threshold early: escalate.

---
## 7. Streaming Framing (Simplified)
Partial frame example:
```json
{"type":"chunk","seq":5,"text":"...partial...","model":"cheap-model"}
```
Final frame adds metadata:
```json
{"type":"final","text":"...","model":"cheap-model","tokens_out":220,"cost_usd":0.0094,"savings_pct":38.2}
```

---
## 8. Handling Errors & Escalation
| Situation | Action |
|----------|--------|
| 5xx from adapter | Retry w/ exponential backoff or escalate next model |
| Policy deny | Surface sanitized message; do NOT auto escalate |
| Cost ceiling would be exceeded | Provide partial or suggest narrower query |
| Latency SLO breach predicted | Launch parallel higher-performance model |

---
## 9. Conversation Memory Integration
Option A: Client sends last N turns (stateless ATP call).  
Option B: Use memory fabric session ID; ATP pulls prior context.  
Option C: Hybrid: short-term memory server-side + immediate ephemeral context from client.

Start with Option A (simplest), then graduate to B when scale demands.

---
## 10. Minimal Data Model (Backend DB)
| Table | Fields |
|-------|--------|
| conversations | id, tenant_id, created_at |
| turns | id, conversation_id, role(user/agent), prompt, answer, model_used, cost_usd, latency_ms |
| savings_snapshot | day, tenant_id, baseline_cost_usd, actual_cost_usd, savings_pct |

---
## 11. Cost Baseline Computation
Baseline = (tokens_in + tokens_out) * reference_price_of_highest_quality_model.
Savings % = (baseline_cost - actual_cost)/baseline_cost * 100.

Store per turn; roll up daily for dashboards.

---
## 12. Security & Privacy Quick Wins
| Risk | Mitigation |
|------|-----------|
| Sensitive PII leaves boundary | Ingress redaction + allowlist of outbound adapters |
| Prompt injection to tool calls | Tool permission scopes per tenant/session |
| Data exfil via model selection | Policy restricts disallowed regions/providers |

---
## 13. Observability Panels
| Panel | Metric |
|-------|--------|
| Cost trend | cost_usd per hour |
| Savings | savings_pct distribution |
| Quality surrogate | avg quality_score per model |
| Escalation rate | (# escalations)/(# turns) |
| Latency | p95 per model |

Goal: Keep escalation rate <20% (means initial cheap pick good), savings_pct >15%.

---
## 14. Incremental Delivery Plan
| Week | Deliverable |
|------|-------------|
| 1 | /v1/ask REST + single model + logging |
| 2 | Streaming WS + cheap+premium two-level fallback |
| 3 | Cost & quality metrics + savings baseline calc |
| 4 | Heuristic early confidence + escalation |
| 5 | Multi-model candidate expansion + daily savings dashboard |
| 6 | Policy + redaction integration |

---
## 15. FAQ (Focused on This Flow)
**Q: Where does routing happen?** Inside ATP core; your backend just forwards.
**Q: How do we define "cheap"?** Lowest expected cost per token among allowed providers meeting minimum quality threshold.
**Q: How do we measure quality without labels?** Use heuristic proxies + later optional human feedback loop.
**Q: Do we cache answers?** Start with prompt hash cache (avoid redundant cost). Invalidate on policy/model change.

---
## 16. Next Steps
1. Implement `/v1/ask` stub calling existing POC router (or placeholder).  
2. Add cheap vs premium model metadata JSON file (cost & quality priors).  
3. Introduce simple choose_model() as above.  
4. Retrofit streaming once stable.  
5. Layer policy & redaction.  
6. Add metrics & savings dashboard.

---
This guide should help translate “user asks a question” → “cheapest acceptable answer pipeline.”
