# Edge Routing, Compression & SLM Fallback Guide

## Overview

The ATP Edge Router provides intelligent request processing at the network edge, including:

- **Prompt Compression**: Reduces request size for efficient core routing
- **SLM Fallback**: Local Small Language Model processing for cost/latency optimization
- **Secure Token Exchange**: Authenticated communication with core routers
- **Metrics & Monitoring**: Comprehensive telemetry for edge operations

## Architecture

```
[Client Request] → [Edge Router] → [SLM Check] → [Compression] → [Core Router]
                      ↓                    ↓
                [Local SLM]         [Compressed Request]
                      ↓                    ↓
                [Edge Response]     [Core Response]
```

## Key Features

### 🔧 Prompt Compression
- Automatic compression of long prompts using truncation + summarization
- Configurable compression ratios and thresholds
- Preserves critical context while reducing token count
- Real-time compression metrics and monitoring

### 🧠 SLM Fallback Processing
- Local Small Language Model for edge processing
- 90%+ cost reduction vs large model processing
- Support for fast/balanced quality requests
- Automatic fallback to core for complex queries

### 🔐 Secure Token Exchange
- HMAC-SHA256 signed tokens for authentication
- Timestamp-based expiration (default: 1 hour)
- Nonce-based replay attack protection
- Request integrity verification via content hashing

### 🚀 Request Relay
- Transparent proxying to core router
- Streaming response support
- Error handling and retry logic
- Latency monitoring and metrics

### 📊 Observability
- Comprehensive metrics collection including edge savings percentage
- Structured logging
- Health check endpoints
- Performance monitoring

## Configuration

### Edge Router Configuration

```python
from router_service.edge_router import EdgeConfig

config = EdgeConfig(
    core_endpoint="https://core-router.internal:8443",
    edge_id="edge-us-west-01",
    shared_secret="your-256-bit-secret-key",
    token_ttl_seconds=3600,        # 1 hour
    replay_window_seconds=300,     # 5 minutes
    max_request_size=1048576,      # 1MB
    # Compression settings
    max_prompt_length=4000,        # Tokens before compression
    compression_ratio=0.7,         # Target compression ratio
    # SLM settings
    enable_slm_fallback=True,      # Enable local SLM processing
    slm_max_tokens=1000,           # Max tokens for SLM
    slm_quality_threshold=0.75     # Quality threshold for SLM
)
```

### Environment Variables

```bash
# Required
EDGE_SHARED_SECRET=your-256-bit-secret-key
CORE_ENDPOINT=https://core-router.internal:8443

# Optional
EDGE_ID=edge-us-west-01
EDGE_PORT=8080
DISABLE_SSL_VERIFY=false

# Compression settings
EDGE_MAX_PROMPT_LENGTH=4000
EDGE_COMPRESSION_RATIO=0.7

# SLM settings
EDGE_ENABLE_SLM=true
EDGE_SLM_MAX_TOKENS=1000
EDGE_SLM_QUALITY_THRESHOLD=0.75
```

## Prompt Compression

### Compression Heuristic

The edge router automatically compresses long prompts using a truncation + summarization approach:

1. **Detection**: Prompts exceeding `max_prompt_length` tokens are flagged for compression
2. **Truncation**: Preserve first 25% and last 25% of the original prompt
3. **Summarization**: Extract key sentences from the middle 50% containing important keywords
4. **Reconstruction**: Combine preserved sections with summary for coherent context

### Configuration

```python
EdgeConfig(
    max_prompt_length=4000,      # Tokens before compression
    compression_ratio=0.7        # Target compression ratio
)
```

### Example

**Original Prompt** (5000 tokens):
```
Introduction to machine learning concepts...
[2000 tokens of detailed explanation]
Key algorithms include decision trees, neural networks...
[2000 tokens of examples and code]
Conclusion and future directions...
```

**Compressed Prompt** (3500 tokens):
```
Introduction to machine learning concepts...
[SUMMARY: Key algorithms include decision trees, neural networks, with important results showing...]
Conclusion and future directions...
```

