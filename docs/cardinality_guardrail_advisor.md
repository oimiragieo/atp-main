# High-Cardinality Guardrail Advisor

## Overview

The High-Cardinality Guardrail Advisor (GAP-367) is a monitoring system that detects and provides recommendations for metrics with excessive label cardinality. High cardinality can lead to performance degradation, increased memory usage, and higher monitoring costs.

## Features

- **Automatic Detection**: Monitors metrics for cardinality explosions in real-time
- **Configurable Thresholds**: Customizable warning and critical thresholds
- **Smart Recommendations**: Provides actionable advice for optimizing high-cardinality metrics
- **Alert Cooldown**: Prevents alert fatigue with configurable cooldown periods
- **Pattern Recognition**: Detects common optimization opportunities in label values

## Configuration

### Basic Setup

```python
from router_service.cardinality_guardrail_advisor import init_cardinality_advisor

# Initialize with default thresholds (warning: 100, critical: 1000)
advisor = init_cardinality_advisor()

# Or customize thresholds
advisor = init_cardinality_advisor(
    warning_threshold=50,
    critical_threshold=200,
    max_sample_labels=10,
    alert_cooldown_seconds=3600  # 1 hour
)
```

### Integration with Metrics Collection

```python
from router_service.cardinality_guardrail_advisor import record_metric_label

# Record label values during metrics collection
def record_custom_metric(user_id: str, endpoint: str, status_code: int):
    # Your existing metrics collection
    # ...

    # Add cardinality monitoring
    record_metric_label("http_requests_total", user_id)
    record_metric_label("http_requests_total", endpoint)
    record_metric_label("http_requests_total", str(status_code))
```

## Thresholds and Severity Levels

| Severity | Threshold | Description |
|----------|-----------|-------------|
| Normal | < warning_threshold | No action needed |
| Low | ≥ warning_threshold | Monitor growth rate |
| Medium | ≥ warning_threshold * 1.5 | Consider optimization |
| High | ≥ critical_threshold | Review and optimize |
| Critical | ≥ critical_threshold * 2 | Immediate action required |

## Recommendations

The advisor provides specific recommendations based on detected patterns:

### Numeric ID Aggregation
**Pattern**: Labels containing numeric values (e.g., `user_12345`, `order_98765`)
**Recommendation**: Aggregate into ranges
```python
# Instead of: user_12345, user_12346, user_12347, ...
# Use: user_12300-12399, user_12400-12499, ...
```

### Long Label Truncation
**Pattern**: Labels longer than 50 characters
**Recommendation**: Truncate or hash long values
```python
# Instead of: very_long_label_name_that_causes_performance_issues
# Use: hash_or_truncated_value
```

### Inconsistent Label Lengths
**Pattern**: High variance in label lengths
**Recommendation**: Standardize label formats
```python
# Instead of: short, very_long_label_name, medium
# Use: consistent_naming_convention
```

### Multiple Prefixes
**Pattern**: Different prefixes for similar concepts
**Recommendation**: Use consistent naming
```python
# Instead of: api_v1_endpoint, db_v1_query, cache_v1_hit
# Use: service_v1_endpoint, service_v1_query, service_v1_hit
```

## Monitoring and Alerts

### Metrics

The advisor exposes the following Prometheus metrics:

- `cardinality_alerts_total`: Total number of cardinality alerts generated
- `cardinality_metrics_monitored`: Number of metrics currently being monitored
- `cardinality_violations_active`: Number of active cardinality violations

### Alert Examples

```yaml
# Prometheus alert rule example
groups:
  - name: cardinality_alerts
    rules:
      - alert: HighCardinalityDetected
        expr: cardinality_violations_active > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High cardinality detected in metrics"
          description: "Metrics with excessive unique labels detected. Check cardinality advisor recommendations."

      - alert: CriticalCardinalityDetected
        expr: increase(cardinality_alerts_total[1h]) > 5
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Critical cardinality explosion"
          description: "Multiple metrics experiencing cardinality explosions. Immediate optimization required."
```

## API Reference

### Core Classes

#### CardinalityGuardrailAdvisor

Main advisor class for monitoring cardinality.

**Methods:**
- `record_label_value(metric_name, label_value)`: Record a label value for monitoring
- `get_violations()`: Get all current violations
- `get_recommendations()`: Get advisor recommendations
- `get_cardinality_stats()`: Get statistics for all monitored metrics
- `clear_violation(metric_name)`: Clear a violation after remediation
- `reset_metric(metric_name)`: Reset monitoring for a metric

#### CardinalityViolation

Represents a cardinality violation.

