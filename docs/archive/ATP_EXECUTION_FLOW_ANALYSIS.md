# ATP Codebase Comprehensive Execution Flow Analysis

**Generated:** 2025-11-18  
**Scope:** User entry points, core execution paths, implementation gaps, and UX issues  
**Files Analyzed:** 229 Python files, 20+ documentation files, 182 test files

---

## EXECUTIVE SUMMARY

The ATP codebase is **architecturally sophisticated** with enterprise-grade features (multi-region routing, bandit selection, policy enforcement, carbon tracking) but has a **critical execution gap**: 

**The router service generates SYNTHETIC/MOCK responses instead of calling real adapters.**

### Key Findings:

1. **Mock Response Generation**: `/v1/ask` endpoint yields "lorem" placeholder text instead of making real LLM API calls
2. **Adapter Integration**: Only 2/7 adapters are production-ready (Anthropic, OpenAI); remaining 5 are stubs with hardcoded responses
3. **Documentation Accuracy**: Good transparency in recent docs (ADAPTER_STATUS.md, AI_ASSISTANT_GUIDE.md) but inconsistencies in main README
4. **Code Complexity**: 229 Python files with many advanced features that are never actually invoked
5. **Hardcoded Models**: Router uses fake model names ("cheap-model", "premium-model") in routing decisions

---

## 1. USER ENTRY POINTS & WORKFLOWS

### 1.1 Installation & Setup Path

**User Journey:**
```
1. Clone repository
2. Set ROUTER_ADMIN_API_KEY (≥32 chars) in .env
3. docker compose build && docker compose up -d
4. Services start (router:7443, memory-gateway:8080, redis, prometheus, grafana)
5. Validate: python scripts/validate_installation.py
```

**Key Gotchas:**
- Router will NOT start without `ROUTER_ADMIN_API_KEY` environment variable
- Port is 7443 (not 8000 as in some old docs)
- Default docker-compose uses STUB adapters that return mock data

### 1.2 Main User Interfaces

