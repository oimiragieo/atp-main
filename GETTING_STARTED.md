# Getting Started with ATP Platform

**Complete step-by-step guide for new users**

> **⚡ In a hurry?** Check out the [Quick Start Guide](QUICK_START.md) to get running in 5 minutes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (5 minutes)](#quick-start-5-minutes)
3. [Installation Methods](#installation-methods)
4. [Verify Installation](#verify-installation)
5. [First Steps](#first-steps)
6. [Understanding the Architecture](#understanding-the-architecture)
7. [Common Use Cases](#common-use-cases)
8. [Troubleshooting](#troubleshooting)

## Related Documentation

- **[Quick Start](QUICK_START.md)** - Get ATP running in 5 minutes
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Complete configuration reference
- **[Production Deployment](PRODUCTION_DEPLOYMENT_GUIDE.md)** - Production setup guide
- **[CLI Status](tools/cli/CLI_STATUS.md)** - CLI command availability

---

## Prerequisites

### Required
- **Docker** 20.10+ and **Docker Compose** 2.0+
- **Git** (to clone the repository)

### Optional (for development)
- **Python** 3.11+ (for local development and CLI)
- **Rust** 1.70+ (for Rust router development)
- **Node.js** 18+ (for UI development)

### Check Prerequisites
```bash
# Check Docker
docker --version
docker compose version

# Check Python (optional)
python3 --version

# Check Git
git --version
```

---

## Quick Start (5 minutes)

The fastest way to get ATP running:

### 1. Clone the Repository
```bash
git clone <repository-url>
cd atp-main
```

### 2. Configure Required Environment Variables

**IMPORTANT**: Set `ROUTER_ADMIN_API_KEY` before starting:

```bash
# Copy environment template
cp .env.example .env

# Quick setup for local development
echo "ROUTER_ADMIN_API_KEY=dev-local-testing-key-12345678901234567890" >> .env
```

> **Note**: The router will NOT start without this key. See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for all configuration options.

### 3. Start Everything with Docker Compose
```bash
# Build and start all services
docker compose build
docker compose up -d
```

This starts:
- **Router Service** (port 7443)
- **Memory Gateway** (port 8080)
- **Redis** (port 6379)
- **Prometheus** (port 9090)
- **Grafana** (port 3000)
- **OPA** (port 8181)
- **OpenTelemetry Collector** (ports 4317, 4318)

### 4. Verify Services are Running
```bash
# Check all containers
docker compose ps

# Automated validation (recommended)
pip install requests  # Install dependency if needed
python scripts/validate_installation.py

# Or manual health checks
curl http://localhost:7443/healthz  # Router
curl http://localhost:8080/healthz  # Memory Gateway
```

### 5. Try Your First Memory Operation
```bash
# Install client dependencies if not already done
pip install -r client/requirements.txt
```
```bash
python client/memory_put_get.py
```

You should see output like:
```
PUT: 200 {'status': 'stored', 'key': 'session/s1'}
GET: 200 {'object': {'type': 'task.plan.v1', 'steps': ['analyze', 'generate', 'test']}}
SEARCH: 200 {'results': [...]}
```

**Congratulations!** 🎉 ATP is now running.

---

## Installation Methods

### Method 1: Docker Compose (Recommended)

**Best for:** Production deployment, quick evaluation

```bash
# Development mode (with logs)
docker compose up

# Production mode (background)
docker compose up -d

# Scale specific services
docker compose up -d --scale router=3

# Stop all services
docker compose down
```

**Environment Configuration:**
Create a `.env` file in the root directory:
```bash
cp .env.example .env
# Edit .env with your settings (REQUIRED: ROUTER_ADMIN_API_KEY)
```

**REQUIRED Variable**:
- `ROUTER_ADMIN_API_KEY` - Admin API key (minimum 32 characters)

See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for complete configuration reference.

---

### Method 2: Local Development Setup

**Best for:** Development, testing, debugging

#### Step 1: Install Dependencies
```bash
# Core dependencies
pip install -r requirements.txt

# Development dependencies (linting, testing)
pip install -r requirements-dev.txt
```

#### Step 2: Install the CLI
```bash
# Install atpctl globally
pip install -e tools/cli

# Verify installation
atpctl --help
```

#### Step 3: Start Services Individually
```bash
# Terminal 1: Start Redis
docker compose up redis -d

# Terminal 2: Start Memory Gateway
docker compose up memory-gateway -d

# Terminal 3: Start Router Service
cd router_service
python -m router_service.main

# Terminal 4: Use the CLI
atpctl status
```

---

### Method 3: Kubernetes Deployment

**Best for:** Production at scale

#### Option A: Raw Manifests
```bash
kubectl apply -f deploy/k8s/
kubectl get pods
kubectl get services
```

#### Option B: Kustomize
```bash
kubectl apply -k deploy/kustomize/
```

#### Option C: Helm
```bash
helm install atp deploy/helm/atp-router/ \
  --set router.replicas=3 \
  --set redis.enabled=true
```

See [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) for detailed production setup.

---

## Verify Installation

### Automated Validation (Recommended)
```bash
# Run comprehensive validation
python3 scripts/validate_installation.py

# Quick validation (skips health checks)
python3 scripts/validate_installation.py --quick

# Verbose output
python3 scripts/validate_installation.py --verbose
```

The validation script checks:
- Prerequisites (Docker, Python, Git)
- File structure completeness
- Docker services status
- Service health endpoints
- Python dependencies
- Documentation availability

### 1. Check Service Health
```bash
# All services
python client/health_check.py

# Individual checks
curl http://localhost:7443/healthz    # Router: should return "OK"
curl http://localhost:8080/healthz    # Memory Gateway: should return {"status": "ok"}
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health # Grafana
```

### 2. Check Metrics
```bash
# Router metrics
curl http://localhost:7443/metrics

# Should see metrics like:
# router_requests_total
# router_latency_seconds
# adapter_calls_total
```

### 3. Access Web UIs
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **OPA**: http://localhost:8181

---

## First Steps

### 1. Run Basic Memory Operations
```bash
# Store an object
curl -X PUT http://localhost:8080/v1/memory/tenant/acme/session/s1 \
  -H "Content-Type: application/json" \
  -d '{"object": {"message": "Hello ATP!"}}'

# Retrieve it
curl http://localhost:8080/v1/memory/tenant/acme/session/s1

# Search
curl -X POST http://localhost:8080/v1/memory/search \
  -H "Content-Type: application/json" \
  -d '{"q": "Hello"}'
```

### 2. Use the Interactive CLI
```bash
# Install CLI if not already done
pip install -e tools/cli

# Start interactive chat
atpctl chat repl

# In the REPL:
You: Hello! What can you help me with?
Assistant: [Response from AI]

# Try commands
/help    # Show available commands
/save    # Save conversation
/export  # Export to markdown
/exit    # Exit REPL
```

### 3. Monitor Your System
```bash
# View system status
atpctl system status

# View metrics
atpctl system metrics

# Stream logs
atpctl system logs --follow
```

### 4. Configure Providers
```bash
# Add OpenAI provider
atpctl providers add openai --api-key YOUR_OPENAI_KEY

# Add Anthropic provider
atpctl providers add anthropic --api-key YOUR_ANTHROPIC_KEY

# List all providers
atpctl providers list
```

---

## Understanding the Architecture

### Component Overview

```
┌─────────────────┐
│   Nginx Proxy   │ :7443 (external)
└────────┬────────┘
         │
┌────────▼────────┐
│  Router Service │ :7443 (internal)
│  - Fair Scheduler
│  - Cost Optimizer
│  - Bandit Selection
└────┬─────┬──────┘
     │     │
     │     └──────────────┐
     │                    │
┌────▼────────┐    ┌──────▼─────────┐
│  Adapters   │    │ Memory Gateway │ :8080
│  - OpenAI   │    │  - KV Store    │
│  - Anthropic│    │  - PII Redact  │
│  - Ollama   │    │  - Search      │
└─────────────┘    └────────────────┘
     │                    │
     └─────────┬──────────┘
               │
        ┌──────▼──────┐
        │    Redis    │ :6379
        │  (State)    │
        └─────────────┘
```

### Data Flow

1. **Client** sends request to Router (port 7443)
2. **Router** uses Fair Scheduler to manage request
3. **Bandit Algorithm** selects optimal model/adapter
4. **Adapter** calls actual LLM provider (OpenAI, Anthropic, etc.)
5. **Response** streamed back to client
6. **Metrics** recorded in Prometheus
7. **State** saved in Redis
8. **Context** stored in Memory Gateway

---

## Common Use Cases

### Use Case 1: Quick AI Chat
```bash
# Start interactive chat
atpctl chat repl

# Ask questions, get responses
# Auto-saves conversation history
```

### Use Case 2: Cost-Optimized Inference
```python
import requests

response = requests.post("http://localhost:7443/v1/ask", json={
    "prompt": "Explain quantum computing",
    "quality_target": "balanced",  # fast, balanced, or high
    "max_cost_usd": 0.05,          # Budget limit
    "latency_slo_ms": 2000         # Max latency
})

# Router automatically selects cheapest adapter meeting requirements
```

### Use Case 3: Multi-Provider Fallback
```bash
# Configure multiple providers
atpctl providers add openai --api-key $OPENAI_KEY --priority 1
atpctl providers add anthropic --api-key $ANTHROPIC_KEY --priority 2

# Router automatically tries fallback if primary fails
```

### Use Case 4: Memory/Context Management
```bash
# Store task context
python client/memory_put_get.py

# Context persists across requests
# Accessible to all adapters
```

---

## Troubleshooting

### Services Won't Start

**Problem:** `docker compose up` fails

**Solutions:**
```bash
# Check if ports are already in use
sudo lsof -i :7443
sudo lsof -i :8080

# Clean up and restart
docker compose down
docker compose up --force-recreate
```

---

### Health Checks Fail

**Problem:** `curl http://localhost:7443/healthz` returns error

**Solutions:**
```bash
# Check container logs
docker compose logs router
docker compose logs memory-gateway

# Verify containers are running
docker compose ps

# Restart specific service
docker compose restart router
```

---

### CLI Dependencies Missing

**Problem:** `atpctl` command not found or import errors

**Solutions:**
```bash
# Install CLI dependencies
pip install typer rich prompt-toolkit pyyaml httpx

# Or install from requirements
pip install -r requirements.txt

# Install CLI globally
pip install -e tools/cli
```

---

### Connection Refused Errors

**Problem:** `Connection refused` when calling APIs

**Solutions:**
```bash
# Check if services are running
docker compose ps

# Check if reverse proxy is up
docker compose logs reverse-proxy

# Try direct connection (bypassing proxy)
curl http://localhost:7443/healthz  # Direct to router
```

---

### Memory Gateway Issues

**Problem:** Memory operations fail

**Solutions:**
```bash
# Check memory gateway logs
docker compose logs memory-gateway

# Verify endpoint
curl http://localhost:8080/healthz

# Test with simple PUT
curl -X PUT http://localhost:8080/v1/memory/test/key \
  -H "Content-Type: application/json" \
  -d '{"object": {"test": "value"}}'
```

---

## Next Steps

Now that ATP is running:

1. **Read the Docs**: Check [docs/01_ATP.md](docs/01_ATP.md) for architecture details
2. **Try Examples**: Explore [examples/](examples/) directory
3. **Configure Adapters**: See [adapters/](adapters/) for adapter setup
4. **Production Deploy**: Read [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)
5. **Develop**: See [CONTRIBUTING.md](CONTRIBUTING.md) for development guide

---

## Quick Reference

### Essential Commands

```bash
# Start everything
docker compose up -d

# Stop everything
docker compose down

# View logs
docker compose logs -f

# Health check
python client/health_check.py

# CLI
atpctl chat repl
atpctl system status
atpctl providers list

# Scale
docker compose up -d --scale router=3
```

### Important URLs

- Router: http://localhost:7443
- Memory Gateway: http://localhost:8080
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090
- Router Metrics: http://localhost:7443/metrics

### Key Files

- `docker-compose.yml` - Service definitions
- `.env.example` - Environment variable template
- `requirements.txt` - Python dependencies
- `CONTRIBUTING.md` - Development guide
- `README.md` - Project overview

---

## Getting Help

- **Documentation**: [docs/](docs/) directory
- **Examples**: [examples/](examples/) directory
- **Issues**: Check GitHub issues
- **CLI Help**: `atpctl --help`
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

---

**Welcome to ATP!** 🚀 You're now ready to build scalable, cost-optimized AI applications.
