# AI Assistant Rules for ATP Platform

## Primary Directive

**Help users succeed** - Don't just get past health checks, ensure users understand what's working and what's not.

## Critical Information to Always Remember

### 1. Default Adapters are STUBS
- **Default docker-compose.yml uses STUB adapters** (ollama, persona)
- **These return MOCK/HARDCODED responses** - NOT real AI
- **NEVER tell users** "ATP is working" based only on health checks
- **ALWAYS warn** that responses will be fake unless they configure real adapters

**Production-Ready Adapters (only 2):**
- ✅ Anthropic (`ANTHROPIC_API_KEY` required)
- ✅ OpenAI (`OPENAI_API_KEY` required)

### 2. Router Requires ROUTER_ADMIN_API_KEY
- **Router will NOT start** without `ROUTER_ADMIN_API_KEY` in `.env`
- **Must be ≥32 characters**
- Quick fix: `cp .env.example .env` and edit

### 3. Default Port is 7443 (not 8000)
- Router: http://localhost:7443
- Memory Gateway: http://localhost:8080

### 4. Some CLI Commands Don't Work
- **Working**: `atpctl chat`, `atpctl system`, `atpctl config`, `atpctl policies`
- **Broken**: `atpctl providers`, `atpctl cluster` (CLI exists but API endpoints missing)
- **Always check**: `tools/cli/CLI_STATUS.md` before suggesting CLI commands

## Decision Trees

### User Asks: "Help me set up ATP"

```
1. Ask what they want:
   a) Quick demo → Guide to QUICK_START.md
   b) Full setup → Guide to GETTING_STARTED.md
   c) Production → Guide to PRODUCTION_DEPLOYMENT_GUIDE.md

2. Warn about stub adapters UPFRONT

3. Guide through:
   - Verify .env exists with ROUTER_ADMIN_API_KEY
   - Run: docker compose up -d
   - Wait 30 seconds
   - Run: python scripts/validate_installation.py

4. If they want REAL AI responses:
   - Ask: Anthropic or OpenAI?
   - Guide: Set API key in .env
   - Update: docker-compose.yml to include real adapter
   - Restart: docker compose up {adapter} -d
```

### User Says: "ATP isn't working"

```
1. Check basics:
   - Services running? → docker compose ps
   - Health checks passing? → curl http://localhost:7443/healthz
   - .env configured? → grep ROUTER_ADMIN_API_KEY .env

2. Check logs:
   - docker compose logs router
   - docker compose logs memory-gateway

3. Common issues:
   - "Connection refused" → Wait 30s, services still starting
   - "404 Not Found" → Wrong endpoint or port
   - "Mock responses" → Using stub adapters (expected behavior)
   - "Router won't start" → Missing ROUTER_ADMIN_API_KEY
```

### User Asks: "How do I use the CLI?"

```
1. Check CLI_STATUS.md first

2. Guide working commands:
   - atpctl chat repl (interactive REPL)
   - atpctl system status (health checks)
   - atpctl config show (configuration)

3. Warn about broken commands:
   - atpctl providers * → API endpoints not implemented
   - atpctl cluster * → API endpoints not implemented

4. Provide workarounds:
   - Provider config: Use .env or docker-compose.yml
   - Scaling: Use docker compose scale or kubectl scale
```

## Validation Checklist

**Before telling user "ATP is working", verify:**

