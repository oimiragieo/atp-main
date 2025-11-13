# ADR: Rejection/Speculative Sampling Event Surfacing (GAP-135)

## Status
Accepted

## Context
The ATP router service handles various rejection scenarios (input validation, replay detection, policy violations) and implements speculative sampling for latency optimization. However, these events are not consistently surfaced or observable, making it difficult to:

1. Monitor system health and rejection patterns
2. Analyze speculative sampling effectiveness
3. Debug issues in production
4. Make data-driven decisions about system behavior

## Decision
Implement a structured event system for rejection and speculative sampling events with the following components:

### Event Types
1. **Rejection Events**: Structured events for all rejection scenarios
2. **Speculative Events**: Events for speculative sampling decisions and outcomes

### Architecture
- **EventEmitter**: Central event emission system with pluggable handlers
- **Structured Events**: Typed event classes with consistent schemas
- **Metrics Integration**: Automatic counter increments for speculative events
- **Backward Compatibility**: Non-breaking integration with existing components

## Implementation Details

### Event Schemas

#### Rejection Event
```json
{
  "event_type": "rejection",
  "reason": "input_validation|replay_detected|policy_violation|...",
  "component": "input_hardening|replay_guard|policy_engine|...",
  "request_id": "optional-request-identifier",
  "details": {
    "additional": "context-specific-data"
  },
  "timestamp": 1640995200.123
}
```

#### Speculative Event
```json
{
  "event_type": "speculative",
  "speculative_type": "speculation_attempted|speculation_accepted|speculation_rejected",
  "model_name": "draft-model-name",
  "latency_saved_ms": 15.5,
  "confidence_score": 0.85,
  "request_id": "optional-request-identifier",
  "details": {
    "draft_response": "draft model output",
    "target_response": "target model output"
  },
  "timestamp": 1640995200.123
}
```

### Components

#### EventEmitter Class
- Thread-safe event emission
- Pluggable handler system
- Graceful handler failure handling

#### SpeculativeSampler Class
- Implements speculative sampling logic
- Automatic event emission for all decisions
- Configurable acceptance thresholds
- Benchmarking capabilities

#### Integration Points
- **Input Hardening**: Emits rejection events for validation failures
- **Replay Guard**: Emits rejection events for duplicate detection
- **Speculative Sampling**: Emits events for all speculation attempts and outcomes

### Metrics
- `speculative_events_total`: Counter for all speculative sampling events
- Existing rejection counters remain unchanged for backward compatibility

## Consequences

### Positive
- **Improved Observability**: Consistent event structure for monitoring and alerting
- **Better Debugging**: Rich context in rejection and speculation events
- **Data-Driven Decisions**: Analytics on rejection patterns and speculation effectiveness
- **Non-Breaking**: Existing functionality unchanged, events are additive

### Negative
- **Performance Impact**: Event emission adds small latency overhead
- **Memory Usage**: Event objects and handler storage consume memory
- **Complexity**: Additional abstraction layer for event handling

### Mitigation
- **Lazy Handler Registration**: Handlers only registered when needed
- **Efficient Serialization**: Events use lightweight dictionary representation
- **Configurable Emission**: Event emission can be disabled for performance-critical paths

## Alternatives Considered

### Alternative 1: Direct Metrics Only
- **Pros**: Simpler implementation, lower overhead
- **Cons**: Less context, harder to correlate events, limited debugging information
- **Decision**: Rejected - insufficient observability for complex scenarios

### Alternative 2: Structured Logging Only
- **Pros**: Flexible, searchable, integrates with existing logging infrastructure
- **Cons**: Higher latency, more complex parsing, less structured for metrics
- **Decision**: Rejected - better suited for metrics integration

### Alternative 3: Custom Event Bus
- **Pros**: More flexible, supports complex routing and filtering
- **Cons**: Higher complexity, potential for tight coupling
- **Decision**: Rejected - overkill for current requirements

## Testing Strategy

### Unit Tests
- Event creation and serialization
- Handler registration and emission
- Speculative sampling logic
- Integration with existing components

### Integration Tests
- End-to-end event flow
- Handler failure scenarios
- Performance impact measurement

### Benchmark Tests
- Speculative sampling effectiveness
- Event emission overhead
- Memory usage patterns

## Future Considerations

### Potential Extensions
- **Event Persistence**: Store events in database for historical analysis
- **Event Filtering**: Allow components to filter events by type/severity
- **Event Aggregation**: Batch similar events for efficiency
- **Event Routing**: Route events to different handlers based on type

### Monitoring
- Dashboards for rejection rates and patterns
- Alerts on unusual speculation acceptance rates
- Performance monitoring for event emission overhead

## References
- GAP-102: Self-consistency sampling (dependency)
- Input hardening implementation
- Replay guard implementation
- Existing metrics registry patterns
