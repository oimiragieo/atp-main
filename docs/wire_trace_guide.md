# Golden Wire Trace Fixtures & Regression Harness

## Overview

The Golden Wire Trace Fixtures & Regression Harness (GAP-334) provides a systematic approach to capturing and validating canonical ATP protocol frame traces. This ensures protocol consistency and helps detect regressions in frame serialization/deserialization.

## Key Components

### 1. Canonical Trace Generation
The harness generates standardized session traces covering key protocol scenarios:
- **Basic Handshake**: SYN/ACK exchange for session establishment
- **Fragmented Messages**: Multi-part message transmission
- **Parallel Sessions**: Concurrent session processing with lane isolation
- **Error Handling**: RST frames and error propagation

### 2. JSONL Fixture Storage
Traces are stored in JSON Lines format for easy parsing and version control:
```json
{"scenario": "basic_handshake", "frames": [...], "expected_properties": {...}}
{"scenario": "fragmented_message", "frames": [...], "expected_properties": {...}}
```

### 3. Regression Detection
The harness compares current frame generation against golden fixtures:
- Frame structure validation
- Field-by-field diff analysis
- Session consistency checks
- QoS and window parameter validation

### 4. Change Approval Workflow
Intentional changes require explicit approval:
```bash
# Generate initial fixtures
python tools/golden_wire_trace_poc.py --generate-fixtures

# Run regression check
python tools/golden_wire_trace_poc.py --run-regression

# Approve changes if intentional
python tools/golden_wire_trace_poc.py --run-regression --approve-changes
```

## Usage in CI/CD

### Automated Regression Testing
```yaml
- name: Run Wire Trace Regression
  run: |
    python tools/golden_wire_trace_poc.py --run-regression
  continue-on-error: false

- name: Approve Changes (if intentional)
  run: |
    python tools/golden_wire_trace_poc.py --run-regression --approve-changes
  if: github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'protocol-change')
```

### Metrics Integration
The harness integrates with the metrics registry:
- `wire_regressions_detected_total`: Counter for detected regressions
- Tracks regression frequency for monitoring protocol stability

## Frame Structure Validation

### Required Fields
All frames must include:
- `v`: Protocol version (currently 1)
- `session_id`: Unique session identifier
- `stream_id`: Stream within session
- `msg_seq`: Message sequence number
- `frag_seq`: Fragment sequence (0 for non-fragmented)
- `flags`: Array of protocol flags
- `qos`: Quality of service level
- `ttl`: Time-to-live
- `window`: Flow control window
- `meta`: Metadata object
- `payload`: Message payload

### Validation Rules
- QoS must be one of: "gold", "silver", "bronze"
- Flags cannot contain empty strings
- Window parameters must be non-negative
- Session IDs must be consistent within a trace

## Best Practices

### When to Update Fixtures
- Protocol version changes
- New frame types or fields
- QoS parameter adjustments
- Window management changes

### Testing Strategy
- Run regression tests on every PR
- Require approval for protocol changes
- Monitor regression metrics for trends
- Include in release validation

### Maintenance
- Review fixtures quarterly for relevance
- Update for new protocol features
- Archive obsolete scenarios
- Document breaking changes

## Integration Points

### Dependencies
- `router_service.frame`: Frame model definitions
- `metrics.registry`: Metrics collection
- `test_artifacts/golden_traces/`: Fixture storage

### Related Components
- Frame codec validation
- Session state management
- Protocol conformance testing
- Cross-version compatibility

## Troubleshooting

### Common Issues
1. **Missing Fixtures**: Run `--generate-fixtures` first
2. **Encoding Errors**: Ensure UTF-8 encoding for JSONL files
3. **Import Errors**: Verify router_service module availability
4. **Permission Issues**: Check write access to test_artifacts directory

### Debug Mode
Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

### Planned Features
- Cross-version frame comparison
- Performance regression detection
- Automated fixture generation from live traffic
- Protocol fuzzing integration
- Historical regression analysis

### Extension Points
- Custom scenario generators
- Alternative serialization formats
- External fixture storage
- Real-time regression alerting
