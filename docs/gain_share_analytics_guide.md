# Gain-Share Cost Analytics Module (GAP-335B)

## Overview

The Gain-Share Cost Analytics module provides comprehensive analytics for cost savings achieved through routing optimization. This module enables:

- **Baseline Frontier Model Repository**: Historical storage and management of frontier model costs
- **Realized Savings Computation**: Calculation of actual savings vs. baseline costs over time
- **Gain-Share Billing**: Support for revenue-sharing arrangements based on achieved savings
- **ROI Reporting**: Detailed analytics for demonstrating value to enterprise customers

## Architecture

### Core Components

#### `GainShareAnalytics` Class
Main service class that orchestrates all gain-share analytics functionality.

#### `BaselineEntry` Dataclass
Represents a single baseline cost comparison entry:
```python
@dataclass
class BaselineEntry:
    timestamp: int
    model: str
    tokens_used: int
    baseline_cost_usd: float
    actual_cost_usd: float
    savings_usd: float
    tenant: str
    adapter: str
```

#### `FrontierModel` Dataclass
Represents a frontier model baseline for cost comparison:
```python
@dataclass
class FrontierModel:
    model_name: str
    cost_per_1k_tokens_usd: float
    capabilities: List[str]
    last_updated: int
```

## Key Features

### 1. Frontier Model Repository

The module maintains a repository of frontier models (highest capability/cost baselines) for cost comparison:

```python
# Update or add a frontier model
analytics.update_frontier_model(
    model_name="premium-model",
    cost_per_1k_tokens_usd=0.03,
    capabilities=["reasoning", "code", "dialog"]
)

# Retrieve frontier model
model = analytics.get_frontier_model("premium-model")
```

### 2. Realized Savings Computation

Calculate savings achieved vs. frontier baseline and record for analytics:

```python
result = analytics.calculate_realized_savings(
    chosen_model="cheap-model",
    tokens_used=1000,
    actual_cost_usd=0.005,
    tenant="enterprise-customer",
    adapter="openai-adapter"
)

print(f"Savings: ${result['savings_usd']:.3f} ({result['savings_pct']:.1f}%)")
```

### 3. Savings Analytics & Reporting

Generate comprehensive savings summaries and gain-share reports:

```python
# Get savings summary for all tenants
summary = analytics.get_savings_summary()

# Get savings summary for specific tenant
tenant_summary = analytics.get_savings_summary(tenant="enterprise-customer")

# Generate gain-share billing report
report = analytics.get_gain_share_report(
    tenant="enterprise-customer",
    gain_share_pct=30.0  # 30% of savings
)
```

## Usage Examples

### Basic Savings Tracking

```python
from router_service.gain_share_analytics import gain_share_analytics

# Record a routing decision and its cost
result = gain_share_analytics.calculate_realized_savings(
    chosen_model="gpt-3.5-turbo",
    tokens_used=1500,
    actual_cost_usd=0.00225,  # $0.0015 per 1k tokens
    tenant="acme-corp",
    adapter="openai"
)

print(f"Achieved ${result['savings_usd']:.4f} in savings")
```

### Frontier Model Management

```python
# Add new frontier model
gain_share_analytics.update_frontier_model(
    model_name="claude-3-opus",
    cost_per_1k_tokens_usd=0.015,
    capabilities=["reasoning", "analysis", "writing"]
)

# Get all frontier models
frontier_models = gain_share_analytics.get_all_frontier_models()
for name, model in frontier_models.items():
    print(f"{name}: ${model.cost_per_1k_tokens_usd:.4f}/1k tokens")
```

### Enterprise Reporting

```python
# Monthly savings report for enterprise customer
summary = gain_share_analytics.get_savings_summary(
    tenant="enterprise-customer",
    since_timestamp=month_start_timestamp
)

# Generate gain-share invoice
gain_share_report = gain_share_analytics.get_gain_share_report(
    tenant="enterprise-customer",
    gain_share_pct=25.0
)

print(f"Total savings: ${summary['total_savings_usd']:.2f}")
print(f"Gain-share amount: ${gain_share_report['gain_share_amount_usd']:.2f}")
```

