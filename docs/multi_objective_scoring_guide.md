# Multi-Objective Scoring Engine Guide

## Overview

The Multi-Objective Scoring Engine (GAP-335A) provides sophisticated optimization for routing decisions by considering multiple competing objectives simultaneously. This enables intelligent trade-off analysis between cost, latency, quality, and environmental impact.

## Key Features

- **Four Objective Dimensions**: Cost, latency, quality score, and carbon intensity
- **Dual Optimization Approaches**: Pareto frontier analysis and weighted scalarization
- **Flexible Weight Configuration**: Customizable objective importance
- **Comprehensive Metrics**: Built-in telemetry for optimization insights

## Objective Dimensions

### Cost (Minimize)
- **Unit**: USD per request
- **Source**: Cost aggregator integration
- **Impact**: Direct financial cost of routing decision

### Latency (Minimize)
- **Unit**: Milliseconds
- **Source**: Performance monitoring
- **Impact**: User experience and SLA compliance

### Quality Score (Maximize)
- **Unit**: 0.0 to 1.0
- **Source**: Consensus scoring and self-consistency sampling
- **Impact**: Response accuracy and reliability

### Carbon Intensity (Minimize)
- **Unit**: gCO2e/kWh
- **Source**: Carbon intensity tracker
- **Impact**: Environmental sustainability

## Optimization Approaches

### Pareto Frontier Analysis

Identifies non-dominated solutions where no single option is better in all objectives.

```python
from router_service.multi_objective_scorer import multi_objective_scorer, ObjectiveVector, ScoredOption

# Create routing options
options = [
    ScoredOption("gpt-4", ObjectiveVector(cost=0.10, latency=2000, quality_score=0.95, carbon_intensity=300), {}),
    ScoredOption("claude-3", ObjectiveVector(cost=0.08, latency=1800, quality_score=0.92, carbon_intensity=280), {}),
    ScoredOption("llama-3-70b", ObjectiveVector(cost=0.03, latency=1200, quality_score=0.88, carbon_intensity=200), {}),
]

# Find Pareto-optimal options
pareto_frontier = multi_objective_scorer.score_options(options, use_pareto=True)
print(f"Pareto frontier size: {len(pareto_frontier)}")
```

### Weighted Scalarization

Combines multiple objectives into a single score using configurable weights.

```python
# Configure weights (must sum to 1.0)
multi_objective_scorer.set_weights(
    cost=0.3,           # 30% weight on cost minimization
    latency=0.2,        # 20% weight on latency minimization
    quality_score=0.4,  # 40% weight on quality maximization
    carbon_intensity=0.1 # 10% weight on carbon minimization
)

# Score options using scalarization
scored_options = multi_objective_scorer.score_options(options, use_pareto=False)
best_option = scored_options[0]  # Highest scalar score
```

## Selection Strategies

### Pareto Frontier Selection

When using Pareto frontier analysis, choose from multiple optimal options:

```python
# Select first option (simplest)
best = multi_objective_scorer.select_best_option(options, selection_strategy="first")

# Select closest to ideal point
best = multi_objective_scorer.select_best_option(options, selection_strategy="closest_to_ideal")

# Random selection from frontier
best = multi_objective_scorer.select_best_option(options, selection_strategy="random")
```

## Integration Examples

### With Existing Cost Infrastructure

```python
from router_service.cost_aggregator import GLOBAL_COST
from router_service.carbon_energy_attribution import carbon_attribution

# Get current cost snapshot
cost_snapshot = GLOBAL_COST.snapshot()

# Calculate carbon impact for a model
carbon_data = carbon_attribution.calculate_co2e_emissions(
    energy_kwh=0.002,
    region="us-west"
)

# Create objective vector
objectives = ObjectiveVector(
    cost=cost_snapshot.get("gold", 0.05),
    latency=1500,  # measured latency
    quality_score=0.89,  # from consensus scoring
    carbon_intensity=carbon_data
)
```

### With Consensus Scoring

```python
from router_service.consensus import jaccard_agreement
from router_service.evidence import SelfConsistencySampler

# Calculate quality score from consensus
responses = ["Response A", "Response B", "Response C"]
consensus_score = jaccard_agreement(responses)

# Or use self-consistency sampling
sampler = SelfConsistencySampler()
result = sampler.sample_consistent_response("prompt", inference_fn)
quality_score = result.consensus_score
```

## Metrics and Monitoring

The engine automatically tracks:

- `multi_objective_scoring_invocations_total`: Total scoring operations
- `multi_objective_frontier_size`: Distribution of Pareto frontier sizes
- `multi_objective_pareto_dominated_total`: Count of dominated options filtered

## Weight Tuning Guidelines

### Cost-Optimized Routing
```python
multi_objective_scorer.set_weights(cost=0.6, latency=0.2, quality_score=0.15, carbon_intensity=0.05)
```

### Quality-First Routing
```python
multi_objective_scorer.set_weights(cost=0.1, latency=0.2, quality_score=0.6, carbon_intensity=0.1)
```

### Sustainability-Focused Routing
```python
multi_objective_scorer.set_weights(cost=0.2, latency=0.2, quality_score=0.2, carbon_intensity=0.4)
```

### Balanced Approach (Default)
```python
multi_objective_scorer.set_weights(cost=0.25, latency=0.25, quality_score=0.25, carbon_intensity=0.25)
```

## Performance Considerations

- **Pareto Frontier**: O(n²) complexity for dominance checking
- **Scalarization**: O(n) complexity, faster for large option sets
- **Memory Usage**: Minimal, stores only objective vectors and metadata

## Best Practices

1. **Normalize Objectives**: Ensure objectives are on comparable scales
2. **Weight Validation**: Always validate that weights sum to 1.0
3. **Regular Retuning**: Re-evaluate weights based on business priorities
4. **Monitor Trade-offs**: Use metrics to understand optimization behavior
5. **A/B Testing**: Compare different weight configurations in production

## Troubleshooting

### Common Issues

**Empty Pareto Frontier**: Check for invalid objective values or all options being dominated
**Unexpected Rankings**: Verify weight configuration and objective normalization
**Performance Issues**: Consider scalarization for large option sets (>100 options)

### Validation

```python
# Validate objective vector
try:
    obj = ObjectiveVector(cost=1.0, latency=100.0, quality_score=0.8, carbon_intensity=200.0)
except ValueError as e:
    print(f"Invalid objectives: {e}")

# Test dominance relationships
assert obj1.dominates(obj2)  # Should be True if obj1 actually dominates obj2
```

## Future Enhancements

- **Dynamic Weight Adjustment**: Machine learning-based weight optimization
- **Multi-Criteria Decision Analysis**: Integration with AHP, TOPSIS methods
- **Constraint Handling**: Support for hard constraints on objectives
- **Historical Learning**: Weight adaptation based on user feedback
- **Interactive Exploration**: Web UI for weight sensitivity analysis</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\multi_objective_scoring_guide.md
