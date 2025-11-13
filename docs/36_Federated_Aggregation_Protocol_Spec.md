# Federated Routing Prior Aggregation Protocol

## Overview

GAP-220 implements federated learning of routing priors across multiple ATP Router nodes without exposing raw request data. This protocol enables collaborative model improvement while maintaining privacy and security.

## Protocol Goals

1. **Privacy Preservation**: Aggregate routing statistics without exposing individual request data
2. **Secure Aggregation**: Cryptographically secure multi-party computation for statistical aggregation
3. **Convergence Guarantees**: Ensure aggregated priors converge to optimal routing decisions
4. **Fault Tolerance**: Handle node failures and network partitions gracefully
5. **Scalability**: Support federation across hundreds of router nodes

## Core Concepts

### Routing Priors

Routing priors represent learned preferences for model selection based on:
- Historical performance data (latency, quality, cost)
- Request patterns and characteristics
- Regional carbon intensity preferences
- Model capability mappings

### Aggregation Units

#### Model Performance Priors
```python
{
    "model_id": "gpt-4",
    "region": "us-west",
    "quality_tier": "high",
    "latency_percentile": {
        "p50": 850,
        "p95": 1200,
        "p99": 1800
    },
    "success_rate": 0.987,
    "sample_count": 15420
}
```

#### Request Pattern Priors
```python
{
    "request_hash": "a1b2c3d4...",
    "optimal_model": "distilbert",
    "confidence": 0.89,
    "energy_savings_pct": 94.2,
    "sample_count": 892
}
```

#### Regional Carbon Priors
```python
{
    "region": "us-west",
    "carbon_intensity_gco2_per_kwh": 200,
    "routing_penalty_factor": 0.001,
    "last_updated": 1634567890
}
```

## Aggregation Protocol

### Phase 1: Local Statistics Collection

Each router node maintains local statistics:

1. **Model Performance Tracking**
   - Latency distributions per model/region/quality tier
   - Success/failure rates
   - Cost efficiency metrics
   - Energy consumption patterns

2. **Request Pattern Learning**
   - Hash-based request clustering
   - Optimal model identification
   - Confidence scoring
   - Performance validation

3. **Privacy Filtering**
   - Remove personally identifiable information
   - Aggregate sensitive data into statistical bins
   - Apply differential privacy noise (future enhancement)

### Phase 2: Secure Aggregation Protocol

#### Round-Based Aggregation

```
Round Coordinator → All Nodes: "Begin Round N"
All Nodes → Coordinator: Encrypted local statistics
Coordinator → All Nodes: Aggregated results
All Nodes: Update local priors
```

#### Cryptographic Primitives

1. **Homomorphic Encryption**
   - Allows computation on encrypted data
   - Supports sum/average operations without decryption
   - Used for aggregating performance metrics

2. **Secure Multi-Party Computation (MPC)**
   - Distributed computation across multiple nodes
   - No single node sees complete dataset
   - Enables complex statistical operations

3. **Threshold Cryptography**
   - Distributed key generation and signing
   - Requires minimum number of nodes for valid aggregation
   - Prevents single-point-of-failure attacks

#### Aggregation Functions

##### Weighted Average (Latency Metrics)
```
aggregated_p95 = Σ(node_p95 × node_weight) / Σ(node_weight)
where node_weight = min(node_sample_count / 1000, 1.0)
```

##### Success Rate Aggregation
```
aggregated_success_rate = Σ(success_count) / Σ(total_count)
```

##### Confidence-Weighted Model Selection
```
model_score = confidence × sample_count × recency_factor
aggregated_optimal = argmax(model_scores)
```

### Phase 3: Convergence and Validation

#### Convergence Metrics

1. **Prior Stability**
   - Measure change in routing decisions over rounds
   - Target: <5% change between consecutive rounds

2. **Cross-Validation**
   - Holdout validation across federated nodes
   - Compare aggregated vs local-only performance

3. **Diversity Preservation**
   - Ensure aggregated priors don't collapse to single model
   - Maintain exploration across model options

#### Validation Protocol

```python
def validate_aggregation_round(previous_priors, new_priors):
    """Validate aggregation round quality."""
    stability_score = calculate_prior_stability(previous_priors, new_priors)
    diversity_score = calculate_model_diversity(new_priors)
    performance_delta = measure_performance_impact(new_priors)

    return {
        "stability_score": stability_score,  # 0-1, higher better
        "diversity_score": diversity_score,  # 0-1, higher better
        "performance_delta": performance_delta,  # percentage improvement
        "round_quality": (stability_score + diversity_score) / 2
    }
```

## Implementation Status

### Proof of Concept (POC)

A working proof of concept has been implemented in `tools/secure_aggregation_poc.py` that demonstrates:

