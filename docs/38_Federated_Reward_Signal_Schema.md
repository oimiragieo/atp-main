# Federated Reward Signal Schema (GAP-371)

## Overview

The Federated Reward Signal Schema defines the structure for anonymous cluster statistics aggregation across routers in the ATP system. This schema enables privacy-preserving cross-tenant reinforcement signals by allowing routers to share aggregated performance metrics without exposing individual tenant data.

## Schema Version

**Current Version:** 1

The schema version is included in all federated reward signals to ensure compatibility and support future schema evolution.

## Signal Structure

### Required Fields

- `schema_version` (integer): Schema version for compatibility (currently 1)
- `aggregation_round` (integer): Federated learning round identifier (must be positive)
- `cluster_hash` (string): Anonymous cluster identifier (SHA-256 hash, minimum 16 characters)
- `reward_signals` (object): Aggregated reward signals by model/task combination
- `participant_count` (integer): Number of routers contributing to this signal (must be positive)
- `timestamp` (string): ISO 8601 timestamp of signal creation

### Optional Fields

- `privacy_budget_used` (number): Privacy budget consumed for this aggregation (non-negative)
- `noise_scale` (number): Differential privacy noise scale applied (non-negative)

## Reward Signals Format

The `reward_signals` object contains aggregated metrics for different model/task combinations. Each key represents a combination (e.g., "gpt-4:chat", "claude-3:code"), and each value contains:

### Required Reward Signal Fields

- `success_rate` (number): Fraction of successful requests (0.0 to 1.0)
- `avg_latency` (number): Average latency in seconds (non-negative)
- `total_samples` (integer): Total number of samples aggregated (positive)

### Optional Reward Signal Fields

- `quality_score` (number): Average quality score (0.0 to 1.0)
- `cost_efficiency` (number): Cost per token efficiency metric (non-negative)

## Privacy Protection

### Cluster Anonymization

Clusters are identified using SHA-256 hashes instead of plain identifiers:

```python
import hashlib

def create_cluster_hash(cluster_id: str, salt: str = "") -> str:
    content = f"{cluster_id}:{salt}"
    return hashlib.sha256(content.encode()).hexdigest()
```

### Aggregation Requirements

- Signals from the same cluster and aggregation round can be aggregated
- Weighted averaging is used based on sample counts
- Privacy budget tracking ensures differential privacy guarantees

## Usage Examples

### Creating a Federated Reward Signal

```python
from router_service.federated_rewards import FederatedRewardSignal

# Create reward signals for different model/task combinations
reward_signals = {
    "gpt-4:chat": {
        "success_rate": 0.95,
        "avg_latency": 1.2,
        "total_samples": 1000,
        "quality_score": 0.88
    },
    "claude-3:code": {
        "success_rate": 0.92,
        "avg_latency": 2.1,
        "total_samples": 500,
        "cost_efficiency": 0.003
    }
}

signal = FederatedRewardSignal(
    aggregation_round=1,
    cluster_hash="a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890",
    reward_signals=reward_signals,
    participant_count=5,
    privacy_budget_used=0.1,
    noise_scale=0.5
)
```

### Validating a Signal

```python
from router_service.federated_rewards import validate_federated_reward_signal

data = signal.to_dict()
errors = validate_federated_reward_signal(data)

if errors:
    print("Validation errors:", errors)
else:
    print("Signal is valid")
```

### Aggregating Multiple Signals

```python
from router_service.federated_rewards import aggregate_reward_signals

signals = [signal1, signal2, signal3]  # From same cluster and round
aggregated = aggregate_reward_signals(signals)

if aggregated:
    print(f"Aggregated {aggregated.participant_count} participants")
else:
    print("Signals are incompatible for aggregation")
```

## JSON Schema

The federated reward signal follows this JSON Schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "FederatedRewardSignal",
  "type": "object",
  "required": [
    "schema_version",
    "aggregation_round",
    "cluster_hash",
    "reward_signals",
    "participant_count",
    "timestamp"
  ],
  "properties": {
    "schema_version": {
      "type": "integer",
      "const": 1,
      "description": "Schema version for compatibility"
    },
    "aggregation_round": {
      "type": "integer",
      "minimum": 1,
      "description": "Federated learning round identifier"
    },
    "cluster_hash": {
      "type": "string",
      "minLength": 16,
      "maxLength": 64,
      "description": "Anonymous cluster identifier (SHA-256 hash)"
    },
    "reward_signals": {
      "type": "object",
      "description": "Aggregated reward signals by model/task combination",
      "patternProperties": {
        ".*": {
          "type": "object",
          "required": ["success_rate", "avg_latency", "total_samples"],
          "properties": {
            "success_rate": {
              "type": "number",
              "minimum": 0.0,
              "maximum": 1.0,
              "description": "Fraction of successful requests"
            },
            "avg_latency": {
              "type": "number",
              "minimum": 0.0,
              "description": "Average latency in seconds"
            },
            "total_samples": {
              "type": "integer",
              "minimum": 1,
              "description": "Total number of samples aggregated"
            },
            "quality_score": {
              "type": "number",
              "minimum": 0.0,
              "maximum": 1.0,
              "description": "Average quality score (optional)"
            },
            "cost_efficiency": {
              "type": "number",
              "minimum": 0.0,
              "description": "Cost per token efficiency metric"
            }
          }
        }
      },
      "additionalProperties": false
    },
    "participant_count": {
      "type": "integer",
      "minimum": 1,
      "description": "Number of routers contributing to this signal"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of signal creation"
    },
    "privacy_budget_used": {
      "type": "number",
      "minimum": 0.0,
      "description": "Privacy budget consumed for this aggregation"
    },
    "noise_scale": {
      "type": "number",
      "minimum": 0.0,
      "description": "Differential privacy noise scale applied"
    }
  }
}
```

## Metrics

The implementation tracks the following metric:

- `federated_reward_batches_total`: Counter for the total number of federated reward signal batches created

## Dependencies

- **GAP-220**: Federated routing prior aggregator (provides foundational secure aggregation)
- **GAP-372**: Secure aggregation protocol (extends this schema with cryptographic protections)
- **Future GAP-373**: Reinforcement prior update integration (will consume these signals)

## Security Considerations

1. **Cluster Anonymization**: SHA-256 hashing prevents cluster identification
2. **Differential Privacy**: Optional noise injection for additional privacy
3. **Privacy Budget Tracking**: Monitors privacy loss across aggregations
4. **Input Validation**: Comprehensive schema validation prevents malformed data
5. **Aggregation Safety**: Only compatible signals (same cluster/round) can be aggregated

## Future Extensions

- Schema versioning for backward compatibility
- Additional reward signal types (e.g., fairness metrics, custom KPIs)
- Compression for efficient transmission
- Digital signatures for authenticity verification