- [ ] Services running (`docker compose ps` shows healthy)
- [ ] Health checks pass (7443/healthz and 8080/healthz return OK)
- [ ] User knows they're using stub adapters (if applicable)
- [ ] If expecting real AI: Production adapter configured with valid API key
- [ ] Metrics accessible (http://localhost:7443/metrics)

**NEVER say "ATP is working correctly" based solely on health checks passing!**

## What NOT to Say

### ❌ Don't Say
- "ATP is working" (based only on health checks)
- "Your AI responses are ready" (if using stub adapters)
- "All CLI commands work" (providers/cluster broken)
- "Just run atpctl providers add..." (will fail)
- "Install via npm" (this is a Python project)
- "The default port is 8000" (it's 7443)

### ✅ Do Say
- "ATP services are healthy, but you're using stub adapters (mock responses)"
- "For real AI responses, configure Anthropic or OpenAI adapter"
- "Some CLI commands don't work yet - check CLI_STATUS.md"
- "Provider management needs to be done via docker-compose.yml currently"
- "This is a Python project - use pip for dependencies"
- "The router is on port 7443"

## File Reference Guide

### Quick Reference (5 seconds)
- `QUICK_START.md` - 5-minute setup
- `AI_ASSISTANT_GUIDE.md` - Your comprehensive guide
- `ADAPTER_STATUS.md` - Which adapters work

### Full Guides (5 minutes)
- `GETTING_STARTED.md` - Complete onboarding
- `ENVIRONMENT_VARIABLES.md` - All configuration
- `TROUBLESHOOTING.md` - Common issues

### Technical Deep Dives (30+ minutes)
- `docs/01_ATP.md` - Protocol specification
- `DEEP_DIVE_REVIEW.md` - Architecture analysis
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - Production setup

### Development
- `claude.md` - This project's Claude guide (you're here)
- `.claude/rules/development.md` - Development standards
- `CONTRIBUTING.md` - Contribution guidelines
- `pyproject.toml` - Python project config

## Common Error Messages and Responses

### "Connection refused" on port 7443
**Your Response:**
```
This usually means the router is still starting up.

Try:
1. Wait 30 seconds
2. Check: docker compose ps
3. Check logs: docker compose logs router

If still failing, check that ROUTER_ADMIN_API_KEY is set in .env
```

### "404 Not Found" on API endpoints
**Your Response:**
```
This could be:
1. Wrong port (should be 7443, not 8000)
2. Endpoint not implemented (check CLI_STATUS.md for broken commands)
3. Service not started

Verify URL: http://localhost:7443/healthz should work
```

### Router crashes on startup
**Your Response:**
```
Most common cause: Missing ROUTER_ADMIN_API_KEY

Fix:
1. cp .env.example .env
2. Edit .env and set ROUTER_ADMIN_API_KEY (≥32 characters)
3. docker compose restart router

Example:
ROUTER_ADMIN_API_KEY=dev-local-testing-key-12345678901234567890
```

### Getting mock/hardcoded responses
**Your Response:**
```
This is expected! Default adapters are stubs (return mock data).

For real AI responses, configure a production adapter:

Option 1: Anthropic (Claude)
1. Get API key from https://console.anthropic.com
2. Add to .env: ANTHROPIC_API_KEY=your-key-here
3. docker compose up anthropic_adapter -d

Option 2: OpenAI (GPT)
1. Get API key from https://platform.openai.com
2. Add to .env: OPENAI_API_KEY=your-key-here
3. docker compose up openai_adapter -d

See ADAPTER_STATUS.md for details.
```

## Code Guidance

### When Helping with Code

1. **Check existing patterns** before suggesting new code
   - Look at `router_service/service.py` for endpoint patterns
   - Look at `router_service/models.py` for data model patterns
   - Look at tests for testing patterns

2. **Follow project standards**
   - Use StructuredLogger, not print()
   - Use error_response(), not HTTPException
   - Use settings object, not direct os.getenv()
   - Add type hints
   - Write tests

3. **Security first**
   - Never hardcode secrets
   - Always validate input
   - Use parameterized queries
   - Check for injection vulnerabilities

### Suggesting New Features

**Before suggesting code**, check:
1. Does similar functionality exist? → Reuse it
2. Is this in project scope? → Check docs
3. Are there security implications? → Flag them
4. Will this break existing features? → Test carefully

## Helping with Debugging

### Information to Gather

1. **What are they trying to do?**
   - Quick demo, development, or production?

2. **What's the actual error?**
   - Full error message
   - Logs: `docker compose logs router`
   - Health checks: `curl http://localhost:7443/healthz`

3. **Environment details**
   - Is .env configured?
   - Which adapters are running?
   - What's in docker compose ps?

### Debugging Workflow

```
1. Verify basics
   - Services running?
   - .env configured?
   - Ports accessible?

2. Check logs
   - docker compose logs router
   - docker compose logs memory-gateway

3. Test components
   - python scripts/validate_installation.py
   - python client/health_check.py

4. Isolate issue
   - Is it router? adapter? network?
   - Can you curl the endpoint directly?
   - Are there errors in logs?

5. Provide solution
   - Specific fix
   - Link to relevant docs
   - Explain why it happened
```

## Advanced Topics

### When User Asks About Architecture

Reference these docs in order:
1. `claude.md` - Quick overview
2. `docs/01_ATP.md` - ATP protocol spec
3. `docs/04_AGP_Federation_Spec.md` - Federation details
4. `DEEP_DIVE_REVIEW.md` - Comprehensive analysis

### When User Asks About Production

Guide them through:
1. Read `PRODUCTION_DEPLOYMENT_GUIDE.md` thoroughly
2. Review `ENVIRONMENT_VARIABLES.md` for required config
3. Set up secrets management (never commit .env)
4. Configure ONLY production adapters (Anthropic/OpenAI)
5. Use Redis for state backend
6. Set up monitoring (Prometheus, Grafana)
7. Use Helm/Terraform for deployment
8. Run validation: `python scripts/validate_installation.py --verbose`

### When User Asks About Testing

```
Testing is well-established:
- Framework: pytest
- Coverage: 84% minimum (enforced)
- Run: make test or pytest -v
- Coverage report: make coverage

Test locations:
- tests/ - Unit and integration tests
- tests/conftest.py - Pytest fixtures
- 2,079+ tests currently

See pyproject.toml for pytest configuration.
```

## Status Summary Table (Keep This Current)

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

## Remember

Your goal is to **help users succeed**, not just get systems running. Set realistic expectations, warn about limitations, and guide users to the right documentation. Be honest about what works and what doesn't.

**When in doubt**: Check AI_ASSISTANT_GUIDE.md, ADAPTER_STATUS.md, and CLI_STATUS.md

---

**Last Updated**: 2025-11-17
**Keep this file synchronized with**: AI_ASSISTANT_GUIDE.md, ADAPTER_STATUS.md, CLI_STATUS.md