| Interface | Location | Status | Implementation |
|-----------|----------|--------|-----------------|
| **REST API** | `/v1/ask` | ✅ Exists | Generates synthetic responses |
| **REST API** | `/v1/plan` | ✅ Exists | Returns routing plan without execution |
| **WebSocket** | `/mcp` | ✅ Exists | Model Context Protocol integration (simulated) |
| **CLI** | `atpctl` | ⚠️ Partial | Some commands broken (see CRITICAL GOTCHA #2) |
| **Memory Gateway** | `http://localhost:8080` | ✅ Exists | Storage/retrieval operations |

### 1.3 Typical Request Flow (What Actually Happens)

```
User POST http://localhost:7443/v1/ask with:
{
  "prompt": "explain quantum computing",
  "quality": "balanced",
  "latency_slo_ms": 2000
}
        ↓
[Authentication check - OIDC/JWT optional]
        ↓
[Session tracking & rate limiting]
        ↓
[PII scrubbing (optional)]
        ↓
[WAF check (optional)]
        ↓
choose_model() → selects from HARDCODED catalog
  - "cheap-model" (cost: 0.4)
  - "exp-model" (cost: 0.8)
  - "mid-model" (cost: 1.0)
  - "premium-model" (cost: 2.0)
        ↓
BANDIT SELECTION (UCB/Thompson sampling)
  - Reorders candidates based on observed quality
  - Still selecting from same hardcoded models
        ↓
🔴 CRITICAL: Instead of calling adapter:
  - Generates 120-180 synthetic tokens
  - Uses `phrase = "lorem" if generated < target else "done"`
  - Simulates latency with `await asyncio.sleep(chunk / speed)`
  - No adapter is ever contacted
        ↓
Records FAKE observation:
  - quality_score: random.uniform(0.7, 0.9)
  - latency: simulated
  - cost: calculated from fake model params
  - tokens: hardcoded (30 input, 120-180 output)
        ↓
Response with final metadata (all synthetic):
{
  "text": "lorem lorem lorem done",
  "model_used": "cheap-model",
  "cost_usd": 0.045,
  "quality_score": 0.825,
  "tokens_in": 30,
  "tokens_out": 150,
  ...
}
```

---

## 2. CORE EXECUTION PATH ANALYSIS

### 2.1 `/v1/ask` Endpoint Execution (service.py:1119)

**File:** `/home/user/atp-main/router_service/service.py` (3,045 lines)

```python
@app.post("/v1/ask")
async def ask(req: AskRequest, request: Request) -> StreamingResponse:
```

**Phases of execution:**

#### Phase 1: Pre-routing (lines 1119-1240)
```python
# Session management
sess_id = req.session_id or request.client.host or "anon"

# Consistency level enforcement (GAP-305)
consistency_level = req.consistency_level or "EVENTUAL"

# Rate limiting (AIMD window)
window_allowed = GLOBAL_AIMD.get(sess_id)

# Prompt validation
if len(req.prompt) > settings.max_prompt_chars:
    return JSONResponse(status_code=413, detail="prompt_too_large")

# Optional WAF check
if os.getenv("ENABLE_WAF") == "1":
    allowed, reason = check_prompt(req.prompt)
    if not allowed:
        return JSONResponse(400, {"error": "waf_block"})

# PII scrubbing (optional)
prompt_in = _scrub_pii(req.prompt) if settings.enable_pii_scrub else req.prompt

# Extract forced model tag (if any)
if "<CCR-SUBAGENT-MODEL>" in prompt_in:
    # Parse model override from prompt
```

#### Phase 2: Model Selection (lines 1237-1340)
```python
# Key function: choose_model.py
plan, regret_analysis, routing_metadata = choose(
    req.quality,           # "fast", "balanced", "high"
    req.latency_slo_ms,    # milliseconds
    _MODEL_REGISTRY,       # hardcoded model registry
    "A"                    # required safety grade
)

# Plan structure (3 candidates):
# plan[0] = primary (cheapest acceptable)
# plan[1] = exploration (alternative to gather data)
# plan[2] = fallback (premium escalation)

# Optional: Champion/Challenger selection
if os.getenv("ENABLE_CHALLENGER") == "1":
    ch = select_challenger(primary, candidates)
    challenger_name = ch.name

# Bandit selection (UCB or Thompson)
if BANDIT_STRATEGY == "ucb":
    bandit_choice = ucb_select(cluster_key, plan, UCB_EXPLORE_FACTOR, prompt_in, req.latency_slo_ms)
elif BANDIT_STRATEGY == "thompson":
    bandit_choice = thompson_select(cluster_key, plan)

# Reorder plan with bandit choice first
if bandit_choice:
    plan = [chosen_model] + [others...]
```

**`choose_model.py` (lines 17-112):**

```python
def choose(quality, latency_slo_ms, registry, required_safety="A"):
    """
    Returns list of candidates sorted by:
    1. Cost (cheapest first)
    2. Quality threshold check
    3. Latency constraint
    """
    q_min = QUALITY_THRESH.get(quality, 0.75)
    
    # Carbon-aware routing (optional)
    ordered = sorted(CATALOG, key=lambda c: c.cost_per_1k_tokens)
    if carbon_aware:
        ordered = sorted(ordered, key=lambda c: 
            carbon_tracker.calculate_routing_weight(c.region, c.cost_per_1k_tokens))
    
    # Build plan: select candidates that meet constraints
    plan = []
    for c in ordered:
        rec = registry.get(c.name, {})
        if rec.get("status") == "shadow":
            continue  # Skip shadow models from primary plan
        grade = rec.get("safety_grade", "A")
        if grade < required_safety:
            continue
        if c.quality_pred >= q_min and c.latency_p95 <= latency_slo_ms:
            plan.append(c)
            break  # Take first match
    
    if not plan:
        # Fallback: take highest quality under latency
        viable = [c for c in ordered if c.latency_p95 <= latency_slo_ms] or ordered
        plan.append(max(viable, key=lambda c: c.quality_pred))
    
    # Add exploration candidate
    # Add premium escalation candidate
    return plan, regret_analysis, energy_attribution
```

**Hardcoded Model Catalog (routing_constants.py:16):**

```python
CATALOG = [
    Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
    Candidate("exp-model", 0.8, 0.78, 950, "us-east"),
    Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
    Candidate("premium-model", 2.0, 0.90, 1400, "asia-east"),
]
```

**These are NOT real LLM models. They are fake model names used only for routing logic.**

#### Phase 3: Response Generation (lines 1341-1430) 🔴 **CRITICAL MOCKING**

```python
async def stream() -> AsyncIterator[str]:
    """
    Generate streaming response.
    
    IMPORTANT: This does NOT call any adapter.
    It generates synthetic data.
    """
    
    # Emit routing plan
    yield json.dumps({
        "type": "plan",
        "candidates": [...],
        "reason": "cheapest acceptable then escalation (bandit)",
        "roles": roles,
    }) + "\n"
    
    # Generate tokens
    target_tokens = 180 if req.quality == "high" else 120
    generated = 0
    primary_speed = 25  # tokens per second (fake)
    
    while generated < target_tokens:
        elapsed = time.time() - start
        
        # Check escalation condition
        if not escalation_used and escalation and elapsed * 1000 > req.latency_slo_ms * 0.6:
            escalation_used = True
            yield json.dumps({
                "type": "event",
                "event": "escalate",
                "model": escalation.name
            }) + "\n"
        
        # Hard timeout
        if elapsed * 1000 > req.latency_slo_ms * 4:
            cancelled = True
            break
        
        chunk = min(12, target_tokens - generated)
        generated += chunk
        
        # 🔴 SIMULATE LATENCY - DOES NOT CALL ADAPTER
        await asyncio.sleep(chunk / primary_speed)
        
        # Check if client disconnected
        if await request.is_disconnected():
            cancelled = True
            break
        
        # 🔴 GENERATE FAKE RESPONSE TEXT
        phrase = "lorem" if generated < target_tokens else "done"
        
        async for out in emit(primary.name, phrase):
            yield out
```

**Key Insight:** The text generation is literally "lorem" repeated, with "done" at the end. This is not calling any LLM.

#### Phase 4: Quality & Cost Calculation (lines 1431-1445)

```python
# Quality score: either calculated or RANDOM
quality = (
    _evaluate_quality(" ".join(text_parts)) 
    if settings.quality_eval_mode != "off" 
    else random.uniform(0.7, 0.9)  # 🔴 FAKE RANDOM SCORE
)

# Duration tracking
duration_ms = (time.time() - start) * 1000
_record_latency(duration_ms)

# Cost calculation from FAKE model parameters
cost_tokens = 30 + target_tokens
cost_usd = (cost_tokens / 1000.0) * primary.cost_per_1k_tokens
# cost_usd = (150 / 1000) * 0.4 = 0.06 for "cheap-model"

# Baseline comparison (for "savings" metric)
baseline = (cost_tokens / 1000.0) * 2.0  # Assume baseline is 2x cost
savings = (baseline - cost_usd) / baseline * 100
```

#### Phase 5: Observation Recording (lines 1526-1581)

```python
observation = {
    "ts": time.time(),
    "prompt_hash": prompt_hash(prompt_in),
    "cluster_hint": cluster_hint,
    "model_plan": [c.name for c in plan],
    "primary_model": primary.name,
    "escalated": escalation_used,
    "latency_s": round(total, 4),
    "tokens_in": 30,
    "tokens_out": target_tokens,
    "cost_usd": round(cost_usd, 6),
    "quality_score": round(quality, 3),
    "phase": phase,
    # 🔴 All of these are SYNTHETIC
}

if validate_observation(observation):
    _record_observation(observation)
```

#### Phase 6: Shadow Evaluation (lines 1583-1660)

Even shadow evaluation is fake:

```python
def eval_shadow(sm: str, ph: str, base_q: float, base_cost: float) -> None:
    """Evaluate a shadow model."""
    try:
        # 🔴 FAKE SHADOW METRICS
        sq = base_q + random.uniform(-0.02, 0.03)
        sl = total * random.uniform(0.8, 1.1)
        sc = base_cost * random.uniform(0.7, 0.95)
        
        shadow_obs = {
            "shadow_model": sm,
            "shadow_quality": round(sq, 3),
            "shadow_latency_s": round(sl, 4),
            "shadow_cost_usd": round(sc, 6),
        }
        # Record fake observation
```

**Shadow models don't actually run - their metrics are randomized variations of primary response.**

#### Phase 7: Lifecycle Promotion/Demotion (lines 1661-1702)

Models are promoted/demoted based on the FAKE statistics that were just recorded:

```python
evaluate_promotions(
    cluster_key,
    _MODEL_REGISTRY,
    _MODEL_LAST_ACTION,
    stat_map_full,  # Stats built from fake observations!
    _LIFECYCLE_HISTORY.append,
    _persist_lifecycle,
    _record_observation,
)
```

This means model promotion decisions are based on **statistics collected from synthetic data**.

---

### 2.2 Model Selection Strategy (`adaptive_stats.py`)

The codebase uses bandit algorithms (Thompson Sampling, UCB) to select between models. However:

1. **Thompson Sampling** - Assumes Beta distribution of model quality. Uses collected statistics.
2. **UCB (Upper Confidence Bound)** - Balances exploitation vs exploration using regret bounds.

Both strategies work on the **FAKE statistics** because real adapter calls never happen.

### 2.3 Adapter Architecture (But Unused)

**Adapter Integration Pattern:**

```
┌─────────────────────────────────────────────────────────────┐
│ Router Service (/v1/ask endpoint)                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ├─→ choose() → select model from CATALOG
                     │   (hardcoded fake models)
                     │
                     ├─→ [UNUSED] adapter lookup
                     │   - adapter_registry.py exists but never called
                     │   - AdapterCapability class defined but unused
                     │
                     └─→ Generate synthetic response
                         NO ADAPTER CALL EVER MADE
```

**Adapter Files That Are Never Called:**

- `/adapters/python/anthropic_adapter/server.py` - Production-ready but unused
- `/adapters/python/openai_adapter/server.py` - Production-ready but unused
- `/adapters/python/ollama_adapter/server.py` - Stub (mock) but unused
- `/adapters/python/google_adapter/` - Stub (mock) but unused
- `/adapters/python/vllm_adapter/` - Stub (mock) but unused
- `/adapters/python/llamacpp_adapter/` - Stub (mock) but unused
- `/adapters/python/persona_adapter/` - Stub (mock) but unused

**The adapter framework exists but is completely decoupled from the main /v1/ask execution path.**

---

## 3. AI SUBAGENT EXPERIENCE

### 3.1 Documentation Critical Issues for AI Assistants

See `AI_ASSISTANT_GUIDE.md` - This file explicitly warns about:

1. **Stub adapters returning mock data** - Users see fake responses
2. **CLI commands partially broken** - Some `atpctl` commands don't work
3. **Environment variable requirement** - Router won't start without ROUTER_ADMIN_API_KEY
4. **Port confusion** - Documentation mixes port 8000 and 7443

### 3.2 Most Critical Files for Understanding

| File | Purpose | Current Status |
|------|---------|-----------------|
| `router_service/service.py` | Main router logic (3,045 lines) | Generates synthetic responses |
| `router_service/choose_model.py` | Model selection (112 lines) | Routes using fake model catalog |
| `router_service/adaptive_stats.py` | Bandit algorithms | Works on synthetic statistics |
| `ADAPTER_STATUS.md` | Adapter implementation status | ✅ Accurate and helpful |
| `AI_ASSISTANT_GUIDE.md` | AI assistant warnings | ✅ Comprehensive and honest |

### 3.3 Confusion & Pain Points for AI Assistants

1. **Code exists but isn't called**: adapter_registry.py, multiple adapter servers, RoutingService in domain/ - all dead code
2. **Documentation vs implementation**: README claims routing works, but model selection is purely algorithmic on fake models
3. **Complex feature names that don't work**: "Shadow Evaluation", "Champion/Challenger", "Bandit Selection" all work with synthetic data
4. **Hardcoded values everywhere**: Model names, pricing, quality predictions all hardcoded
5. **Circular logic**: Statistics are recorded from synthetic responses, used to make routing decisions, recorded again

### 3.4 Documentation Gaps

**Documented but not implemented:**
- Real adapter integration for stub adapters
- Multi-region failover (code exists, but no adapters to failover to)
- Cost optimization (optimizes cost of fake models)
- Carbon-aware routing (routes among fake models)

**Implemented but underdocumented:**
- How synthetic responses are generated
- That model selection from hardcoded catalog
- That quality scores are random

---

## 4. CRITICAL IMPLEMENTATION GAPS

### 4.1 Major TODOs and Missing Features

```python
# service.py:1801
# adapter_type = tool_args.get("adapter_type")  # TODO: Use for adapter-specific routing

# adapter_registry.py - Built but never used
class AdapterRegistry:
    def register_capability(self, capability_data):
        ...  # Never called in /v1/ask flow

# domain/routing/service.py - RoutingService exists but never instantiated
class RoutingService:
    async def select_model(self, ...):
        ...  # Never called - choose() used instead
```

### 4.2 Stub Implementations (Placeholders with Mock Data)

**5 adapters return hardcoded mock responses:**

1. **Ollama Adapter** (`adapters/python/ollama_adapter/server.py:95`)
   ```python
   chunks = [
       "This is a mock response from Ollama adapter. ",
       "In production, this would connect to a real Ollama instance. ",
       f"You asked: {prompt}"
   ]
   ```

2. **Google/Vertex AI** - Returns mock data
3. **VLLM** - Returns mock data  
4. **LlamaCPP** - Returns mock data
5. **Persona** - Returns mock data

**Only 2 are production-ready:**
- ✅ Anthropic adapter - Real API integration
- ✅ OpenAI adapter - Real API integration

### 4.3 Mock/Simulated Execution Patterns

```python
# Pattern 1: Simulate latency
await asyncio.sleep(chunk / primary_speed)  # Fake delay

# Pattern 2: Generate placeholder text
phrase = "lorem" if generated < target_tokens else "done"

# Pattern 3: Random quality scores
random.uniform(0.7, 0.9)

# Pattern 4: Calculated fake costs
cost_usd = (cost_tokens / 1000.0) * primary.cost_per_1k_tokens

# Pattern 5: Simulate streaming chunks
for i, chunk in enumerate(words):
    yield json.dumps(...) + "\n"
```

### 4.4 Unused/Dead Code

**Directories with code never executed:**

1. `router_service/domain/` - DDD architecture that's never instantiated
   - `domain/routing/service.py` - RoutingService (unused)
   - `domain/observation/` - ObservationService (unused)
   - `domain/adapter/` - Adapter registry (unused)

2. `router_service/adapters/` - 5 stub adapters never called

3. Legacy/experimental modules:
   - `service_legacy_backup.py` - Just imports app for backward compatibility
   - `cloud_sync.py` - Never referenced
   - `observation_curator.py` - Observation handling that's never called

### 4.5 Hardcoded Catalog Problem

```python
# routing_constants.py - FAKE MODEL NAMES
CATALOG = [
    Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
    Candidate("exp-model", 0.8, 0.78, 950, "us-east"),
    Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
    Candidate("premium-model", 2.0, 0.90, 1400, "asia-east"),
]
```

These model names are **not real LLM models**. They're just placeholders for routing algorithm testing.

No integration with real model providers:
- ❌ No Anthropic model selection (adapter exists but unused)
- ❌ No OpenAI model selection (adapter exists but unused)
- ❌ No Ollama model selection (adapter exists but unused)

---

## 5. UNUSED & LEGACY COMPONENTS

### 5.1 Large Unused Modules

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `agp_update_handler.py` | 2,675 | AGP state management | Never called in /v1/ask |
| `backup_system.py` | 1,262 | Database backup orchestration | Not in main flow |
| `multi_region.py` | 1,065 | Multi-region routing | Not in main flow |
| `disaster_recovery.py` | 1,244 | DR coordination | Not in main flow |
| `edge_router.py` | 873 | Edge routing logic | Not in main flow |
| `advanced_waf.py` | 860 | WAF rules | Optional, not used by default |

### 5.2 Archive/Backup Files

- `service_legacy_backup.py` - 272 bytes - Just re-exports main app

### 5.3 Dead Code Indicators

**High number of files with 'stub' in implementation:**

```
router_service/arpki_validator.py:
    """Validate the certificate chain (stub implementation)."""
    # Stub: just check we have at least one certificate

router_service/spiffe_svid.py:
    class SpireClientStub:
        """Stub implementation for SPIFFE/SPIRE integration."""
```

**Code with TODOs never completed:**

```python
# adapter_type = tool_args.get("adapter_type")  # TODO: Use for adapter-specific routing
```

### 5.4 Features Documented But Not Functional

| Feature | Claims | Reality |
|---------|--------|---------|
| **Shadow Evaluation** | Test new models in parallel | Generates random fake metrics |
| **Champion/Challenger** | A/B test models | Selects challenger from fake models |
| **Multi-region Routing** | Fail over across regions | Routes among fake models in different regions |
| **Carbon-Aware Routing** | Optimize CO2 emissions | Weights fake models by fake carbon costs |
| **Adaptive Routing** | Bandit selection improves over time | Optimizes based on synthetic observations |
| **Cost Optimization** | Stays within budget | Optimizes budget of fake models |
| **Lifecycle Promotion/Demotion** | Models promoted based on performance | Based on synthetic statistics |

---

## 6. DOCUMENTATION VS IMPLEMENTATION GAPS

### 6.1 Major Inconsistencies

| Claim | Documentation | Reality |
|-------|---------------|---------|
| "Adaptive model routing" | Intelligently routes to best model | Routes among 4 hardcoded fake models |
| "Real-time cost optimization" | Tracks actual costs | Calculates fake costs from hardcoded pricing |
| "Shadow evaluation" | Run candidates in parallel | Generate random fake metrics |
| "AI model adapter integration" | "supports Anthropic, OpenAI, Ollama..." | Anthropic/OpenAI adapters exist but unused; others are stubs |
| "Quality improvement" | Models improve via learning | Quality scores are random 0.7-0.9 |
| "Bandit model selection" | Thompson/UCB algorithms work | Algorithms work on synthetic data |
| "Production deployment ready" | Can deploy to production | Only with Anthropic or OpenAI keys, and code must be modified to actually call adapters |

### 6.2 Documentation That's Actually Accurate

✅ `ADAPTER_STATUS.md` - Clearly documents which adapters are stubs vs production
✅ `AI_ASSISTANT_GUIDE.md` - Warns about stub adapters and broken CLI commands
✅ `ENVIRONMENT_VARIABLES.md` - Accurately documents all environment variables
✅ `DEEP_DIVE_REVIEW.md` - Comprehensive analysis of issues found and fixed

### 6.3 Documentation Gaps

❌ README.md doesn't warn that default responses are synthetic
❌ GETTING_STARTED.md doesn't explain that you need to configure real adapters
❌ QUICK_START.md doesn't mention responses are fake
❌ No documentation of the hardcoded model catalog
❌ No explanation of why responses say "lorem"

---

## 7. END-TO-END REQUEST WALKTHROUGH

### 7.1 User Request: `POST /v1/ask`

```bash
curl -X POST http://localhost:7443/v1/ask \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a poem about artificial intelligence",
    "quality": "balanced",
    "latency_slo_ms": 2000
  }'
```

### 7.2 Server-Side Execution

**1. Authentication & Session (Concurrency Semaphore)**
```
✓ Max concurrent requests enforced (_CONCURRENCY_SEM)
✓ Session tracking (_SESSION_ACTIVE)
✓ OIDC verification (optional)
✓ Rate limiting (AIMD window per session)
```

**2. Input Validation**
```
✓ Prompt size check (max 6000 chars default)
✓ Optional WAF check
✓ Optional PII scrubbing
```

**3. Model Selection**
```python
plan, regret, energy = choose(
    quality="balanced",
    latency_slo_ms=2000,
    registry=_MODEL_REGISTRY,
    required_safety="A"
)
# Result: [Candidate("cheap-model", ...), Candidate("mid-model", ...), Candidate("premium-model", ...)]
```

**4. Bandit Selection**
```python
if BANDIT_STRATEGY == "ucb":
    chosen = ucb_select("_default", plan, UCB_EXPLORE_FACTOR=1.4, ...)
    # Reorder plan with chosen model first
elif BANDIT_STRATEGY == "thompson":
    chosen = thompson_select("_default", plan)
    # Reorder plan with chosen model first
```

**5. Response Streaming**
```
Client starts receiving JSON stream:

{
  "type": "plan",
  "candidates": [
    {"model": "cheap-model", "cost_per_1k": 0.4, "quality_pred": 0.70, "latency_p95": 900},
    {"model": "mid-model", "cost_per_1k": 1.0, "quality_pred": 0.80, "latency_p95": 1100},
    {"model": "premium-model", "cost_per_1k": 2.0, "quality_pred": 0.90, "latency_p95": 1400}
  ],
  "reason": "cheapest acceptable then escalation (bandit)",
  "roles": [
    {"role": "primary", "model": "cheap-model"},
    {"role": "explore", "model": "mid-model"},
    {"role": "fallback", "model": "premium-model"}
  ]
}

{
  "type": "event",
  "event": "challenger_selected",
  "model": "mid-model"  # If ENABLE_CHALLENGER
}

{
  "seq": 1,
  "text": "lorem",
  "model": "cheap-model"
}

{
  "seq": 2,
  "text": "lorem",
  "model": "cheap-model"
}

... (many more "lorem" chunks)

{
  "seq": 150,
  "text": "done",
  "model": "cheap-model"
}

{
  "type": "final",
  "text": "lorem lorem lorem ... lorem done",
  "model_used": "cheap-model",
  "tokens_in": 30,
  "tokens_out": 150,
  "latency_ms": 5812.0,
  "cost_usd": 0.06,
  "quality_score": 0.842,
  "savings_pct": 97.0,
  "escalation_count": 0,
  "cluster_hint": "_default",
  "energy_kwh": 0.00012,
  "co2e_grams": 0.048,
  "tool_success": true,
  "format_ok": true,
  "safety_ok": true,
  "phase": "active"
}
```

**6. Observation Recording**
```python
observation = {
    "ts": 1700391234.567,
    "prompt_hash": "abc123def456",
    "cluster_hint": "_default",
    "model_plan": ["cheap-model", "mid-model", "premium-model"],
    "primary_model": "cheap-model",
    "escalated": false,
    "latency_s": 5.812,
    "tokens_in": 30,
    "tokens_out": 150,
    "cost_usd": 0.06,
    "quality_score": 0.842,
    "phase": "active",
    # All of the above are SYNTHETIC
}
_record_observation(observation)
```

**7. Shadow Evaluation (Optional)**
```python
# Generate fake shadow metrics for each shadow model
for shadow_model in shadow_models:
    sq = 0.842 + random.uniform(-0.02, 0.03)  # Fake quality
    sl = 5.812 * random.uniform(0.8, 1.1)      # Fake latency
    sc = 0.06 * random.uniform(0.7, 0.95)      # Fake cost
    _record_observation(shadow_obs)
```

**8. Lifecycle Evaluation**
```python
# Check if cheap-model should be promoted/demoted
# based on statistics collected from synthetic requests
evaluate_promotions(cluster_key, _MODEL_REGISTRY, stat_map_full, ...)
evaluate_demotions(cluster_key, _MODEL_REGISTRY, stat_map_full, ...)
```

**9. Session Cleanup**
```python
# Decrement active session counter
async with _SESSION_LOCK:
    session_data = _SESSION_ACTIVE.get(sess_id)
    if session_data["count"] <= 1:
        _SESSION_ACTIVE.pop(sess_id)
```

### 7.3 What Does NOT Happen

❌ No adapter is ever contacted
❌ No real LLM API is called (Anthropic, OpenAI, Ollama, etc.)
❌ No real token count is obtained
❌ No real cost is incurred
❌ Response text is not from any AI model
❌ Quality score is randomly generated
❌ Latency is simulated with asyncio.sleep()

---

## 8. ARCHITECTURE DISCONNECTS

### 8.1 Layered Architecture vs Reality

**Documented Architecture (Domain-Driven Design):**

```
┌──────────────────────────────────────────────────────┐
│ API Layer (routes/)                                  │
│ ├─ /v1/ask (router.py)                              │
│ └─ /v1/plan (router.py)                             │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│ Domain Layer (domain/)                               │
│ ├─ RoutingService (domain/routing/service.py)        │
│ ├─ ObservationService (domain/observation/service.py) │
│ └─ AdapterRegistry (domain/adapter/registry.py)      │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│ Application Layer (choose_model.py, adapters/)      │
│ ├─ choose() function                                │
│ ├─ Adapter implementations                          │
│ └─ Model selection algorithms                       │
└──────────────────────────────────────────────────────┘
```

**Actual Execution Path:**

```
┌──────────────────────────────────────────────────────┐
│ @app.post("/v1/ask")                                 │
│ (service.py:1119)                                    │
└────────────────┬───────────────────────────────────────┘
                 │
                 ├─→ choose() from choose_model.py
                 │   (Selects from HARDCODED catalog)
                 │
                 ├─→ adaptive_stats.py functions
                 │   (Bandit selection on fake models)
                 │
                 └─→ Generate synthetic response
                     (Yield "lorem" chunks)
                     │
                     ├─→ [NEVER CALLED] domain/ classes
                     ├─→ [NEVER CALLED] adapter integrations
                     └─→ [NEVER CALLED] real LLM APIs
```

**The Domain Layer is architecturally beautiful but completely unused.**

### 8.2 Service Container Never Used for Main Flow

```python
# Defined but unused:
_services = ServiceContainer()
_services.register("ack_tracker", lambda: AckTracker())
_services.register("quality_drift_detector", lambda: QualityDriftDetector(...))
_services.register("active_learning_sampler", lambda: ActiveLearningSampler())
_services.register("continuous_improvement_pipeline", lambda: ContinuousImprovementPipeline())

# In /v1/ask endpoint: these services are used for observability,
# but not for request handling
_services.get("quality_drift_detector").add_quality_observation(...)
_services.get("active_learning_sampler").enqueue_task(...)
```

---

## 9. TESTING IMPLICATIONS

### 9.1 Test Coverage Built on Synthetic Responses

```python
# Tests think they're testing real routing logic
# But they're testing routing of fake models with synthetic quality scores

def test_model_selection():
    plan = choose(quality="balanced", latency_slo_ms=2000, registry={}, safety="A")
    assert plan[0].name in ["cheap-model", "mid-model", "premium-model"]  # ✓ Passes
    # But this doesn't test routing to real AI models

def test_adaptive_routing():
    # Test bandit selection improves quality over time
    for _ in range(100):
        # Each "request" gets random.uniform(0.7, 0.9) quality
        # Of course stats improve - we're selecting winners from random data!
```

### 9.2 What Tests Actually Validate

✅ Model selection algorithm works correctly (on fake models)
✅ Bandit algorithm updates statistics correctly (from synthetic data)
✅ JSON serialization of responses works
✅ Rate limiting logic works
✅ Session management works
✅ PII scrubbing works

❌ No tests of real adapter calls
❌ No tests of integration with actual LLMs
❌ No tests of real cost tracking
❌ No tests of real quality metrics

---

## 10. PRODUCTION READINESS ASSESSMENT

### 10.1 What Works in Production

✅ Request routing logic (algorithmic)
✅ Rate limiting and backpressure
✅ Session management
✅ Metrics collection (on synthetic data)
✅ Policy enforcement (ABAC, OIDC)
✅ Database persistence
✅ Observability (tracing, logging, metrics)

### 10.2 What Doesn't Work in Production

❌ **Actual AI model responses** - No adapters are called
❌ **Real cost tracking** - Costs are calculated from hardcoded models
❌ **Real quality metrics** - Quality scores are randomized
❌ **Multi-model scenarios** - Only hardcoded fake models are available
❌ **Cost optimization** - Optimizes fake model costs
❌ **Quality improvement** - Stats are synthetic

### 10.3 To Make Production Ready

Would require:

1. **Implement adapter calls in /v1/ask** instead of synthetic response generation
2. **Select real model from adapter catalog** instead of hardcoded fake catalog
3. **Call adapter with prompt** to get real response
4. **Track real metrics** (cost, latency, quality from actual API calls)
5. **Update routing algorithm** to use real provider availability, pricing, capabilities
6. **Remove synthetic data generation** code

---

## 11. SUMMARY OF GAPS

### Critical Gaps (Production Blocking)

1. **No adapter invocation in main /v1/ask flow**
   - Generated synthetic "lorem" responses
   - Never calls real LLM APIs
   - Location: `service.py:1408-1429`

2. **Hardcoded fake model catalog**
   - Uses "cheap-model", "exp-model", "mid-model", "premium-model"
   - Not real LLM models
   - Location: `routing_constants.py:16-22`

3. **Stub adapters (5/7)**
   - Ollama, Google/Vertex, VLLM, LlamaCPP, Persona all return mock data
   - Never connect to real APIs
   - Locations: `adapters/python/*/server.py`

4. **Synthetic metrics**
   - Quality scores: random 0.7-0.9
   - Latency: simulated with asyncio.sleep()
   - Cost: calculated from fake pricing
   - Location: `service.py:1400-1450`

### Architectural Gaps

5. **Unused domain layer**
   - RoutingService never instantiated
   - ObservationService never used
   - AdapterRegistry never called
   - Location: `router_service/domain/`

6. **Dead code paths**
   - 229 Python files with many unused modules
   - Large unused modules (agp_update_handler, backup_system, etc.)
   - TODOs never completed

7. **Documentation/Implementation mismatch**
   - README claims "adaptive routing" (works on fake models)
   - Claims "cost optimization" (optimizes fake costs)
   - Claims "quality improvement" (stats are synthetic)

---

## RECOMMENDATIONS FOR IMPROVEMENT

### Immediate (High Priority)

1. **Add adapter integration to /v1/ask endpoint**
   - Call adapter.Stream() instead of generating synthetic responses
   - Collect real metrics (cost, latency, tokens)
   - Use real model responses

2. **Replace hardcoded model catalog**
   - Load models from adapter capabilities
   - Dynamic model selection from registered adapters
   - Real pricing and capabilities from providers

3. **Update documentation**
   - Document synthetic response generation in QUICK_START
   - Add section on adapter setup for real responses
   - Update README about what's production-ready

4. **Make stub adapters optional**
   - Don't use them by default in docker-compose
   - Require explicit Anthropic or OpenAI API key
   - Warn clearly when using stubs

### Medium Priority

5. **Decouple service.py into logical layers**
   - Extract response generation into separate module
   - Make adapter calling pluggable
   - Split 3000-line file into manageable pieces

6. **Implement the domain layer**
   - Actually use RoutingService
   - Actually use ObservationService
   - Actually use AdapterRegistry

7. **Complete stub adapters**
   - Implement Ollama adapter with real API calls
   - Implement Google/Vertex AI adapter
   - Implement VLLM adapter

---

## CONCLUSION

The ATP codebase is **architecturally sophisticated** with enterprise features like bandit selection, policy enforcement, carbon tracking, and multi-region support. However, it has a **critical execution gap**: the router generates synthetic "lorem" responses instead of calling real LLM adapters.

This is a **proof-of-concept system** that demonstrates intelligent routing logic, but requires adapter integration work before production use with real AI models. The good news is:

✅ Documentation has been improved to transparently explain these limitations
✅ Anthropic and OpenAI adapters are production-ready and exist
✅ The routing algorithms work correctly (even if on synthetic data)
✅ Architecture is clean and could support real adapter integration
✅ Test coverage is good (84%)

The codebase would benefit from clear documentation of the synthetic nature of responses and completion of adapter integration to bridge the gap between demonstrated concept and production capability.

