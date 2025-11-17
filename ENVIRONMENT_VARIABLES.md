# ATP Environment Variables Reference

**Complete reference for all environment variables used in the ATP platform**

Last Updated: 2025-01-17

---

## Table of Contents

1. [Core Router Configuration](#core-router-configuration)
2. [Observability & Monitoring](#observability--monitoring)
3. [State Backend](#state-backend)
4. [Security & Authentication](#security--authentication)
5. [Performance & Limits](#performance--limits)
6. [Lifecycle Management](#lifecycle-management)
7. [Memory Gateway](#memory-gateway)
8. [Adapters](#adapters)
9. [CLI Configuration](#cli-configuration)
10. [Development & Testing](#development--testing)

---

## Core Router Configuration

### ROUTER_SERVICE_VERSION
- **Description**: Version identifier for the router service
- **Default**: `"v0.1.0"`
- **Required**: No
- **Example**: `ROUTER_SERVICE_VERSION=v1.0.0`

### ROUTER_DATA_DIR
- **Description**: Directory for router data persistence
- **Default**: `./data`
- **Required**: No
- **Example**: `ROUTER_DATA_DIR=/var/lib/atp/data`

### ROUTER_PORT
- **Description**: Port for router service HTTP server
- **Default**: `7443`
- **Required**: No
- **Example**: `ROUTER_PORT=8080`
- **Note**: Default changed to 7443 for consistency. Update client applications accordingly.

---

## Observability & Monitoring

### ROUTER_ENABLE_TRACING
- **Description**: Enable OpenTelemetry distributed tracing
- **Default**: `false` (or `0`)
- **Required**: No
- **Values**: `1`, `true`, `yes` (enabled) | `0`, `false`, `no` (disabled)
- **Example**: `ROUTER_ENABLE_TRACING=1`

### ROUTER_OTLP_ENDPOINT
- **Description**: OpenTelemetry collector endpoint for trace export
- **Default**: `http://localhost:4317`
- **Required**: Only if tracing is enabled
- **Example**: `ROUTER_OTLP_ENDPOINT=http://otel-collector:4317`

### ROUTER_DISABLE_OTLP_EXPORT
- **Description**: Disable network export of traces (for testing)
- **Default**: `false`
- **Required**: No
- **Example**: `ROUTER_DISABLE_OTLP_EXPORT=1`

### ROUTER_TEST_TRACING_MODE
- **Description**: Use in-memory dummy tracer for testing
- **Default**: Not set
- **Required**: No
- **Values**: `dummy`
- **Example**: `ROUTER_TEST_TRACING_MODE=dummy`

### ROUTER_ENABLE_LAT_HIST
- **Description**: Enable latency histogram metrics
- **Default**: `true`
- **Required**: No
- **Example**: `ROUTER_ENABLE_LAT_HIST=1`

---

## State Backend

### ROUTER_STATE_BACKEND
- **Description**: State storage backend selection
- **Default**: `memory`
- **Required**: No
- **Values**: `memory` | `redis`
- **Example**: `ROUTER_STATE_BACKEND=redis`
- **Note**: Use `redis` for production deployments with multiple router instances

### ROUTER_REDIS_URL
- **Description**: Redis connection URL for state backend
- **Default**: `redis://localhost:6379/0`
- **Required**: Only if `ROUTER_STATE_BACKEND=redis`
- **Format**: `redis://[user:password@]host:port/db`
- **Example**: `ROUTER_REDIS_URL=redis://redis:6379/0`

### ROUTER_PERSIST_INTERVAL_SEC
- **Description**: Interval for persisting state to storage (seconds)
- **Default**: `60`
- **Required**: No
- **Example**: `ROUTER_PERSIST_INTERVAL_SEC=30`

---

## Security & Authentication

### ROUTER_ADMIN_API_KEY
- **Description**: **[REQUIRED]** Admin API key for administrative operations
- **Default**: None
- **Required**: **YES** (router will not start without this)
- **Security**: Generate a strong random key (min 32 characters)
- **Example**: `ROUTER_ADMIN_API_KEY=your-secure-admin-key-here-min-32-chars`
- **Warning**: Never commit this to version control. Use secret management.

### ROUTER_PII_SCRUB
- **Description**: Enable PII (Personally Identifiable Information) scrubbing
- **Default**: `false`
- **Required**: No
- **Example**: `ROUTER_PII_SCRUB=1`
- **Note**: When enabled, PII is redacted from logs and traces

### JWT_SECRET
- **Description**: Secret key for JWT token signing
- **Default**: None
- **Required**: For production deployments with authentication
- **Security**: Use strong random secret (min 64 characters recommended)
- **Example**: `JWT_SECRET=your-jwt-secret-key-minimum-64-characters`

### ENCRYPTION_KEY
- **Description**: Encryption key for sensitive data at rest
- **Default**: None
- **Required**: For production deployments
- **Security**: Must be exactly 32 bytes (base64 encoded)
- **Example**: `ENCRYPTION_KEY=your-32-byte-base64-encoded-key-here=`

### OPA_URL
- **Description**: Open Policy Agent URL for policy enforcement
- **Default**: `http://localhost:8181`
- **Required**: Only if using OPA for policy enforcement
- **Example**: `OPA_URL=http://opa:8181`

---

## Performance & Limits

### ROUTER_RPS_LIMIT
- **Description**: Maximum requests per second rate limit
- **Default**: `100`
- **Required**: No
- **Example**: `ROUTER_RPS_LIMIT=1000`
- **Note**: Adjust based on your infrastructure capacity

### ROUTER_RPS_BURST
- **Description**: Burst allowance for rate limiting
- **Default**: Equal to `ROUTER_RPS_LIMIT`
- **Required**: No
- **Example**: `ROUTER_RPS_BURST=200`
- **Note**: Allows short bursts above sustained rate limit

### ROUTER_MAX_PROMPT_CHARS
- **Description**: Maximum characters allowed in a single prompt
- **Default**: `6000`
- **Required**: No
- **Example**: `ROUTER_MAX_PROMPT_CHARS=10000`
- **Note**: Prevents excessive token usage

### ROUTER_MAX_CONCURRENT
- **Description**: Maximum concurrent requests being processed
- **Default**: `100`
- **Required**: No
- **Example**: `ROUTER_MAX_CONCURRENT=500`

---

## Lifecycle Management

### PROMOTE_MIN_CALLS
- **Description**: Minimum calls required before considering model promotion
- **Default**: `10`
- **Required**: No
- **Example**: `PROMOTE_MIN_CALLS=20`

### PROMOTE_COST_IMPROVE
- **Description**: Required cost improvement (fraction) for promotion
- **Default**: `0.1` (10% improvement)
- **Required**: No
- **Example**: `PROMOTE_COST_IMPROVE=0.15`

### DEMOTE_MIN_CALLS
- **Description**: Minimum calls before considering model demotion
- **Default**: `10`
- **Required**: No
- **Example**: `DEMOTE_MIN_CALLS=20`

### DEMOTE_COST_REGRESS
- **Description**: Cost regression threshold (fraction) for demotion
- **Default**: `0.2` (20% worse performance)
- **Required**: No
- **Example**: `DEMOTE_COST_REGRESS=0.25`

### PROMO_DEMO_HYSTERESIS_SEC
- **Description**: Cooldown period between promotion/demotion actions (seconds)
- **Default**: `300` (5 minutes)
- **Required**: No
- **Example**: `PROMO_DEMO_HYSTERESIS_SEC=600`

### BANDIT_STRATEGY
- **Description**: Multi-armed bandit algorithm selection strategy
- **Default**: `ucb` (Upper Confidence Bound)
- **Required**: No
- **Values**: `ucb` | `thompson` | `epsilon_greedy`
- **Example**: `BANDIT_STRATEGY=thompson`

### UCB_EXPLORE_FACTOR
- **Description**: Exploration factor for UCB algorithm
- **Default**: `2.0`
- **Required**: No
- **Example**: `UCB_EXPLORE_FACTOR=1.5`
- **Note**: Higher values encourage more exploration

### ENABLE_BUDGET_PREFLIGHT
- **Description**: Enable budget checking before request processing
- **Default**: `false`
- **Required**: No
- **Example**: `ENABLE_BUDGET_PREFLIGHT=1`

### ENABLE_CHALLENGER
- **Description**: Enable champion/challenger experimentation
- **Default**: `false`
- **Required**: No
- **Example**: `ENABLE_CHALLENGER=1`
- **Note**: When enabled, includes challenger model metadata in responses

---

## Memory Gateway

### MEMORY_GATEWAY_URL
- **Description**: URL for the memory gateway service
- **Default**: `http://localhost:8080`
- **Required**: Only if using memory gateway features
- **Example**: `MEMORY_GATEWAY_URL=http://memory-gateway:8080`

### FEATURE_WIRE_MEMORY
- **Description**: Enable memory gateway integration
- **Default**: `false`
- **Required**: No
- **Example**: `FEATURE_WIRE_MEMORY=true`

---

## Adapters

### ADAPTER_ENDPOINTS
- **Description**: JSON array of adapter gRPC endpoint URLs
- **Default**: `[]`
- **Required**: At least one adapter endpoint for router to function
- **Format**: JSON array of URLs
- **Example**: `ADAPTER_ENDPOINTS=["http://persona_adapter:7070","http://ollama_adapter:7070"]`

### ANTHROPIC_API_KEY
- **Description**: API key for Anthropic Claude models
- **Default**: None
- **Required**: Only if using Anthropic adapter
- **Example**: `ANTHROPIC_API_KEY=sk-ant-...`
- **Security**: Never commit to version control

### OPENAI_API_KEY
- **Description**: API key for OpenAI GPT models
- **Default**: None
- **Required**: Only if using OpenAI adapter
- **Example**: `OPENAI_API_KEY=sk-...`
- **Security**: Never commit to version control

### GOOGLE_API_KEY
- **Description**: API key for Google/Vertex AI models
- **Default**: None
- **Required**: Only if using Google adapter
- **Example**: `GOOGLE_API_KEY=...`
- **Note**: Currently stub implementation only

---

## CLI Configuration

### ATP_API_URL
- **Description**: Base URL for ATP Router Service (used by atpctl CLI)
- **Default**: `http://localhost:7443`
- **Required**: No
- **Example**: `ATP_API_URL=https://atp.yourdomain.com`
- **Note**: Updated default from 8000 to 7443 for consistency

### ATP_API_KEY
- **Description**: API key for CLI authentication
- **Default**: None
- **Required**: Only if router requires authentication
- **Example**: `ATP_API_KEY=your-api-key`

### ATP_CLIENT_TIMEOUT
- **Description**: Timeout for client HTTP requests (seconds)
- **Default**: `3` (for health checks), `5` (for operations)
- **Required**: No
- **Example**: `ATP_CLIENT_TIMEOUT=10`

---

## Development & Testing

### RUST_LOG
- **Description**: Rust logging level for atp-router (Rust implementation)
- **Default**: `info`
- **Required**: No
- **Values**: `trace` | `debug` | `info` | `warn` | `error`
- **Example**: `RUST_LOG=info,atp_router=debug`

### CORS_ALLOWED_ORIGINS
- **Description**: Comma-separated list of allowed CORS origins
- **Default**: `*` (all origins - development only)
- **Required**: No
- **Example**: `CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.example.com`
- **Security**: Restrict in production

### NEXT_PUBLIC_AGGREGATOR_URL
- **Description**: URL for admin aggregator service (Next.js frontend)
- **Default**: None
- **Required**: Only if using Next.js admin dashboard
- **Example**: `NEXT_PUBLIC_AGGREGATOR_URL=http://localhost:8081`

---

## Quick Start Examples

### Minimal Local Development
```bash
# Minimum required for local development
export ROUTER_ADMIN_API_KEY="dev-admin-key-minimum-32-characters-long"
export ROUTER_STATE_BACKEND=memory

# Start router
python -m router_service
```

### Production with Redis
```bash
# Production configuration
export ROUTER_ADMIN_API_KEY="prod-admin-key-USE-SECRET-MANAGER"
export ROUTER_STATE_BACKEND=redis
export ROUTER_REDIS_URL=redis://redis:6379/0
export ROUTER_ENABLE_TRACING=1
export ROUTER_OTLP_ENDPOINT=http://otel-collector:4317
export ROUTER_RPS_LIMIT=1000
export ROUTER_MAX_CONCURRENT=500
export ROUTER_PII_SCRUB=1

# Adapter configuration
export ANTHROPIC_API_KEY="sk-ant-YOUR-KEY-HERE"
export OPENAI_API_KEY="sk-YOUR-KEY-HERE"
export ADAPTER_ENDPOINTS='["http://anthropic-adapter:7070","http://openai-adapter:7070"]'

# Start router
python -m router_service
```

### With Full Observability
```bash
# Complete observability stack
export ROUTER_ENABLE_TRACING=1
export ROUTER_OTLP_ENDPOINT=http://otel-collector:4317
export ROUTER_ENABLE_LAT_HIST=1

# State persistence
export ROUTER_STATE_BACKEND=redis
export ROUTER_REDIS_URL=redis://redis:6379/0
export ROUTER_PERSIST_INTERVAL_SEC=30

# Policy enforcement
export OPA_URL=http://opa:8181
```

---

## Security Best Practices

1. **Never commit secrets to version control**
   - Use `.env` files (gitignored)
   - Use secret management systems (AWS Secrets Manager, GCP Secret Manager, etc.)

2. **Required production secrets**:
   - `ROUTER_ADMIN_API_KEY` (minimum 32 characters)
   - `JWT_SECRET` (minimum 64 characters)
   - `ENCRYPTION_KEY` (exactly 32 bytes, base64)
   - API keys for adapters (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.)

3. **Rotate secrets regularly**
   - Admin API keys: Every 90 days
   - JWT secrets: Every 180 days
   - Encryption keys: Follow your organization's policy

4. **Use environment-specific configurations**
   - Development: `.env.development`
   - Staging: `.env.staging`
   - Production: Secret management system

---

## Troubleshooting

### Router won't start
**Check**: Is `ROUTER_ADMIN_API_KEY` set?
```bash
# Must be set (min 32 chars)
export ROUTER_ADMIN_API_KEY="your-secure-key-minimum-32-characters"
```

### CLI can't connect to router
**Check**: Is `ATP_API_URL` correct?
```bash
# Default changed to 7443
export ATP_API_URL="http://localhost:7443"
```

### Adapters not found
**Check**: Is `ADAPTER_ENDPOINTS` configured?
```bash
# Must be valid JSON array
export ADAPTER_ENDPOINTS='["http://adapter1:7070","http://adapter2:7070"]'
```

### State not persisting
**Check**: Redis configuration
```bash
export ROUTER_STATE_BACKEND=redis
export ROUTER_REDIS_URL=redis://redis:6379/0
```

---

## See Also

- [Getting Started Guide](GETTING_STARTED.md)
- [Production Deployment Guide](PRODUCTION_DEPLOYMENT_GUIDE.md)
- [Security Documentation](docs/security/SECURITY_CLEANUP_SUMMARY.md)
- [.env.example](.env.example) - Template for environment variables
