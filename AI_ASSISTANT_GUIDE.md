# AI Assistant Guide for ATP Platform

**Purpose**: This guide helps AI assistants (like Claude, GPT, etc.) provide accurate support to ATP users.

**Last Updated**: 2025-01-17

---

## 🚨 Critical Information for AI Assistants

### When Helping Users with ATP Setup

#### **CRITICAL GOTCHA #1: Stub Adapters**
- **Default docker-compose.yml uses STUB adapters** (ollama_adapter, persona_adapter)
- **These return MOCK/HARDCODED responses** - they do NOT call real AI models
- **NEVER tell users** "ATP is working" just because health checks pass
- **ALWAYS warn** that responses will be fake unless they configure real adapters

**Production-Ready Adapters** (only 2):
- ✅ **Anthropic** (`adapters/python/anthropic_adapter/`) - Requires `ANTHROPIC_API_KEY`
- ✅ **OpenAI** (`adapters/python/openai_adapter/`) - Requires `OPENAI_API_KEY`

**Stub Adapters** (5) - DO NOT USE IN PRODUCTION:
- ⚠️ Ollama - Returns: "This is a mock response from Ollama adapter..."
- ⚠️ Persona - Returns hardcoded mock data
- ⚠️ Google/Vertex AI - Returns mock data
- ⚠️ VLLM - Returns mock data
- ⚠️ LlamaCPP - Returns mock data

**Reference**: [ADAPTER_STATUS.md](ADAPTER_STATUS.md)

---

#### **CRITICAL GOTCHA #2: CLI Commands Partially Broken**
- **CLI exists and looks complete** but some commands will FAIL
- **Working**: `atpctl chat`, `atpctl system`, `atpctl config`, `atpctl policies`
- **BROKEN**: `atpctl providers *`, `atpctl cluster *` (CLI exists but router API endpoints missing)

**When user asks about CLI**:
1. Check [CLI_STATUS.md](tools/cli/CLI_STATUS.md) first
2. Warn about non-functional commands
3. Provide workarounds (docker-compose for scaling, env vars for providers)

**Reference**: [tools/cli/CLI_STATUS.md](tools/cli/CLI_STATUS.md)

---

#### **CRITICAL GOTCHA #3: Environment Variables**
- **Router WILL NOT START** without `ROUTER_ADMIN_API_KEY` set
- **Must be ≥32 characters** or router refuses to start
- **Default .env file** is now included (as of this update)
- **Quick setup**: `echo "ROUTER_ADMIN_API_KEY=dev-local-testing-key-12345678901234567890" >> .env`

**Reference**: [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)

---

#### **CRITICAL GOTCHA #4: Port Confusion**
- **Current default port**: 7443
- **Old documentation**: May reference 8000
- **Always use**: `http://localhost:7443` for router
- **Memory gateway**: `http://localhost:8080`

---

## 🎯 Quick Decision Tree for AI Assistants

### User Says: "Help me set up ATP"

```
1. Check if they want:
   a) Quick demo (5 min) → QUICK_START.md
   b) Full setup → GETTING_STARTED.md
   c) Production → PRODUCTION_DEPLOYMENT_GUIDE.md

2. ALWAYS warn about stub adapters upfront

3. Guide them to:
   - Verify .env exists with ROUTER_ADMIN_API_KEY
   - Run docker compose up -d
   - Wait 30 seconds
   - Run python scripts/validate_installation.py

4. If they want REAL AI responses:
   - Ask which provider (Anthropic or OpenAI)
   - Guide them to set API key in .env
   - Add adapter to docker-compose.yml
   - Restart services
```

### User Says: "ATP isn't working"

```
1. Check basics:
   - Are services running? → docker compose ps
   - Are health checks passing? → curl http://localhost:7443/healthz
   - Is .env configured? → grep ROUTER_ADMIN_API_KEY .env

2. Check logs:
   - docker compose logs router
   - docker compose logs memory-gateway

3. Common issues:
   - "Connection refused" → Services not started or still starting (wait 30s)
   - "404 Not Found" → Wrong endpoint or port
   - "Mock responses" → Using stub adapters (expected)
   - Router won't start → Missing ROUTER_ADMIN_API_KEY
```

### User Says: "How do I use the CLI?"

```
1. Check CLI_STATUS.md first
2. Guide working commands:
   - atpctl chat repl (works great)
   - atpctl system status (works)
   - atpctl config show (works)

3. Warn about broken commands:
   - atpctl providers * (CLI exists, API missing)
   - atpctl cluster * (CLI exists, API missing)

4. Provide workarounds:
   - Providers: Configure in .env or docker-compose.yml
   - Scaling: Use docker compose scale or kubectl scale
```

---

## 📚 Essential Files Reference

### For New Users
1. **QUICK_START.md** - 5-minute setup (start here)
2. **GETTING_STARTED.md** - Complete guide
3. **ADAPTER_STATUS.md** - Which adapters work vs stubs
4. **ENVIRONMENT_VARIABLES.md** - Configuration reference

### For Troubleshooting
1. **scripts/validate_installation.py** - Automated validation
2. **client/health_check.py** - Quick health check
3. **CLI_STATUS.md** - CLI command availability
4. **docker compose logs** - Service logs

