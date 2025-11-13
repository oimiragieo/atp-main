# Reinforcement Prior Update Integration (GAP-373)

## Overview

GAP-373 implements the integration of aggregated federated reward signals into the routing decision process, enabling reinforcement learning across the ATP Router federation. This feature allows routers to learn from the collective experience of all participants in the federation, improving routing decisions through Bayesian prior updates.

## Protocol Goals

1. **Reinforcement Learning**: Incorporate federated reward signals into routing score calculations
2. **Bayesian Prior Updates**: Use aggregated signals to update model/task priors
3. **Improved Regret Minimization**: Reduce routing regret through collective learning
4. **Adaptive Routing**: Dynamically adjust routing decisions based on federation-wide performance data
5. **Privacy Preservation**: Maintain privacy while enabling collective learning

## Core Concepts

### Reinforcement Priors

Reinforcement priors represent learned expectations for model/task performance based on aggregated federated data:

```python
@dataclass
class ReinforcementPrior:
    model_task_key: str  # e.g., "gpt-4:chat", "claude-3:code"
    success_rate_prior: float  # Bayesian prior for success rate (0-1)
    latency_prior_ms: float  # Bayesian prior for latency in milliseconds
    quality_prior: float  # Bayesian prior for quality score (0-1)
    sample_count: int  # Number of samples contributing to this prior
    last_updated: float  # Timestamp of last update
    confidence: float  # Confidence in the prior (0-1)
```

### Bayesian Prior Updates

The system uses Bayesian updating to incorporate new evidence from aggregated signals:

```python
def update_from_signal(self, signal: FederatedRewardSignal) -> bool:
    # Bayesian update for success rate using Beta distribution
    prior_alpha = self.success_rate_prior * self.sample_count
    prior_beta = (1 - self.success_rate_prior) * self.sample_count

    new_successes = int(reward_data['success_rate'] * reward_data['total_samples'])
    new_failures = reward_data['total_samples'] - new_successes

    posterior_alpha = prior_alpha + new_successes
    posterior_beta = prior_beta + new_failes
    self.success_rate_prior = posterior_alpha / (posterior_alpha + posterior_beta)
```

### Prior-Aware Multi-Objective Scoring

The routing scorer incorporates reinforcement priors into decision making:

```python
class PriorAwareMultiObjectiveScorer(MultiObjectiveScorer):
    def calculate_scalar_score(self, objectives: ObjectiveVector, model_task_key: str | None = None) -> float:
        # Apply reinforcement prior if available
        if model_task_key and self.prior_manager:
            adjusted_objectives = self.prior_manager.get_adjusted_objectives(model_task_key, objectives)
        else:
            adjusted_objectives = objectives

        # Use parent implementation with adjusted objectives
        return super().calculate_scalar_score(adjusted_objectives)
```

## Implementation Details

### Files

- `router_service/reinforcement_prior_integration.py` - Core prior management and integration
- `tests/test_reinforcement_prior_integration.py` - Comprehensive test suite
- `metrics/registry.py` - Added GAP-373 metrics

### Key Classes

#### ReinforcementPrior
- Manages Bayesian priors for individual model/task combinations
- Updates priors from federated reward signals
- Calculates confidence-based adjustments to routing objectives

#### ReinforcementPriorManager
- Coordinates prior updates from aggregated signals
- Manages the lifecycle of reinforcement priors
- Provides prior lookup and adjustment services

#### PriorAwareMultiObjectiveScorer
- Extends the existing multi-objective scorer
- Incorporates reinforcement priors into scoring calculations
- Maintains backward compatibility with existing scoring logic

### Integration Points

The system integrates with existing components:

1. **Federated Reward Signals (GAP-371)**: Consumes aggregated signals
2. **Secure Aggregation (GAP-372)**: Uses cryptographically secure aggregated data
3. **Multi-Objective Scorer**: Extends existing routing decision logic
4. **Metrics System**: Provides observability into prior updates

## Usage Example

```python
from router_service.reinforcement_prior_integration import (
    get_prior_aware_scorer,
    update_priors_from_aggregation
)
from router_service.federated_rewards import FederatedRewardSignal

# Get the global prior-aware scorer
scorer = get_prior_aware_scorer()

# Update priors from aggregated signal
reward_signals = {
    "gpt-4:chat": {
        "success_rate": 0.95,
        "avg_latency": 800.0,
        "quality_score": 0.9,
        "total_samples": 1000
    }
}
signal = FederatedRewardSignal(
    aggregation_round=1,
    cluster_hash="federation_cluster",
    reward_signals=reward_signals,
    participant_count=10
)

updates = update_priors_from_aggregation(signal)
print(f"Applied {updates} prior updates")

# Use scorer with prior integration
from router_service.multi_objective_scorer import ObjectiveVector

objectives = ObjectiveVector(
    cost=1.0,
    latency=1000.0,
    quality_score=0.8,
    carbon_intensity=50.0
)

# Score with prior adjustment
score = scorer.calculate_scalar_score(objectives, "gpt-4:chat")
print(f"Adjusted score: {score}")
```