#### Core Features Implemented
- **Secure Multi-Party Computation**: HMAC-based signatures with timestamp validation
- **Homomorphic Encryption Simulation**: Simplified homomorphic addition for encrypted statistics
- **Differential Privacy**: Random noise injection (±50 units) for privacy preservation
- **Federated Statistics Collection**: Aggregation of routing performance metrics across multiple nodes
- **Privacy Preservation**: Individual node data remains encrypted throughout the process

#### POC Architecture
```python
# Secure Aggregation Node
class SecureAggregatorNode:
    def __init__(self, node_id, signing_key, encryption_key)
    def add_routing_stats(self, stats: RoutingStats)
    def generate_encrypted_contribution(self) -> EncryptedStats
    def verify_encrypted_contribution(self, contribution, key) -> bool

# Coordinator for Aggregation
class SecureAggregatorCoordinator:
    def __init__(self, node_keys, encryption_key)
    def collect_contribution(self, contribution) -> bool
    def perform_aggregation(self) -> Dict[str, Dict[str, float]]
    def get_aggregation_summary(self) -> Dict[str, Any]
```

#### POC Demonstration Output
```
🔐 Secure Aggregation POC for Federated Routing Priors
============================================================

📊 Adding sample routing statistics to nodes...
  ✓ router-1: 3 model-region combinations
  ✓ router-2: 3 model-region combinations
  ✓ router-3: 3 model-region combinations

🔒 Generating encrypted contributions...
  ✓ router-1: contribution verified and collected
  ✓ router-2: contribution verified and collected
  ✓ router-3: contribution verified and collected

📈 Aggregation Results:
  Participating nodes: 3/3

📋 Aggregated Statistics:
  gpt-4:us-west: {total_requests: 319, successful_requests: 329, ...}
  distilbert:us-west: {total_requests: 548, successful_requests: 692, ...}
  llama-3-8b:eu-west: {total_requests: 570, successful_requests: 540, ...}
```

### Metrics Integration

The following metrics have been added to the metrics registry:

#### Federation Metrics
- `federated_rounds_completed`: Counter incremented each time a secure aggregation round completes successfully
- Integrated with existing metrics registry in `metrics/registry.py`
- Exported via `/metrics` endpoint for monitoring and alerting

#### Usage Example
```python
from metrics.registry import FEDERATED_ROUNDS_COMPLETED

# Increment counter when aggregation completes
FEDERATED_ROUNDS_COMPLETED.inc()
```

### Testing and Validation

#### Convergence Tests
- **Single Round Convergence**: Validates aggregation completes with all participating nodes
- **Multi-Round Stability**: Ensures results remain consistent across multiple rounds
- **Differential Privacy Validation**: Confirms noise injection creates expected variation
- **Privacy Preservation**: Verifies individual node data cannot be reconstructed
- **Partial Participation**: Tests aggregation works with subset of available nodes

#### Test Coverage
```python
class TestSecureAggregationConvergence:
    def test_single_round_convergence(self, encryption_key, node_keys, sample_routing_stats)
    def test_multi_round_convergence_stability(self, encryption_key, node_keys)
    def test_differential_privacy_noise_injection(self, encryption_key, node_keys)
    def test_derived_metrics_accuracy(self, encryption_key, node_keys)
    def test_privacy_preservation(self, encryption_key, node_keys, sample_routing_stats)
    def test_convergence_with_partial_participation(self, encryption_key, node_keys)
    def test_aggregation_consistency_across_runs(self, encryption_key, node_keys)
```

## Security Considerations

### Threat Model

1. **Eavesdropping**: Network traffic interception
2. **Malicious Nodes**: Compromised or adversarial participants
3. **Inference Attacks**: Reconstructing individual requests from aggregates
4. **Sybil Attacks**: Fake nodes attempting to influence aggregation

### Security Controls

#### Authentication & Authorization
- Mutual TLS for node-to-node communication
- Certificate-based node identity verification
- Regular key rotation and certificate renewal

#### Data Protection
- End-to-end encryption for all aggregation traffic
- Homomorphic encryption for sensitive metrics
- Differential privacy for statistical disclosures

#### Attack Mitigation
- Outlier detection and filtering
- Byzantine fault tolerance algorithms
- Rate limiting and abuse detection

## Implementation Architecture

### Core Components

#### AggregationCoordinator
```python
class AggregationCoordinator:
    def __init__(self, node_registry, crypto_provider):
        self.nodes = node_registry
        self.crypto = crypto_provider
        self.current_round = 0
        self.round_state = {}

    def initiate_round(self) -> RoundContext:
        """Begin new aggregation round."""

    def collect_encrypted_stats(self, node_id, encrypted_stats) -> bool:
        """Collect encrypted statistics from node."""

    def aggregate_and_distribute(self) -> AggregatedPriors:
        """Perform secure aggregation and distribute results."""
```

