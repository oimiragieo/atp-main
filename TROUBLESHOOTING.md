# ATP Troubleshooting Guide

**Comprehensive troubleshooting guide for common ATP platform issues**

Last Updated: 2025-01-17

---

## Table of Contents

1. [Quick Diagnosis](#quick-diagnosis)
2. [Installation Issues](#installation-issues)
3. [Service Startup Issues](#service-startup-issues)
4. [Adapter Issues](#adapter-issues)
5. [CLI Issues](#cli-issues)
6. [Network & Connectivity Issues](#network--connectivity-issues)
7. [Performance Issues](#performance-issues)
8. [Data & State Issues](#data--state-issues)
9. [Getting Help](#getting-help)

---

## Quick Diagnosis

### Run These First

```bash
# 1. Check all services
docker compose ps

# 2. Automated validation
python scripts/validate_installation.py --verbose

# 3. Check router health
curl http://localhost:7443/healthz

# 4. Check memory gateway health
curl http://localhost:8080/healthz

# 5. Check logs
docker compose logs --tail=50
```

### Health Check Expected Responses

**Router** (`http://localhost:7443/healthz`):
```
OK
```

**Memory Gateway** (`http://localhost:8080/healthz`):
```json
{"status": "ok"}
```

---

## Installation Issues

### Issue: "docker compose command not found"

**Cause**: Docker Compose not installed or using old Docker version

**Fix**:
```bash
# Check Docker version (need 20.10+)
docker --version

# Check Docker Compose (need 2.0+)
docker compose version

# If using old docker-compose (v1), upgrade Docker Desktop
# Or install docker-compose-plugin
```

---

### Issue: "No .env file found"

**Cause**: Missing .env file (should exist as of 2025-01-17)

**Fix**:
```bash
# .env file should already exist in repo root
# If missing, copy from template:
cp .env.example .env

# Verify it has ROUTER_ADMIN_API_KEY
grep ROUTER_ADMIN_API_KEY .env
```

---

### Issue: "Permission denied" when running scripts

**Cause**: Script not executable or permission issues

**Fix**:
```bash
# Make scripts executable
chmod +x scripts/*.py
chmod +x client/*.py

# Or run with python explicitly
python scripts/validate_installation.py
python client/health_check.py
```

---

## Service Startup Issues

### Issue: Router won't start / exits immediately

**Symptoms**:
```bash
docker compose logs router
# Shows: "ROUTER_ADMIN_API_KEY must be set and at least 32 characters"
```

**Cause**: Missing or invalid `ROUTER_ADMIN_API_KEY`

**Fix**:
```bash
# Check .env file
grep ROUTER_ADMIN_API_KEY .env

# If missing or too short, set it:
echo "ROUTER_ADMIN_API_KEY=dev-local-testing-key-12345678901234567890" >> .env

# Restart services
docker compose restart router
```

**Reference**: Line 36 in [QUICK_START.md](QUICK_START.md)

---

### Issue: "Port already in use" errors

**Symptoms**:
```bash
docker compose up
# Error: bind: address already in use
```

**Cause**: Another service using required ports (7443, 8080, 6379, 9090, 3000)

**Fix**:
```bash
# Find what's using the port
sudo lsof -i :7443
sudo lsof -i :8080

# Option 1: Stop the conflicting service
sudo systemctl stop <service-name>

# Option 2: Change ATP ports in docker-compose.yml
# Edit ports section, e.g., "8443:7443" instead of "7443:7443"

# Restart
docker compose down
docker compose up -d
```

---

### Issue: Services stuck in "starting" state

**Symptoms**:
```bash
docker compose ps
# Shows: "starting" for 5+ minutes
```

**Cause**: Dependency not healthy, network issues, or resource constraints

**Fix**:
```bash
# Check logs for specific service
docker compose logs router
docker compose logs memory-gateway

# Check resource usage
docker stats

# Common fix: Restart with force recreate
docker compose down
docker compose up -d --force-recreate

# If still stuck, check Docker daemon
sudo systemctl restart docker
```

---

### Issue: "Unhealthy" status for services

**Symptoms**:
```bash
docker compose ps
# Shows: "unhealthy" status
```

**Cause**: Health check failing

**Fix**:
```bash
# Check health check details
docker inspect <container-name> | grep -A 20 Health

# Check logs
docker compose logs <service-name>

# Common causes:
# 1. Service not fully started → Wait 30 more seconds
# 2. Dependency not available → Check Redis, OPA, etc.
# 3. Configuration error → Check .env and logs

# Force restart
docker compose restart <service-name>
```

---

## Adapter Issues

### Issue: Getting mock/hardcoded responses

**Symptoms**:
```
Response: "This is a mock response from Ollama adapter..."
```

**Cause**: Using stub adapters (expected behavior)

**This is NOT a bug** - Default docker-compose.yml uses stub adapters for demo purposes.

**Fix** (for real AI responses):
```bash
# Option A: Use Anthropic (Claude)
echo "ANTHROPIC_API_KEY=your_key_here" >> .env

# Add to docker-compose.yml:
# anthropic_adapter:
#   build: ./adapters/python/anthropic_adapter
#   environment:
#     - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
#   ports: ["7073:7070"]

docker compose up anthropic_adapter -d

# Option B: Use OpenAI (GPT)
echo "OPENAI_API_KEY=your_key_here" >> .env

# Add to docker-compose.yml:
# openai_adapter:
#   build: ./adapters/python/openai_adapter
#   environment:
#     - OPENAI_API_KEY=${OPENAI_API_KEY}
#   ports: ["7074:7070"]

docker compose up openai_adapter -d
```

**Reference**: [ADAPTER_STATUS.md](ADAPTER_STATUS.md)

---

### Issue: Adapter returns 401 Unauthorized

**Symptoms**:
```
Error: API authentication failed
```

**Cause**: Invalid or missing API key

**Fix**:
```bash
# Check API key is set
grep ANTHROPIC_API_KEY .env
grep OPENAI_API_KEY .env

# Verify key is valid
# Anthropic: https://console.anthropic.com/
# OpenAI: https://platform.openai.com/

# Update .env and restart
docker compose restart anthropic_adapter
docker compose restart openai_adapter
```

---

### Issue: Adapter not registered with router

**Symptoms**:
```
Error: No adapters available
```

**Cause**: Router not configured to use adapter

**Fix**:
```bash
# Check router environment in docker-compose.yml
# Should have ADAPTER_ENDPOINTS pointing to adapter

# Example:
environment:
  - ADAPTER_ENDPOINTS=["http://anthropic_adapter:7070","http://openai_adapter:7070"]

# Restart router
docker compose restart router
```

---

## CLI Issues

### Issue: "atpctl: command not found"

**Cause**: CLI not installed

**Fix**:
```bash
# Install CLI
cd tools/cli
pip install -e .

# Verify
atpctl --version

# If still not found, check PATH
which atpctl
echo $PATH
```

---

### Issue: "atpctl providers list" returns 404

**Cause**: Router API endpoints not implemented (known limitation)

**This is NOT a bug** - These endpoints are not yet implemented in the router.

**Fix** (workaround):
```bash
# Provider management is done via docker-compose.yml
# See ADAPTER_ENDPOINTS environment variable

# For scaling:
docker compose up -d --scale router=3

# NOT via atpctl cluster scale 3
```

**Reference**: [tools/cli/CLI_STATUS.md](tools/cli/CLI_STATUS.md)

---

### Issue: CLI connection errors

**Symptoms**:
```
Error: Connection refused to http://localhost:7443
```

**Cause**: Router not running or wrong URL

**Fix**:
```bash
# Check router is running
docker compose ps router

# Check router health
curl http://localhost:7443/healthz

# Set correct API URL
export ATP_API_URL="http://localhost:7443"

# Try CLI again
atpctl system status
```

---

## Network & Connectivity Issues

### Issue: "Connection refused" on port 7443

**Cause**: Services not started, still starting, or reverse proxy issue

**Fix**:
```bash
# 1. Check if services are running
docker compose ps

# 2. Wait for services to be healthy (can take 30-60 seconds)
watch docker compose ps

# 3. Check reverse proxy (nginx)
docker compose logs reverse-proxy

# 4. Try direct connection to router (bypassing proxy)
docker exec -it <router-container> curl http://localhost:7443/healthz

# 5. Check if port is actually listening
sudo netstat -tlnp | grep 7443
```

---

### Issue: "Timeout" when calling APIs

**Cause**: Service overloaded, network issues, or slow startup

**Fix**:
```bash
# Check resource usage
docker stats

# Check for errors in logs
docker compose logs --tail=100

# Increase timeout in client
# Edit client scripts to use longer timeout:
timeout = 30  # instead of default 3-5

# Check network connectivity
docker network inspect atp-network
```

---

### Issue: Services can't communicate with each other

**Symptoms**:
```
Error: Cannot connect to redis:6379
Error: Cannot reach memory-gateway:8080
```

**Cause**: Docker network issues

**Fix**:
```bash
# Recreate network
docker compose down
docker network rm atp-network
docker compose up -d

# Check network
docker network inspect atp-network

# Verify DNS resolution inside container
docker exec -it <container> ping redis
docker exec -it <container> ping memory-gateway
```

---

## Performance Issues

### Issue: Slow responses / High latency

**Cause**: Resource constraints, network issues, or upstream provider slow

**Diagnosis**:
```bash
# Check CPU/Memory usage
docker stats

# Check metrics
curl http://localhost:7443/metrics | grep latency

# Check Grafana dashboards
# Open http://localhost:3000 (admin/admin)

# Check adapter logs
docker compose logs anthropic_adapter
docker compose logs openai_adapter
```

**Fix**:
```bash
# Increase resources in Docker Desktop settings
# Recommended: 4+ CPU cores, 8+ GB RAM

# Scale router if needed
docker compose up -d --scale router=3

# Check upstream provider status
# Anthropic: https://status.anthropic.com/
# OpenAI: https://status.openai.com/
```

---

### Issue: High memory usage

**Cause**: Memory leaks, large state, or insufficient cleanup

**Diagnosis**:
```bash
# Check memory usage per container
docker stats

# Check router state backend
# If using Redis, check memory usage:
docker exec -it <redis-container> redis-cli INFO memory

# Check for growing log files
du -sh /var/lib/docker/containers/*
```

**Fix**:
```bash
# Restart services to free memory
docker compose restart

# Use Redis for state instead of in-memory
# In .env:
echo "ROUTER_STATE_BACKEND=redis" >> .env

# Limit Redis memory in docker-compose.yml:
redis:
  command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

# Clean up old logs
docker system prune -a
```

---

## Data & State Issues

### Issue: Lost session state / Memory not persisting

**Cause**: Using in-memory backend without persistence, or Redis not configured

**Fix**:
```bash
# Use Redis backend for persistence
echo "ROUTER_STATE_BACKEND=redis" >> .env
echo "ROUTER_REDIS_URL=redis://redis:6379/0" >> .env

# Ensure Redis has volume for persistence
# In docker-compose.yml:
redis:
  volumes:
    - redis_data:/data

# Restart router
docker compose restart router
```

**Reference**: [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) Line 85-98

---

### Issue: Redis connection errors

**Symptoms**:
```
Error: Cannot connect to Redis at redis://redis:6379/0
```

**Cause**: Redis not running or network issue

**Fix**:
```bash
# Check Redis is running
docker compose ps redis

# Check Redis logs
docker compose logs redis

# Test Redis connection
docker exec -it <redis-container> redis-cli ping
# Should return: PONG

# Restart Redis
docker compose restart redis

# Check Redis URL in .env
grep ROUTER_REDIS_URL .env
```

---

## Validation & Testing

### Issue: validate_installation.py fails

**Symptoms**:
```python
python scripts/validate_installation.py
# Returns errors
```

**Common Causes & Fixes**:

**Missing requests module**:
```bash
pip install requests
```

**Services not running**:
```bash
docker compose up -d
# Wait 30 seconds
python scripts/validate_installation.py
```

**Health checks failing**:
```bash
# Check logs for specific service
docker compose logs <failing-service>

# Common fixes:
docker compose restart <failing-service>
docker compose up -d --force-recreate
```

---

## Getting Help

### Self-Service Checklist

Before asking for help, try:

1. ✅ Run `python scripts/validate_installation.py --verbose`
2. ✅ Check logs: `docker compose logs --tail=100`
3. ✅ Restart services: `docker compose restart`
4. ✅ Check this troubleshooting guide
5. ✅ Check [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for relevant docs

### Gathering Information for Bug Reports

If you need to file an issue, include:

```bash
# System info
uname -a
docker --version
docker compose version
python --version

# Service status
docker compose ps

# Recent logs (last 100 lines)
docker compose logs --tail=100 > logs.txt

# Configuration (REDACT SENSITIVE DATA)
cat .env | grep -v API_KEY > config.txt

# Validation output
python scripts/validate_installation.py --verbose > validation.txt
```

### Where to Get Help

1. **Documentation**: [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)
2. **GitHub Issues**: Check existing issues first
3. **Logs**: Most issues show up in `docker compose logs`
4. **Slack/Discord**: (if community channels exist)

---

## Common Error Messages Reference

| Error Message | Common Cause | Quick Fix |
|--------------|--------------|-----------|
| "Connection refused" | Service not started | Wait 30s, check `docker compose ps` |
| "404 Not Found" | Wrong endpoint/port | Check port 7443, verify endpoint |
| "401 Unauthorized" | Missing/invalid API key | Check API key in .env |
| "ROUTER_ADMIN_API_KEY must be set" | Missing env var | Set in .env (≥32 chars) |
| "Port already in use" | Port conflict | Change ports or stop conflicting service |
| "Mock response from..." | Using stub adapter | Configure production adapter (expected) |
| "Cannot connect to Redis" | Redis not running | Check `docker compose ps redis` |
| "atpctl: command not found" | CLI not installed | `pip install -e tools/cli` |
| "HTTP 404" on CLI commands | API endpoint missing | Check CLI_STATUS.md for workarounds |

---

## Prevention / Best Practices

### For Development
```bash
# Always use validation script
python scripts/validate_installation.py

# Check logs regularly
docker compose logs -f

# Monitor resources
docker stats

# Use Redis backend for multi-instance setups
ROUTER_STATE_BACKEND=redis
```

### For Production
```bash
# Use production deployment guide
# See: PRODUCTION_DEPLOYMENT_GUIDE.md

# Configure monitoring
# Prometheus + Grafana

# Use only production adapters
# Anthropic or OpenAI

# Enable tracing
ROUTER_ENABLE_TRACING=1

# Use proper secrets management
# Never commit .env with real API keys
```

---

## Known Limitations

See these documents for current limitations:

- **[ADAPTER_STATUS.md](ADAPTER_STATUS.md)** - Which adapters are stubs vs production
- **[CLI_STATUS.md](tools/cli/CLI_STATUS.md)** - Which CLI commands work vs broken
- **[TODO.md](TODO.md)** - Planned features and known issues

---

**Last Updated**: 2025-01-17

**Feedback**: If you encountered an issue not covered here, please file an issue or PR to improve this guide.
