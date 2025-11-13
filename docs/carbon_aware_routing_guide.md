# Carbon-Aware Edge Routing Guide

## Overview

GAP-364 implements carbon-aware routing in the ATP Edge Router Service to reduce carbon emissions by routing requests to regions with lower carbon intensity when possible.

## Features

- **Regional Carbon Intensity Tracking**: Fetches real-time carbon intensity data for different regions
- **Automatic Routing Influence**: Adds carbon context to requests for core router decision making
- **Fallback to Demo Data**: Uses demo carbon intensity data when API is unavailable
- **Configurable**: Can be enabled/disabled and configured per deployment
- **Metrics Integration**: Tracks carbon-aware routing decisions

## Architecture

### Core Components

1. **CarbonIntensityTracker**: Fetches and caches carbon intensity data by region
2. **Edge Router Integration**: Adds carbon context to outgoing requests
3. **Metrics**: Prometheus-compatible metrics for monitoring routing decisions
4. **Configuration**: Runtime configuration for enabling/disabling carbon-aware routing

### Carbon Intensity Data Sources

The system supports multiple data sources:

- **Electricity Maps API**: Real-time carbon intensity data (requires API key)
- **Demo Data**: Fallback data for testing and development
- **Caching**: Carbon data is cached to reduce API calls and improve performance

## Configuration

Add carbon-aware routing settings to your `EdgeConfig`:

```python
@dataclass
class EdgeConfig:
    # ... existing config ...

    # Carbon-aware routing settings
    enable_carbon_aware_routing: bool = True  # Enable carbon-aware routing
    carbon_api_key: Optional[str] = None  # API key for carbon intensity service
    carbon_cache_ttl_seconds: int = 3600  # Carbon data cache TTL (1 hour)
```

### Environment Variables

```bash
# Enable carbon-aware routing
ENABLE_CARBON_AWARE_ROUTING=1

# Carbon intensity API key (optional)
CARBON_API_KEY=your_api_key_here

# Carbon data cache TTL
CARBON_CACHE_TTL_SECONDS=3600
```

## Usage

### Basic Setup

```python
from router_service.edge_router import EdgeRouter, EdgeConfig

config = EdgeConfig(
    core_endpoint="https://core-router.internal:8443",
    edge_id="edge-01",
    shared_secret="your-secret",
    enable_carbon_aware_routing=True,
    carbon_api_key="your-api-key"  # Optional
)

router = EdgeRouter(config)
```

### Request Flow with Carbon Awareness

When carbon-aware routing is enabled:

1. **Region Detection**: Extract region from request data (default: "us-west")
2. **Carbon Data Fetch**: Get current carbon intensity for the region
3. **Context Enrichment**: Add carbon context to request
4. **Core Routing**: Core router uses carbon data for routing decisions

```python
# Request with region specification
request_data = {
    "prompt": "Analyze this data...",
    "region": "eu-west",  # Will fetch carbon intensity for EU West
    "quality": "balanced"
}

# Edge router automatically adds carbon context
response = await router.relay_request(request_data)
```

### Carbon Context Format

The edge router adds carbon context to requests:

```json
{
  "prompt": "Analyze this data...",
  "region": "eu-west",
  "carbon_context": {
    "region": "eu-west",
    "intensity_gco2_per_kwh": 150.0,
    "timestamp": "2024-01-15T10:30:00Z",
    "source": "electricitymaps",
    "confidence": 0.95
  }
}
```

## Metrics

### Carbon-Aware Routing Metrics

- `carbon_aware_routing_decisions_total`: Counter of requests with carbon context added
- `carbon_api_requests_total`: Counter of API requests to carbon intensity service
- `carbon_api_errors_total`: Counter of API errors from carbon intensity service
- `carbon_intensity_weight`: Gauge of current carbon intensity weight in routing decisions

### Monitoring Queries

```promql
# Carbon-aware routing decisions per minute
rate(carbon_aware_routing_decisions_total[5m])

# Carbon API error rate
rate(carbon_api_errors_total[5m]) / rate(carbon_api_requests_total[5m])

# Current carbon intensity by region (if labeled)
carbon_intensity_weight{region="eu-west"}
```

## Testing

### Unit Tests

```bash
# Run carbon intensity tracker tests
pytest tests/test_carbon_intensity_tracker.py -v

# Run edge router carbon-aware routing tests
pytest tests/test_edge_router.py::TestCarbonAwareEdgeRouting -v
```

### Integration Tests

```python
import pytest
from router_service.edge_router import EdgeRouter, EdgeConfig

@pytest.mark.asyncio
async def test_carbon_aware_routing_integration():
    """Test full carbon-aware routing integration."""
    config = EdgeConfig(
        core_endpoint="http://test-core",
        enable_carbon_aware_routing=True
    )

    router = EdgeRouter(config)

    # Test request
    request = {"prompt": "test", "region": "us-west"}

    # Process through carbon-aware routing
    await router._apply_carbon_aware_routing(request)

    # Verify carbon context added
    assert "carbon_context" in request
    assert request["carbon_context"]["region"] == "us-west"
```

## Troubleshooting

### Common Issues

1. **No Carbon Data Available**
   - Check API key configuration
   - Verify network connectivity to carbon intensity service
   - Check service status/logs

2. **High API Error Rate**
   - Monitor `carbon_api_errors_total` metric
   - Check API key validity
   - Consider increasing cache TTL

3. **Performance Impact**
   - Carbon data fetching is async and cached
   - API calls are made only when cache expires
   - Disable if performance is critical: `enable_carbon_aware_routing=False`

### Debug Logging

Enable debug logging to troubleshoot carbon-aware routing:

```python
import logging
logging.getLogger('router_service.edge_router').setLevel(logging.DEBUG)
logging.getLogger('router_service.carbon_intensity_tracker').setLevel(logging.DEBUG)
```

## API Reference

### CarbonIntensityTracker

```python
class CarbonIntensityTracker:
    async def get_carbon_intensity(self, region: str) -> Optional[CarbonIntensityData]:
        """Get carbon intensity data for a region."""
        pass
```

### CarbonIntensityData

```python
@dataclass
class CarbonIntensityData:
    region: str
    intensity_gco2_per_kwh: float
    timestamp: datetime
    source: str
    confidence: float
```

## Future Enhancements

- **Dynamic Routing**: Route to lowest carbon region automatically
- **Carbon Budgeting**: Track and limit carbon emissions per tenant
- **Predictive Carbon**: Use weather/renewable forecasts for routing decisions
- **Multi-Region Optimization**: Consider latency vs carbon trade-offs</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\carbon_aware_routing_guide.md