#### RoutingPriorAggregator
```python
class RoutingPriorAggregator:
    def __init__(self, local_stats_provider, federation_client):
        self.local_stats = local_stats_provider
        self.federation = federation_client

    def generate_local_contribution(self) -> EncryptedStats:
        """Generate encrypted local statistics for federation."""

    def apply_aggregated_priors(self, aggregated_priors):
        """Apply federated priors to local routing decisions."""

    def measure_impact(self) -> PerformanceMetrics:
        """Measure impact of federated learning on routing performance."""
```

### Data Flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Router Node   │───▶│Aggregation Coord│───▶│   All Nodes     │
│                 │    │                  │    │                 │
│ Collect Local   │    │ Secure           │    │ Update Priors   │
│ Statistics      │    │ Aggregation      │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ▲                       │                       │
         │                       ▼                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌──────────────────┐
                    │  Updated         │
                    │  Routing         │
                    │  Decisions       │
                    └──────────────────┘
```

## Performance Characteristics

### Scalability Targets

- **Node Count**: Support 100-1000 federated nodes
- **Round Frequency**: 15-60 minute intervals
- **Aggregation Latency**: <30 seconds for 100 nodes
- **Storage Overhead**: <10MB per node for federation state

### Resource Requirements

#### Memory
- Local statistics: ~50MB per node
- Federation state: ~20MB per node
- Aggregation working set: ~100MB coordinator

#### Network
- Per-round bandwidth: ~1MB per node
- Encryption overhead: ~2x message size
- Round-trip latency tolerance: <10 seconds

## Monitoring and Observability

### Key Metrics

#### Federation Health
- `federation_nodes_active`: Number of active federation nodes
- `federation_round_duration_seconds`: Time to complete aggregation round
- `federation_participation_rate`: Percentage of nodes participating
- `federated_rounds_completed`: Counter of successfully completed aggregation rounds

#### Aggregation Quality
- `federation_prior_stability`: Change in routing priors between rounds
- `federation_model_diversity`: Number of models in aggregated priors
- `federation_convergence_rate`: Rate of convergence to optimal priors

#### Security Metrics
- `federation_failed_authentications`: Authentication failure count
- `federation_encryption_errors`: Encryption/decryption error count
- `federation_malformed_messages`: Invalid message detection

### Alerting Rules

```yaml
# Federation health alerts
- alert: FederationRoundTimeout
  expr: federation_round_duration_seconds > 300
  for: 5m

- alert: LowParticipationRate
  expr: federation_participation_rate < 0.8
  for: 10m

- alert: PriorInstability
  expr: federation_prior_stability < 0.95
  for: 15m
```

## Deployment and Operations

### Rollout Strategy

1. **Pilot Phase**: 3-5 nodes with manual monitoring
2. **Beta Phase**: 20-50 nodes with automated monitoring
3. **Production**: Full federation with comprehensive monitoring

### Configuration Management

```yaml
federation:
  enabled: true
  round_interval_minutes: 30
  max_round_duration_seconds: 300
  min_participation_threshold: 0.8
  crypto:
    key_rotation_hours: 24
    encryption_algorithm: "AES-256-GCM"
  aggregation:
    outlier_threshold: 2.0
    minimum_sample_size: 100
```

### Troubleshooting Guide

#### Common Issues

1. **Round Timeouts**
   - Check network connectivity between nodes
   - Verify coordinator resource utilization
   - Review encryption performance

2. **Low Participation**
   - Check node health and availability
   - Verify authentication certificates
   - Review network firewall rules

3. **Prior Instability**
   - Validate local statistics quality
   - Check for outlier data points
   - Review aggregation algorithm parameters

## Future Enhancements

### Advanced Features

1. **Differential Privacy Integration**
   - Add noise to local statistics before aggregation
   - Balance privacy vs accuracy trade-offs

2. **Adaptive Aggregation**
   - Dynamic round frequency based on data volatility
   - Context-aware aggregation weights

3. **Cross-Region Federation**
   - Geographic load balancing
   - Regional carbon-aware routing

4. **Model-Specific Priors**
   - Fine-grained priors per model family
   - Transfer learning across similar models

### Research Directions

1. **Federated Reinforcement Learning**
   - Distributed Q-learning for routing decisions
   - Privacy-preserving policy gradients

2. **Blockchain-Based Coordination**
   - Decentralized aggregation coordination
   - Immutable audit trails

3. **Zero-Knowledge Proofs**
   - Prove statistical properties without revealing data
   - Enhanced privacy guarantees

## References

- **GAP-024**: Multi-region deployment architecture
- **GAP-107**: Distributed statistics collection
- **GAP-116C**: Persona federation schema
- **Secure Aggregation**: Bonawitz et al. "Practical Secure Aggregation for Privacy-Preserving Machine Learning"
- **Federated Learning**: McMahan et al. "Communication-Efficient Learning of Deep Networks from Decentralized Data"</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\36_Federated_Aggregation_Protocol_Spec.md