### For Production
1. **PRODUCTION_DEPLOYMENT_GUIDE.md** - Production setup
2. **SECURITY.md** - Security considerations
3. **deploy/** directory - Deployment configs (K8s, Helm, Terraform)

---

## 🔍 Validation Checklist for AI Assistants

Before telling a user "ATP is working", verify:

- [ ] Services are running (`docker compose ps` shows all healthy)
- [ ] Health checks pass (`curl http://localhost:7443/healthz` returns OK)
- [ ] Memory gateway works (`curl http://localhost:8080/healthz` returns {"status": "ok"})
- [ ] **IMPORTANT**: User knows they're using stub adapters (if applicable)
- [ ] If user expects real AI: Production adapter is configured with valid API key

**NEVER** say "ATP is working correctly" based solely on health checks!

---

## 🎓 Understanding ATP Architecture (for AI Context)

### What is ATP?
- **NOT** an LLM itself
- **IS** a smart router/gateway that:
  - Routes requests to optimal LLM providers (OpenAI, Anthropic, etc.)
  - Optimizes for cost, quality, latency
  - Provides fallback and retry logic
  - Manages memory/context across requests

### Components:
```
User Request
    ↓
Router Service (port 7443)
    ↓
[Smart Selection Logic]
    ↓
Adapter (Anthropic/OpenAI/etc.)
    ↓
Real LLM Provider
    ↓
Response back to user
```

### Key Insight for AIs:
- ATP is middleware, not the AI model
- Default setup uses mock adapters for demo purposes
- Real value comes from connecting to actual LLM providers

---

## 🚀 Common User Journeys

### Journey 1: "I want to try ATP quickly"
```
1. git clone ...
2. cd atp-main
3. Verify .env exists with ROUTER_ADMIN_API_KEY
4. docker compose up -d
5. python scripts/validate_installation.py
6. ⚠️ Warn: Using stub adapters (mock responses)
7. Open Grafana at http://localhost:3000 (admin/admin)
```

### Journey 2: "I want real AI responses"
```
1. Complete Journey 1 first
2. Choose provider: Anthropic or OpenAI
3. Get API key from provider
4. Set in .env: ANTHROPIC_API_KEY=... or OPENAI_API_KEY=...
5. Add adapter to docker-compose.yml
6. docker compose up anthropic_adapter -d (or openai_adapter)
7. Update router config to use new adapter
8. Test with atpctl chat repl
```

### Journey 3: "I want to deploy to production"
```
1. Read PRODUCTION_DEPLOYMENT_GUIDE.md
2. Review ENVIRONMENT_VARIABLES.md for required settings
3. Set up secrets management
4. Configure ONLY production adapters (Anthropic/OpenAI)
5. Use Redis for state backend (ROUTER_STATE_BACKEND=redis)
6. Set up monitoring (Prometheus, Grafana)
7. Deploy with Helm or Terraform
8. Run python scripts/validate_installation.py --verbose
```

---

## ⚠️ Things AI Assistants Should NEVER Say

**DON'T SAY**:
- ❌ "ATP is working" (based only on health checks)
- ❌ "Your AI responses are ready" (if using stub adapters)
- ❌ "All CLI commands work" (providers/cluster commands broken)
- ❌ "Just run atpctl providers add..." (this will fail without warning)

**DO SAY**:
- ✅ "ATP services are healthy, but you're using stub adapters (mock responses)"
- ✅ "For real AI responses, configure Anthropic or OpenAI adapter"
- ✅ "Some CLI commands don't work yet - check CLI_STATUS.md"
- ✅ "Provider management needs to be done via docker-compose.yml currently"

---

## 🐛 Common Error Messages and Fixes

### "Connection refused" on port 7443
**Cause**: Router not started or still starting
**Fix**: Wait 30 seconds, check `docker compose ps`, check logs

### "404 Not Found" on API endpoints
**Cause**: Wrong port, wrong endpoint, or endpoint not implemented
**Fix**: Verify port 7443, check available endpoints in service.py

### Router won't start / crashes immediately
**Cause**: Missing ROUTER_ADMIN_API_KEY
**Fix**: Set in .env file (≥32 characters)

### "atpctl providers list" returns 404
**Cause**: Router API endpoints not implemented (known limitation)
**Fix**: Use docker-compose.yml for provider configuration instead

### Getting mock/hardcoded responses
**Cause**: Using stub adapters (ollama, persona)
**Fix**: Configure production adapter (Anthropic or OpenAI)

---

## 📊 Status Summary Table

| Component | Status | Notes |
|-----------|--------|-------|
| Router Service | ✅ Production | Core routing works |
| Memory Gateway | ✅ Production | KV store works |
| Anthropic Adapter | ✅ Production | Real API integration |
| OpenAI Adapter | ✅ Production | Real API integration |
| Ollama Adapter | ⚠️ Stub | Mock responses only |
| Other Adapters | ⚠️ Stub | Mock responses only |
| CLI: chat | ✅ Works | Full REPL |
| CLI: system | ✅ Works | Status, metrics, logs |
| CLI: config | ✅ Works | Config management |
| CLI: policies | ✅ Works | Policy management |
| CLI: providers | ❌ Broken | API endpoints missing |
| CLI: cluster | ❌ Broken | API endpoints missing |
| Grafana Dashboards | ✅ Works | Port 3000 |
| Prometheus Metrics | ✅ Works | Port 9090 |

---

## 🔄 Update Frequency

This guide should be updated when:
- New adapters become production-ready
- CLI commands are fixed/implemented
- Default ports or configurations change
- New critical gotchas are discovered
- Documentation structure changes

**Last verified**: 2025-01-17

---

## 📞 Getting Help

If AI assistant encounters issues not covered here:
1. Check [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for navigation
2. Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md) when it exists
3. Check recent commits/PRs for changes
4. Look at [CHANGELOG.md](CHANGELOG.md) for version-specific info

---

**Remember**: The goal is to help users succeed, not just get past health checks. Always set realistic expectations about adapter capabilities and CLI functionality.