## Metrics

The module exposes the following Prometheus metrics:

- `gain_share_savings_usd_total`: Counter of total savings achieved (in micro-USD)
- `gain_share_baseline_entries_total`: Gauge of total baseline comparison entries
- `gain_share_avg_savings_pct`: Gauge of average savings percentage across all entries

## Data Persistence

### Frontier Models
Stored in `frontier_models.json` with the following structure:
```json
[
  {
    "model_name": "premium-model",
    "cost_per_1k_tokens_usd": 0.03,
    "capabilities": ["reasoning", "code", "dialog"],
    "last_updated": 1703123456
  }
]
```

### Baseline History
Stored in `baseline_history.jsonl` (JSON Lines format) for efficient appending:
```json
{"timestamp": 1703123456, "model": "gpt-3.5-turbo", "tokens_used": 1000, "baseline_cost_usd": 0.03, "actual_cost_usd": 0.0015, "savings_usd": 0.0285, "tenant": "acme-corp", "adapter": "openai"}
```

## Integration Points

### With Multi-Objective Scorer
The gain-share analytics integrates with the multi-objective scoring engine to track the financial impact of optimization decisions:

```python
from router_service.multi_objective_scorer import multi_objective_scorer
from router_service.gain_share_analytics import gain_share_analytics

# Get optimization recommendation
recommendation = multi_objective_scorer.select_best_option(
    options=available_models,
    weights={"cost": 0.4, "quality": 0.4, "latency": 0.2}
)

# Record the actual cost and savings
result = gain_share_analytics.calculate_realized_savings(
    chosen_model=recommendation["selected_model"],
    tokens_used=actual_tokens,
    actual_cost_usd=actual_cost,
    tenant=tenant_id,
    adapter=adapter_id
)
```

### With Cost Aggregator
Integrates with existing cost tracking infrastructure:

```python
from router_service.cost_aggregator import GLOBAL_COST
from router_service.gain_share_analytics import gain_share_analytics

# Record cost in aggregator
GLOBAL_COST.record(qos="gold", usd=actual_cost_usd, adapter_id=adapter_id)

# Also record in gain-share analytics
gain_share_analytics.calculate_realized_savings(
    chosen_model=chosen_model,
    tokens_used=tokens_used,
    actual_cost_usd=actual_cost_usd,
    tenant=tenant,
    adapter=adapter_id
)
```

## Business Value

### Gain-Share Billing Model
Enable revenue-sharing arrangements where ATP shares a percentage of achieved savings:

- **Enterprise Customers**: Pay base fee + percentage of savings
- **MSPs/Managed Services**: Revenue share on optimization value
- **ROI Demonstration**: Quantify and prove cost optimization value

### Use Cases

1. **Enterprise Cost Optimization**: Track and report savings from model routing optimization
2. **MSP Billing**: Bill customers based on achieved savings percentage
3. **Vendor Negotiations**: Demonstrate optimization value for better vendor terms
4. **Compliance Reporting**: Show cost efficiency improvements for regulatory requirements

## Configuration

The module is designed to work out-of-the-box with sensible defaults but can be customized:

- **Frontier Models**: Update with current market rates and capabilities
- **Gain-Share Percentage**: Configure per customer or contract
- **Reporting Periods**: Customize time windows for analytics
- **Persistence Location**: Configure file paths for data storage

## Testing

Comprehensive test suite covers:
- Savings calculation accuracy
- Data persistence and loading
- Metrics integration
- Edge cases (zero tokens, expensive models, etc.)
- Multi-tenant scenarios
- Large number handling

Run tests with:
```bash
pytest tests/test_gain_share_analytics.py -v
```

## Future Enhancements

Potential future improvements:
- Time-series analysis of savings trends
- Predictive savings modeling
- Integration with external billing systems
- Advanced reporting dashboards
- Machine learning for savings optimization
- Multi-tenant isolation and security</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\gain_share_analytics_guide.md