**Attributes:**
- `metric_name`: Name of the metric with high cardinality
- `unique_labels`: Number of unique labels detected
- `threshold`: Threshold that was exceeded
- `timestamp`: When the violation was detected
- `sample_labels`: Sample of problematic label values

#### AdvisorRecommendation

Recommendation for optimizing high-cardinality metrics.

**Attributes:**
- `metric_name`: Name of the metric
- `severity`: Severity level (low, medium, high, critical)
- `action`: Recommended action
- `rationale`: Explanation of the issue
- `estimated_impact`: Expected impact of the issue
- `suggested_labels`: Specific optimization suggestions

### Global Functions

- `get_cardinality_advisor()`: Get the global advisor instance
- `init_cardinality_advisor(...)`: Initialize the global advisor
- `record_metric_label(metric_name, label_value)`: Convenience function for recording labels
- `get_cardinality_violations()`: Get all current violations
- `get_advisor_recommendations()`: Get all recommendations

## Best Practices

### 1. Set Appropriate Thresholds

Choose thresholds based on your system's capacity:

```python
# For high-throughput systems
init_cardinality_advisor(
    warning_threshold=1000,
    critical_threshold=5000
)

# For resource-constrained systems
init_cardinality_advisor(
    warning_threshold=100,
    critical_threshold=500
)
```

### 2. Monitor Alert Frequency

Use the `cardinality_alerts_total` metric to monitor alert frequency:

```python
# Check alert rate
alert_rate = get_metric_value("cardinality_alerts_total")
if alert_rate > threshold:
    # Investigate and adjust thresholds
    pass
```

### 3. Implement Gradual Optimization

Don't optimize all metrics at once:

1. Start with critical violations
2. Implement low-risk optimizations first
3. Monitor impact before proceeding
4. Gradually increase thresholds as optimizations take effect

### 4. Use with Existing Monitoring

Integrate with your existing monitoring stack:

```python
# Combine with existing metrics
def record_request_metrics(user_id, endpoint, status):
    # Existing metrics
    request_counter.labels(endpoint=endpoint, status=status).inc()

    # Add cardinality monitoring
    record_metric_label("requests_by_user", user_id)
    record_metric_label("requests_by_endpoint", endpoint)
```

## Troubleshooting

### Common Issues

#### False Positives
- **Cause**: Temporary spikes in cardinality
- **Solution**: Increase alert cooldown or adjust thresholds

#### Missing Violations
- **Cause**: Thresholds too high for your use case
- **Solution**: Lower warning/critical thresholds

#### Performance Impact
- **Cause**: Monitoring too many metrics
- **Solution**: Be selective about which metrics to monitor

### Debug Information

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('router_service.cardinality_guardrail_advisor').setLevel(logging.DEBUG)
```

## Examples

### Basic Usage

```python
from router_service.cardinality_guardrail_advisor import (
    init_cardinality_advisor,
    record_metric_label,
    get_advisor_recommendations
)

# Initialize advisor
init_cardinality_advisor(warning_threshold=10, critical_threshold=50)

# Record some metrics
for i in range(15):
    record_metric_label("user_requests", f"user_{i}")
    record_metric_label("api_calls", f"endpoint_{i % 5}")  # Lower cardinality

# Check for recommendations
recommendations = get_advisor_recommendations()
for rec in recommendations:
    print(f"{rec.severity}: {rec.action} for {rec.metric_name}")
```

### Integration with FastAPI

```python
from fastapi import Request
from router_service.cardinality_guardrail_advisor import record_metric_label

@app.middleware("http")
async def cardinality_monitoring(request: Request, call_next):
    # Record cardinality before processing
    record_metric_label("http_requests_path", request.url.path)
    record_metric_label("http_requests_method", request.method)

    # Extract user ID from token if available
    user_id = get_user_from_token(request)
    if user_id:
        record_metric_label("requests_by_user", user_id)

    response = await call_next(request)
    return response
```

### Custom Metric Collection

```python
from router_service.cardinality_guardrail_advisor import record_metric_label

class CustomMetricsCollector:
    def record_business_metric(self, tenant_id: str, operation: str, resource: str):
        # Record business metrics with cardinality monitoring
        record_metric_label("business_operations", operation)
        record_metric_label("business_resources", resource)

        # Tenant-specific monitoring (if applicable)
        record_metric_label(f"tenant_{tenant_id}_operations", operation)

        # Your existing metric recording logic
        # ...
```

## Performance Considerations

- **Memory Usage**: Advisor stores label sets in memory
- **CPU Overhead**: Minimal impact during normal operation
- **Storage**: Sample labels are kept for recommendation generation
- **Thread Safety**: All operations are thread-safe

For high-throughput systems, consider:
- Sampling label values instead of recording all
- Periodic cleanup of old metrics
- Separate advisor instances for different metric categories
