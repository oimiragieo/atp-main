# Predictive Prewarming Scheduler

## Overview

The Predictive Prewarming Scheduler analyzes historical request patterns to predict future demand and proactively warm up edge resources (such as SLM models) before they're needed. This reduces latency for incoming requests by ensuring resources are ready when demand spikes.

## Architecture

```
[Request History] → [Pattern Analysis] → [Demand Prediction] → [Resource Prewarming]
                        ↓                           ↓
                [Time-of-Day Patterns]     [Inter-Arrival Times]
                        ↓                           ↓
                [Median Calculation]     [Prediction Horizon]
                        ↓                           ↓
                [Prewarm Decision]     [Hit Rate Tracking]
```

## Key Features

### 🔮 Demand Prediction
- Analyzes historical request patterns using time-of-day and inter-arrival time analysis
- Uses median inter-arrival times for robust prediction (resistant to outliers)
- Predicts demand up to 5 minutes in advance
- Minimum 10 requests required for reliable prediction

### ⚡ Resource Prewarming
- Prewarms resources 2 minutes before predicted demand
- Tracks prewarmed resources to avoid duplicate warming
- Automatic cleanup of expired prewarms (resources not used within 5 minutes)
- Support for different resource types (SLM models by quality level)

### 📊 Performance Metrics
- **Prewarm Hits**: Counter of successful prewarm usage
- **Prewarm Waste**: Histogram of time wasted on unused prewarms
- Real-time hit rate and waste tracking

## Prediction Algorithm

### Data Collection

The scheduler maintains a rolling history of requests:

```python
request_history: List[Tuple[float, dict]] = []  # (timestamp, request_data)
max_history_size = 1000  # Prevent unbounded growth
```

Each request is categorized by resource type:
```python
resource_id = f"slm_{quality}"  # e.g., "slm_balanced", "slm_fast"
```

### Pattern Analysis

1. **Time-of-Day Patterns**: Track request frequency by hour
   ```python
   hourly_patterns[hour] = request_count
   ```

2. **Inter-Arrival Times**: Calculate time between consecutive requests
   ```python
   inter_arrivals = [t[i+1] - t[i] for i in range(len(timestamps)-1)]
   ```

3. **Median Calculation**: Use median for robust prediction
   ```python
   sorted_intervals = sorted(inter_arrivals)
   median_inter_arrival = sorted_intervals[len(sorted_intervals) // 2]
   ```

### Demand Prediction

```python
def predict_demand() -> Dict[str, float]:
    predictions = {}

    for resource_id, timestamps in resource_demand.items():
        if len(timestamps) < 3:
            continue  # Need minimum data points

        # Calculate median inter-arrival time
        inter_arrivals = calculate_inter_arrivals(timestamps)
        median_interval = calculate_median(inter_arrivals)

        # Predict next arrival
        last_arrival = max(timestamps)
        predicted_next = last_arrival + median_interval

        # Check if prediction is within horizon and in future
        time_until_demand = predicted_next - current_time
        if 0 < time_until_demand <= prediction_horizon_minutes * 60:
            predictions[resource_id] = predicted_next

    return predictions
```

### Prewarming Decision

```python
def should_prewarm(resource_id: str) -> bool:
    if resource_id not in predictions:
        return False

    predicted_time = predictions[resource_id]
    current_time = time.time()
    lead_time_seconds = prewarm_lead_time_minutes * 60

    # Prewarm if within lead time window
    time_until_demand = predicted_time - current_time
    return 0 < time_until_demand <= lead_time_seconds
```

## Configuration

### Scheduler Parameters

```python
@dataclass
class PredictivePrewarmingConfig:
    min_requests_for_prediction: int = 10      # Minimum history for prediction
    prediction_horizon_minutes: int = 5        # How far ahead to predict
    prewarm_lead_time_minutes: int = 2         # When to start prewarming
    max_history_size: int = 1000               # Rolling history limit
    pattern_window_hours: int = 24             # Analysis window
```

