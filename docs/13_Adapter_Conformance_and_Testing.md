# 13 — Adapter Conformance & Testing

## Overview
This document covers adapter interface compliance requirements and testing procedures for ATP router integration.

## Adapter Interface Requirements

All adapter implementations MUST provide the following interface:

### Required Methods
- `Estimate(request, context)` - Async method for cost/time estimation
- `Stream(request, context)` - Async method for response streaming
- `Health(request, context)` - Async method for health status reporting

### Interface Compliance
Adapters are automatically checked for compliance using the `AdapterComplianceChecker` tool (GAP-139).

## Compliance Checking Tool

### Usage

```python
from tools.adapter_compliance_checker import AdapterComplianceChecker

checker = AdapterComplianceChecker()

# Check a single adapter module
result = checker.check_adapter_module("/path/to/adapter/server.py")

# Check all adapters in a directory
results = checker.check_adapters_directory("/path/to/adapters/")

# Generate human-readable report
report = checker.generate_compliance_report(results)
print(report)
```

### Command Line Usage

```bash
cd /path/to/atp-main
python -c "
from tools.adapter_compliance_checker import AdapterComplianceChecker
checker = AdapterComplianceChecker()
results = checker.check_adapters_directory('adapters/')
print(checker.generate_compliance_report(results))
"
```

### Compliance Report Example

```
Adapter Interface Compliance Report
========================================

Total adapters: 3
Compliant: 2
Non-compliant: 1

Details:
  openai_adapter: ✅ COMPLIANT
  anthropic_adapter: ✅ COMPLIANT
  custom_adapter: ❌ NON-COMPLIANT
    Missing methods: Stream, Health
```

## Testing Requirements

### Unit Tests
- gRPC API surface: Estimate/Stream/Health semantics
- Required headers/metadata validation
- Error codes and retry-ability handling

### Integration Tests
- Estimation accuracy validation
- Streaming cadence verification
- Health signal fidelity testing

### Load & Chaos Testing
- Predictability scoring (MAPE, under-rate metrics)
- Failure scenario simulation
- Recovery behavior validation

## Metrics

The compliance checker exposes the following metrics:

- `non_compliant_adapters` - Gauge showing count of non-compliant adapters
- Updated automatically when `check_adapters_directory()` is called

## Troubleshooting

### Common Compliance Issues

1. **Missing Adapter Class**: Ensure your module contains a class named `Adapter`
2. **Missing Methods**: Implement all required methods: `Estimate`, `Stream`, `Health`
3. **Non-callable Methods**: Ensure methods are properly defined as async functions
4. **Import Errors**: Check that the module can be imported without syntax errors

### Example Compliant Adapter

```python
import asyncio
from collections.abc import AsyncIterator
from typing import Any

class Adapter:
    async def Estimate(self, request: Any, context: Any) -> dict:
        """Estimate cost and time for a request."""
        # Implementation here
        return {"cost_usd": 0.01, "estimated_time_ms": 1000}

    async def Stream(self, request: Any, context: Any) -> AsyncIterator[dict]:
        """Stream response chunks."""
        # Implementation here
        yield {"chunk": "response data"}

    async def Health(self, request: Any, context: Any) -> dict:
        """Report adapter health status."""
        # Implementation here
        return {"status": "healthy", "load": 0.5}
```

## CI/CD Integration

The compliance checker should be run as part of the CI pipeline:

```yaml
# Example GitHub Actions step
- name: Check Adapter Compliance
  run: |
    python -c "
    from tools.adapter_compliance_checker import AdapterComplianceChecker
    checker = AdapterComplianceChecker()
    results = checker.check_adapters_directory('adapters/')
    report = checker.generate_compliance_report(results)
    print(report)
    if results['non_compliant_adapters'] > 0:
        exit(1)
    "
```