## SLM Fallback

### Processing Logic

The edge router evaluates each request for local SLM processing:

1. **Eligibility Check**: Short prompts with balanced/high quality requirements
2. **Local Processing**: Use quantized SLM for immediate response
3. **Cost Optimization**: 90%+ cost reduction vs large model processing
4. **Fallback**: Relay to core for complex or high-quality requirements

### SLM Capabilities

- **Max Tokens**: 1000 tokens per request
- **Quality Support**: `fast`, `balanced` (not `high`)
- **Response Types**: Questions, summaries, general queries
- **Cost Savings**: ~90% reduction vs core model processing

### Configuration

```python
EdgeConfig(
    enable_slm_fallback=True,
    slm_max_tokens=1000,
    slm_quality_threshold=0.75
)
```

## Processing Flow

```python
# 1. Check SLM eligibility
if slm.can_handle_request(request):
    return slm.process_request(request)

# 2. Apply compression if needed
if compressor.should_compress(request["prompt"]):
    compressed, metadata = compressor.compress_prompt(request["prompt"])
    request["prompt"] = compressed

# 3. Relay to core with authentication
token = token_manager.generate_token(request)
response = await relay_to_core(request, token)

# 4. Add edge processing metadata
response["edge_processing"] = {
    "method": "slm_fallback" | "compression_relay" | "direct_relay",
    "latency_ms": processing_time,
    "compression_metadata": metadata  # if compressed
}
```

## Usage

### Starting an Edge Router

```bash
# Using command line
python router_service/edge_router.py \
  --core-endpoint https://core-router.internal:8443 \
  --edge-id edge-us-west-01 \
  --shared-secret your-secret-key \
  --port 8080

# Using environment variables
export EDGE_SHARED_SECRET=your-secret-key
export CORE_ENDPOINT=https://core-router.internal:8443
python router_service/edge_router.py --edge-id edge-us-west-01
```

### API Endpoints

#### POST /ask
Relay an inference request to the core router.

**Request:**
```json
{
  "prompt": "Write a short story about AI",
  "quality": "high",
  "latency_slo_ms": 3000,
  "max_tokens": 500
}
```

**Response:**
```json
{
  "model": "gpt-4",
  "response": "Once upon a time...",
  "tokens_used": 150,
  "latency_ms": 1200
}
```

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "edge_id": "edge-us-west-01",
  "uptime_seconds": 3600
}
```

## Security Model

### Token Structure

```json
{
  "payload": {
    "edge_id": "edge-us-west-01",
    "timestamp": 1640995200,
    "nonce": "abc123def456",
    "request_hash": "sha256-hash-of-request"
  },
  "signature": "hmac-sha256-signature"
}
```

### Authentication Flow

1. **Token Generation**: Edge generates signed token with request details
2. **Request Relay**: Token included in Authorization header
3. **Core Validation**: Core validates token signature and freshness
4. **Replay Check**: Core ensures nonce hasn't been used recently
5. **Request Processing**: Valid requests processed normally

### Security Considerations

- **Secret Distribution**: Shared secrets must be securely distributed to edge nodes
- **Token Expiration**: Short TTL reduces window for token replay
- **Replay Protection**: Nonce tracking prevents token reuse
- **Request Integrity**: Content hashing ensures request tampering detection
- **SSL/TLS**: All communication should use HTTPS

## Metrics

### Edge Savings Percentage
- **Metric**: `edge_savings_pct`
- **Type**: Gauge
- **Description**: Percentage cost savings from edge processing
- **Calculation**: `((core_cost - edge_cost) / core_cost) * 100`

### Request Processing
- **Metric**: `edge_requests_total`
- **Labels**: `method` (slm_fallback, compression_relay, direct_relay)
- **Description**: Total requests processed by edge router

### Processing Latency
- **Metric**: `edge_relay_latency_seconds`
- **Type**: Histogram
- **Buckets**: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
- **Description**: End-to-end request processing time

### Counters
- `edge_requests_total`: Total requests relayed
- `edge_auth_failures_total{reason="..."}`: Authentication failures by reason

### Histograms
- `edge_relay_latency_seconds`: Request relay latency distribution

### Gauges
- `edge_active_connections`: Currently active connections
- `edge_savings_pct`: Cost savings percentage from edge processing

## Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY router_service/edge_router.py .

EXPOSE 8080

CMD ["python", "edge_router.py", \
     "--core-endpoint", "${CORE_ENDPOINT}", \
     "--edge-id", "${EDGE_ID}"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: atp-edge-router
spec:
  replicas: 3
  selector:
    matchLabels:
      app: atp-edge-router
  template:
    metadata:
      labels:
        app: atp-edge-router
    spec:
      containers:
      - name: edge-router
        image: atp-edge-router:latest
        ports:
        - containerPort: 8080
        env:
        - name: CORE_ENDPOINT
          value: "https://core-router.internal:8443"
        - name: EDGE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: EDGE_SHARED_SECRET
          valueFrom:
            secretKeyRef:
              name: edge-secrets
              key: shared-secret
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
```

