# 28 — Custom Agent Architecture

Goal: Provide a production-aligned reference agent that consumes ATP routing, exposes a web UI, and can be monetized (SaaS multi-tenant). This becomes the tangible product layer on top of the control plane.

---
## 1. High-Level Layers
| Layer | Responsibility | Tech (Initial) |
|-------|----------------|----------------|
| Web UI | Chat UX, streaming display, cost & latency indicators | React/Next.js (future) / simple HTML first |
| API Backend (BFF) | Auth, session mgmt, conversation store, rate limits | FastAPI / Node (choose one) |
| Agent Orchestrator | Planning, tool selection, memory fetch, ATP request building | Python package `agent_core` |
| Control Plane (ATP) | Routing, policy, cost optimization, observability | Existing POCs evolving to services |
| External Tools & APIs | Domain data, retrieval, CRMs, ticketing, search | Adapter integration via ATP |

---
## 2. Agent Internal Loop (Minimal Viable)
1. Receive user message (with conversation context IDs).
2. Decide: direct answer vs retrieval vs multi-step.
3. Construct ATP /v1/ask request (quality target + cost ceiling derived from plan).
4. Stream answer chunks; apply optional lightweight reasoning wrapper (e.g., reflectively refine final output).
5. Persist turn (conversation_id, turn_id, model_used, cost, quality proxies).
6. Emit metrics (latency, tokens, savings, escalation).

---
## 3. Planning Modes
| Mode | Trigger | Behavior |
|------|---------|----------|
| Direct | Short question, low complexity classifier | Single ask to ATP |
| Retrieve-Answer | Keyword / semantic & knowledge base hit | Fetch docs → include as context_refs |
| Multi-Step | Detected decomposition terms ("analyze", "plan", etc.) | Sequence: plan → execute steps → summarize |

Classifier can start rule-based; upgrade later with small logistic model.

---
## 4. Memory Integration Strategy
| Memory Type | Usage |
|-------------|-------|
| Short-term conversation | Rehydrate last N turns to agent planner |
| Long-term facts | Vector search via memory gateway (context_refs) |
| Scratchpad | Local ephemeral list of reasoning tokens (not stored) |

---
## 5. Tool Abstraction
Tools registered with metadata: name, input schema, execution function. The agent planner can chain tools then call ATP for language synthesis. Eventually exposed via MCP.

Initial built-ins:
- `search_memory(query)` → memory gateway search
- `fetch_doc(id)` → memory retrieval
- `call_router(prompt, context_refs, quality, cost_ceiling)` → wraps ATP /v1/ask streaming

---
## 6. Cost Guardrails
Before each ATP call:
1. Estimate token size (heuristic: characters / 4).
2. Multiply by cheapest route cost per token.
3. If estimated cost > per-turn ceiling (tenant policy), either degrade quality target or ask user to refine.

---
## 7. Quality Proxies
| Proxy | Collection | Use |
|-------|------------|-----|
| Length heuristic | token count/time | Detect stagnation |
| Lexical diversity | unique / total tokens | Low diversity trigger rephrase |
| Retrieval coverage | % answer tokens in retrieved docs | Validate retrieval value |

---
## 8. Extensibility Points
| Extension | Mechanism |
|-----------|----------|
| New tool | Implement function + register in tool registry |
| New planner policy | Add strategy in planner switch map |
| Custom quality rule | Append rule to quality evaluation pipeline |

---
## 9. Multi-Tenancy Considerations
| Concern | Approach |
|---------|---------|
| Data isolation | Prefix keys with tenant_id; policy checks at BFF + ATP |
| Per-tenant cost budgets | Stored in DB; midpoint alerts when 80% consumed |
| Feature flags | Flag table controlling access to planner modes |

---
## 10. Metrics (Agent Layer)
- agent_turn_latency_ms
- agent_tokens_in/out
- agent_cost_usd
- agent_savings_pct
- agent_escalation_rate
- agent_planning_mode_count{mode}

---
## 11. Rollout Milestones
| Week | Output |
|------|--------|
| 1 | agent_core package (router client + simple planner) |
| 2 | Web UI chat + streaming + persistence |
| 3 | Retrieval integration (memory gateway) |
| 4 | Planner modes (direct vs retrieve) + metrics dashboard |
| 5 | Cost guardrails + escalation analytics |
| 6 | Multi-tenant auth + per-tenant budgets |

---
## 12. Monetization Hooks
- Premium planner modes (multi-step reasoning) gated by tier.
- Higher retention of conversation history (Team/Enterprise tiers).
- Usage-based billing on agent turns and routed model cost pass-through with margin.

---
## 13. Security & Compliance Hooks
- Central audit event per agent turn linking all ATP decision IDs.
- Redaction pre-planner; raw user input stored only if policy allows.

---
## 14. Next Implementation Steps (Immediate)
1. Create `agent_core` package with: router_client, tool registry, simple planner, run function.
2. Add POC test: start router service; run agent ask; assert final answer.
3. Add metrics stubs for future instrumentation.

---
## 15. Future (Not Now)
- Human feedback loop (thumbs up/down) feeding quality model.
- Active learning for planner mode classification.
- Tool marketplace embedding.