### Environment Variables

```bash
# Prewarming settings
EDGE_ENABLE_PREWARMING=true
EDGE_PREWARM_MIN_REQUESTS=10
EDGE_PREWARM_HORIZON_MINUTES=5
EDGE_PREWARM_LEAD_TIME_MINUTES=2
```

## Metrics

### Prewarm Hits Total
- **Metric**: `prewarm_hits_total`
- **Type**: Counter
- **Description**: Total number of successful prewarm hits
- **Incremented**: When a prewarmed resource is actually used

### Prewarm Waste Milliseconds
- **Metric**: `prewarm_waste_ms`
- **Type**: Histogram
- **Buckets**: [1000, 5000, 10000, 30000, 60000, 300000]
- **Description**: Time wasted on prewarmed resources that weren't used
- **Recorded**: When cleaning up expired prewarms

## Usage Examples

### Basic Setup

```python
from router_service.edge_router import EdgeConfig, EdgeRouter

config = EdgeConfig(
    core_endpoint="https://core-router.internal:8443",
    edge_id="edge-01",
    shared_secret="secret-key",
    enable_prewarming=True
)

router = EdgeRouter(config)
# Scheduler starts automatically if enabled
```

### Monitoring Prewarm Effectiveness

```python
# Check prewarm hit rate
from metrics.registry import PREWARM_HITS_TOTAL, PREWARM_WASTE_MS

hits = PREWARM_HITS_TOTAL.value
waste_events = len(PREWARM_WASTE_MS._counts) - 1  # Subtract zero bucket

if hits + waste_events > 0:
    hit_rate = hits / (hits + waste_events)
    print(f"Prewarm hit rate: {hit_rate:.2%}")
```

## Performance Characteristics

### Prediction Accuracy
- **Minimum Data**: 10 requests per resource type
- **Accuracy**: Improves with more historical data
- **Robustness**: Median calculation resists outliers
- **Horizon**: 5-minute prediction window

### Resource Overhead
- **Memory**: ~8KB per request in history (timestamp + metadata)
- **CPU**: Minimal background analysis every 30 seconds
- **Storage**: Rolling history prevents unbounded growth

### Hit Rate Optimization
- **Lead Time**: 2-minute prewarming window balances latency vs waste
- **Cleanup**: Automatic cleanup prevents resource leaks
- **Quality-based**: Different resources for different quality levels

## Troubleshooting

### Low Hit Rates

**Symptoms**: High prewarm waste, low hit percentages

**Causes**:
- Insufficient historical data (< 10 requests)
- Inconsistent request patterns
- Too long prewarm lead time
- Prediction horizon too short

**Solutions**:
- Increase `min_requests_for_prediction`
- Adjust `prewarm_lead_time_minutes`
- Extend `prediction_horizon_minutes`

### High Latency

**Symptoms**: Requests still experiencing high latency

**Causes**:
- Prewarming not triggering
- Resources not available when needed
- Prediction timing incorrect

**Solutions**:
- Verify scheduler is running
- Check prediction logs
- Adjust lead time parameters

### Memory Issues

**Symptoms**: High memory usage, slow performance

**Causes**:
- Too much historical data
- Large request metadata

**Solutions**:
- Reduce `max_history_size`
- Implement data compression
- Add history cleanup policies

## Future Enhancements

### Advanced Prediction Models
- **Machine Learning**: Use ML models for more accurate prediction
- **Seasonal Analysis**: Account for daily/weekly patterns
- **Multi-variate**: Consider multiple factors (time, quality, user)

### Resource Management
- **Priority-based**: Prewarm high-priority resources first
- **Cost-aware**: Consider prewarming costs vs benefits
- **Dynamic Scaling**: Scale prewarming based on available resources

### Integration Improvements
- **Health Checks**: Verify prewarmed resources are actually ready
- **Fallback Logic**: Handle prewarming failures gracefully
- **Metrics Export**: Export detailed prewarming analytics