### Load Balancing

```yaml
apiVersion: v1
kind: Service
metadata:
  name: atp-edge-router-service
spec:
  selector:
    app: atp-edge-router
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## Monitoring

### Health Checks

The edge router provides comprehensive health monitoring:

```bash
# Health check
curl http://edge-router:8080/health

# Metrics endpoint (if enabled)
curl http://edge-router:8080/metrics
```

### Logging

Structured logging includes:
- Request IDs for tracing
- Authentication events
- Error conditions
- Performance metrics

### Alerting

Recommended alerts:
- High authentication failure rate
- Increased relay latency
- Service unavailability
- Token expiration issues

## Troubleshooting

### Common Issues

#### Authentication Failures
```
Error: Invalid token signature
```
**Solution**: Verify shared secret is correct and synchronized between edge and core.

#### Replay Attack Detected
```
Error: Replay attack detected
```
**Solution**: Check system clock synchronization and token TTL settings.

#### Core Connection Failed
```
Error: Core router connection failed
```
**Solution**: Verify core endpoint URL and network connectivity.

### Debug Mode

Enable debug logging:
```bash
export PYTHONPATH=/app
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from router_service.edge_router import EdgeRouter, EdgeConfig
# ... debug code ...
"
```

## Performance Tuning

### Connection Pooling
```python
# Configure HTTP client
client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    timeout=httpx.Timeout(10.0, connect=5.0)
)
```

### Caching
Future enhancements may include:
- Response caching for identical requests
- Token caching to reduce generation overhead
- DNS caching for core endpoint resolution

### Scaling Considerations
- Horizontal scaling with load balancer
- Regional deployment for latency optimization
- Auto-scaling based on request volume

## Future Enhancements

### Planned Features
- **Response Caching**: Cache frequent responses at edge
- **Request Compression**: Reduce bandwidth for large prompts
- **Circuit Breaking**: Fail fast during core outages
- **Rate Limiting**: Per-client rate limiting
- **Geo-based Routing**: Route to nearest core instance

### Integration Points
- **CDN Integration**: Use CDN for static content
- **Service Mesh**: Istio integration for advanced routing
- **Edge Computing**: Run lightweight models at edge
- **Federated Learning**: Contribute to model improvement

## Contributing

When contributing to edge routing:
1. Maintain backward compatibility
2. Add comprehensive tests
3. Update documentation
4. Consider security implications
5. Test with various network conditions

## Related Documentation

- [ATP Protocol Specification](../docs/01_ATP.md)
- [Security Model](../docs/09_Security_Model_and_WAF.md)
- [Deployment Guide](../docs/15_Deployment_Guide_Docker_and_K8s.md)
- [Observability Guide](../docs/14_Observability_Tracing_and_Dashboards.md)
