# Success Validator Extension Guide

## Overview

GAP-205 introduces a pluggable success validation system that evaluates model responses for format correctness, safety compliance, and quality scoring. This enables quality-aware routing decisions in the autonomous router.

## Architecture

### Core Components

1. **SuccessValidator** (Abstract Base Class)
   - Defines the validation interface
   - Implementations must provide `validate_response()` method
   - Returns `ValidationResult` with format_ok, safety_ok, quality_score

2. **ValidationResult**
   - Container for validation outcomes
   - Includes success property (format_ok AND safety_ok)
   - Contains detailed validation metadata

3. **BaselineQualityScorer** (Reference Implementation)
   - Simple heuristic-based validation
   - Checks format, safety, and calculates quality scores
   - Updates Prometheus metrics

### Integration Points

- **Service Layer**: `router_service/service.py` uses `SUCCESS_VALIDATOR` global instance
- **UCB System**: Success rates from validation feed into `adaptive_stats.py` for model selection
- **Metrics**: `atp_model_success_rate`, `atp_quality_score_avg`, `atp_validations_total`

## Implementing Custom Validators

### Basic Implementation

```python
from router_service.success_validator import SuccessValidator, ValidationResult

class CustomQualityScorer(SuccessValidator):
    def validate_response(self, response_text, prompt, model_name, **kwargs):
        # Your custom validation logic
        format_ok = self._check_format(response_text)
        safety_ok = self._check_safety(response_text)
        quality_score = self._calculate_quality(response_text, prompt)

        return ValidationResult(
            format_ok=format_ok,
            safety_ok=safety_ok,
            quality_score=quality_score,
            details={"custom_metric": 0.85}
        )
```

### Advanced Features

- **Context Awareness**: Use conversation_id, tenant, model_name for contextual validation
- **Model-Specific Logic**: Different validation rules per model type
- **External Services**: Integrate with external safety classifiers or quality APIs
- **Caching**: Implement response caching for performance

### Configuration

Validators can be configured via environment variables or config files:

```python
# Example configuration
VALIDATOR_CONFIG = {
    "strict_safety": True,
    "quality_threshold": 0.7,
    "enable_external_checks": False
}
```

## Metrics and Monitoring

### Key Metrics

- `atp_validations_total`: Total number of validations performed
- `atp_model_success_rate`: Success rate (format_ok AND safety_ok)
- `atp_quality_score_avg`: Average quality score across validations

### Monitoring Queries

```promql
# Success rate by model
rate(atp_model_success_rate[5m])

# Quality score distribution
histogram_quantile(0.95, rate(atp_quality_score_avg[5m]))
```

## Testing

### Unit Tests

```python
def test_custom_validator():
    validator = CustomQualityScorer()
    result = validator.validate_response("test", "prompt", "gpt-4")
    assert result.success == True
    assert result.quality_score >= 0.0
```

### Integration Tests

- Test with actual model responses
- Verify UCB ordering changes with success rates
- Validate metrics emission

## Best Practices

1. **Performance**: Keep validation fast (< 10ms per response)
2. **Accuracy**: Balance false positives/negatives based on use case
3. **Extensibility**: Design for easy addition of new validation criteria
4. **Monitoring**: Implement comprehensive logging and metrics
5. **Fallback**: Always have a baseline validator as fallback

## Future Enhancements

- ML-based quality scoring models
- Multi-language safety validation
- Real-time validation rule updates
- A/B testing of validation strategies
