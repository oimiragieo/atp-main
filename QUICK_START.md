# ATP Quick Start Guide

**Get ATP running in 5 minutes**

---

## Prerequisites

- Docker and Docker Compose installed
- Git installed
- 8GB RAM minimum

---

## 1. Clone Repository

```bash
git clone <repository-url>
cd atp-main
```

---

## 2. Set Required Environment Variables

Create a `.env` file:

```bash
# Copy template
cp .env.example .env

# Edit .env and set REQUIRED variables:
# ROUTER_ADMIN_API_KEY=your-secure-admin-key-minimum-32-characters-long
```

**IMPORTANT**: The router **will not start** without `ROUTER_ADMIN_API_KEY`.

Quick setup for local development:
```bash
echo "ROUTER_ADMIN_API_KEY=dev-local-testing-key-12345678901234567890" >> .env
```

---

## 3. Start Services

```bash
docker compose build
docker compose up -d
```

Wait 30 seconds for all services to start.

> **🚨 CRITICAL: Router Currently in DEMONSTRATION MODE**
>
> **The router generates synthetic "lorem" responses for testing/development purposes.**
>
> **What this means:**
> - ✅ Routing algorithms work correctly (bandit selection, cost optimization)
> - ✅ Health checks pass, services are functional
> - ✅ Metrics and observability are operational
> - ⚠️ **API responses are placeholder text ("lorem"), NOT real AI completions**
> - ⚠️ **No adapters are called** - even production-ready Anthropic/OpenAI adapters
>
> **Current Status:**
> - Router selects from 4 hardcoded fake models (`service.py:1408-1449`)
> - Quality scores are random: `random.uniform(0.7, 0.9)`
> - Costs calculated from fake model pricing
> - Adapters exist but not integrated into main routing flow
>
> **Use Cases:**
> - ✅ Testing routing algorithms and cost optimization
> - ✅ Development and observability testing
> - ❌ **NOT for production LLM request routing**
>
> **Production Adapters Available (Not Connected):**
> - Anthropic (Claude) - `/adapters/python/anthropic_adapter/` (production-ready)
> - OpenAI (GPT) - `/adapters/python/openai_adapter/` (production-ready)
> - 5 other adapters - Stub implementations
>
> **Next Steps:** See [CODEBASE_AUDIT_REPORT.md](CODEBASE_AUDIT_REPORT.md) for adapter integration roadmap.
>
> **Technical Details:** See [ATP_EXECUTION_FLOW_ANALYSIS.md](ATP_EXECUTION_FLOW_ANALYSIS.md) for complete execution flow analysis.

---

## 4. Verify Installation

### Option A: Automated Validation (Recommended)
```bash
pip install requests  # Install dependency if needed
python scripts/validate_installation.py
```

### Option B: Manual Checks
```bash
# Check router health
curl http://localhost:7443/healthz
# Should return: OK

# Check memory gateway health
curl http://localhost:8080/healthz
# Should return: {"status": "ok"}
```

---

## 5. Run Your First Request

### Test Memory Operations
```bash
pip install requests  # Install dependency if needed
python client/memory_put_get.py
```

You should see:
```
PUT: 200 {'status': 'stored', 'key': 'session/s1'}
GET: 200 {'object': {'type': 'task.plan.v1', 'steps': ['analyze', 'generate', 'test']}}
SEARCH: 200 {'results': [...]}
```

---

## 6. Access Monitoring Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Router Metrics**: http://localhost:7443/metrics

---

## What's Running?

| Service | Port | Purpose |
|---------|------|---------|
| Router Service | 7443 | Main ATP router |
| Memory Gateway | 8080 | Memory/state storage |
| Redis | 6379 | State backend |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Visualization |
| OPA | 8181 | Policy engine |

---

## Common Issues

### "Connection refused" on port 7443
**Solution**: Wait 30 seconds for services to fully start
```bash
docker compose logs router
```

### Router won't start
**Solution**: Check if `ROUTER_ADMIN_API_KEY` is set in `.env`
```bash
grep ROUTER_ADMIN_API_KEY .env
```

### "Module not found" errors
**Solution**: Install Python dependencies
```bash
pip install -r client/requirements.txt
```

---

## Next Steps

1. **Read the Full Guide**: [GETTING_STARTED.md](GETTING_STARTED.md)
2. **Configure Adapters**: [ADAPTER_STATUS.md](ADAPTER_STATUS.md)
3. **Environment Variables**: [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
4. **Production Deployment**: [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

---

## Stop Services

```bash
docker compose down
```

To remove all data:
```bash
docker compose down -v
```

---

## Getting Help

- Check logs: `docker compose logs -f`
- Health checks: `python scripts/validate_installation.py --verbose`
- Documentation: [docs/](docs/)
