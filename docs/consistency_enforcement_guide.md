# Consistency Level Enforcement (GAP-305)

## Overview

This document describes the implementation of consistency level enforcement for ATP, supporting both EVENTUAL and READ-YOUR-WRITES (RYW) consistency levels. The system provides session stickiness middleware that routes reads to primary storage during the replication window for RYW sessions.

## Architecture

### Core Components

1. **ConsistencyEnforcer**: Main enforcement engine that manages sessions and routing decisions
2. **SessionState**: Tracks session metadata including consistency level and write timestamps
3. **Session Stickiness Middleware**: Integrated into the router service for automatic enforcement

### Consistency Levels

- **EVENTUAL**: Default consistency level with no enforcement (reads may see stale data)
- **RYW**: Read-your-writes consistency ensures that writes are immediately visible to the writing session

## Implementation Details

### Session Management

```python
# Start a session with consistency enforcement
session = enforcer.start_session(
    session_id="user_session_123",
    consistency_level="RYW",
    namespace="tenant1",
    ttl_seconds=300
)

# Record write operations for consistency tracking
enforcer.record_write("user_session_123", "tenant1")

# Check if read should route to primary
should_route_primary = enforcer.should_route_to_primary("user_session_123", "tenant1")
```

### Router Integration

The consistency enforcer is integrated into the `/v1/ask` endpoint:

1. Session identification from `session_id`, `conversation_id`, or headers
2. Consistency level extraction from request parameters
3. Write recording after successful response generation
4. Automatic cleanup of expired sessions

### Memory Gateway Integration

The memory gateway supports consistency headers:

```http
GET /v1/memory/tenant1/key1
X-Session-ID: user_session_123
X-Consistency-Level: RYW
```

## Configuration

### Environment Variables

- `ENABLE_CONSISTENCY_ENFORCEMENT`: Enable/disable consistency enforcement (default: true)
- `DEFAULT_CONSISTENCY_LEVEL`: Default consistency level for sessions (default: EVENTUAL)
- `SESSION_TTL_SECONDS`: Session timeout in seconds (default: 300)
- `RYW_WINDOW_SECONDS`: RYW enforcement window after writes (default: 2)

### Namespace Defaults

Consistency levels can be configured per namespace:

```python
enforcer.set_namespace_default("secure_namespace", "RYW")
```

## Metrics

The implementation provides comprehensive metrics:

- `ryw_sessions_active`: Gauge of active RYW sessions
- `ryw_enforcement_count`: Counter of RYW enforcement decisions
- `ryw_read_latency_ms`: Histogram of read latencies for RYW operations

## API Usage

### Client Request Format

```json
{
  "prompt": "What is the weather?",
  "session_id": "user_session_123",
  "consistency_level": "RYW",
  "conversation_id": "conv_456",
  "tenant": "tenant1"
}
```

### Response Headers

For RYW requests, the response includes consistency metadata:

```http
X-Consistency-Enforced: true
X-Session-ID: user_session_123
```

## Testing

### Unit Tests

Comprehensive test suite covering:

- Session lifecycle management
- Write recording and RYW enforcement
- Session expiry handling
- Namespace-level configuration
- Performance characteristics

### Integration Tests

- End-to-end consistency verification
- Replication lag simulation
- Session stickiness validation
- Memory gateway integration

## Performance Considerations

### Latency Impact

- EVENTUAL consistency: No additional latency
- RYW consistency: Minimal overhead for session management (~1-2ms)

### Memory Usage

- Session state storage: ~200 bytes per active session
- Automatic cleanup of expired sessions
- Configurable TTL to control memory usage

## Security Considerations

### Session Isolation

- Sessions are isolated by tenant/namespace
- Session IDs are opaque and randomly generated
- No cross-tenant session access

### Data Privacy

- Session metadata does not contain sensitive data
- Automatic cleanup prevents data accumulation
- No persistent storage of session state

## Monitoring and Observability

### Key Metrics to Monitor

1. **Session Activity**: Track active sessions and creation rates
2. **Enforcement Rate**: Monitor RYW enforcement decisions
3. **Latency Impact**: Measure read latency differences between consistency levels
4. **Error Rates**: Track consistency-related errors

### Alerts

- High session creation rate (potential DoS)
- Excessive RYW enforcement (performance impact)
- Session state memory usage (resource exhaustion)

## Troubleshooting

### Common Issues

1. **Session Not Found**: Check session TTL and cleanup timing
2. **RYW Not Enforced**: Verify write recording and session state
3. **High Latency**: Check replication lag and RYW window size

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
export ENABLE_CONSISTENCY_DEBUG=1
```

## Future Enhancements

### Planned Features

1. **Cross-region Consistency**: Multi-region RYW support
2. **Custom Consistency Levels**: User-defined consistency policies
3. **Consistency SLAs**: Service level agreements for consistency guarantees
4. **Advanced Routing**: Intelligent primary/replica selection

### Performance Optimizations

1. **Session Sharding**: Distribute session state across multiple instances
2. **Async Cleanup**: Background session cleanup to reduce latency
3. **Compression**: Compress session metadata for memory efficiency