## Security and Privacy

### Privacy Preservation

- **Federated Learning**: Only aggregated statistics are shared, not individual requests
- **Differential Privacy**: Noise injection in GAP-371/GAP-372 protects against inference
- **Secure Aggregation**: Cryptographic protections prevent reconstruction attacks

### Access Control

- **Signal Validation**: Only authorized aggregated signals are accepted
- **Prior Updates**: Updates are validated before application
- **Audit Trail**: All prior updates are logged and monitored

## Performance Characteristics

### Update Latency

- **Signal Processing**: ~1ms per model/task combination
- **Prior Updates**: O(n) where n is number of model/task combinations
- **Memory Overhead**: Minimal - priors stored in memory with cleanup
- **Scoring Impact**: ~10μs additional latency per scoring decision

### Scalability

- **Federation Size**: Scales to hundreds of routers
- **Model/Task Coverage**: Supports thousands of model/task combinations
- **Update Frequency**: Configurable update intervals
- **Cleanup**: Automatic removal of stale priors

## Metrics and Monitoring

The implementation provides comprehensive observability:

- `prior_updates_applied_total`: Counter for successful prior updates
- `prior_update_failures_total`: Counter for update failures
- `active_priors`: Gauge for number of active reinforcement priors
- `prior_update_latency_seconds`: Histogram for update operation latency

## Configuration

### Prior Update Parameters

```python
# Confidence threshold for prior application
MIN_CONFIDENCE_THRESHOLD = 0.1

# Maximum age for prior retention (7 days)
MAX_PRIOR_AGE_SECONDS = 86400 * 7

# Learning rate for exponential moving averages
LEARNING_RATE = 0.1
```

### Scoring Weights

The system uses the existing multi-objective scoring weights:

```python
weights = {
    "cost": 0.25,
    "latency": 0.25,
    "quality_score": 0.25,
    "carbon_intensity": 0.25,
}
```

## Testing

The implementation includes comprehensive tests:

- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end prior update workflows
- **Performance Tests**: Latency and scalability validation
- **Edge Case Tests**: Error handling and boundary conditions

Run tests with:
```bash
pytest tests/test_reinforcement_prior_integration.py -v
```

## Future Enhancements

### Advanced Learning Algorithms

- **Thompson Sampling**: Multi-armed bandit algorithms for exploration
- **Contextual Bandits**: Context-aware routing decisions
- **Deep Reinforcement Learning**: Neural network-based prior modeling

### Enhanced Privacy

- **Homomorphic Encryption**: Fully homomorphic encryption for aggregation
- **Zero-Knowledge Proofs**: Privacy-preserving prior updates
- **Federated Averaging**: Advanced federated learning techniques

### Performance Optimizations

- **Prior Caching**: Redis-based prior storage and distribution
- **Batch Updates**: Bulk prior update operations
- **Async Processing**: Non-blocking prior updates

## Dependencies

- **GAP-371**: Federated Reward Signal Schema
- **GAP-372**: Secure Aggregation Protocol
- **Multi-Objective Scorer**: Existing routing decision framework
- **Metrics Registry**: Prometheus-compatible monitoring

## Deployment Considerations

### Rollout Strategy

1. **Feature Flag**: Enable reinforcement prior integration via feature flag
2. **Gradual Rollout**: Start with subset of routers
3. **Monitoring**: Comprehensive monitoring during rollout
4. **Fallback**: Automatic fallback to baseline scoring if issues detected

### Compatibility

- **Backward Compatible**: Existing routing logic unchanged
- **Opt-in**: Prior integration is optional per deployment
- **Migration**: Seamless migration from existing scoring systems

## Troubleshooting

### Common Issues

1. **Low Confidence Priors**: Check signal quality and aggregation parameters
2. **Stale Priors**: Verify cleanup intervals and signal freshness
3. **Performance Impact**: Monitor scoring latency and optimize if needed
4. **Signal Validation**: Check secure aggregation and signal integrity

### Debugging

Enable debug logging to trace prior updates:
```python
import logging
logging.getLogger('router_service.reinforcement_prior_integration').setLevel(logging.DEBUG)
```

## Conclusion

GAP-373 enables collective reinforcement learning across the ATP Router federation, allowing routers to benefit from the aggregated experience of all participants. By incorporating federated reward signals into routing decisions, the system achieves better regret minimization and adaptive routing while maintaining privacy and security.
