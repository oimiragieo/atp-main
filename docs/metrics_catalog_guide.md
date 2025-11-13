# ATP Router Metrics Catalog

## Overview

The ATP Router maintains a comprehensive catalog of all metrics used for monitoring, observability, and performance tracking. This catalog is automatically generated and validated to ensure consistency across the system.

## Catalog Structure

The metrics catalog is stored in `docs/metrics_catalog.json` and contains:

- **18 core metrics** covering request processing, model selection, consensus, resources, errors, SLM energy savings, QoS, federation, security, and carbon tracking
- **Schema validation** using JSON Schema Draft 07
- **Type definitions** for counters, histograms, and gauges
- **Unit specifications** and label definitions
- **Automatic generation** from both known metrics and runtime registry discovery

## Key Metrics

### Request Processing
- `atp_router_requests_total`: Total requests processed (counter)
- `atp_router_request_duration_seconds`: Request duration histogram
- `atp_router_active_connections`: Active connection gauge

### Model Selection & Consensus
- `atp_router_model_selections_total`: Model selections by algorithm (counter)
- `atp_router_ucb_score`: Upper Confidence Bound scores (gauge)
- `atp_router_consensus_agreement_pct`: Consensus agreement percentage (gauge)
- `atp_router_evidence_score`: Evidence scores for consensus (histogram)

### Resource & Performance
- `atp_router_memory_usage_bytes`: Memory usage (gauge)
- `atp_router_cpu_usage_percent`: CPU usage percentage (gauge)
- `atp_router_errors_total`: Error counts by type and component (counter)

### SLM & Energy Tracking
- `slm_energy_savings_kwh_total`: Energy savings from SLM vs large models (counter)
- `slm_carbon_savings_co2e_grams_total`: CO2e savings (counter)
- `slm_energy_efficiency_ratio`: Energy efficiency ratio (gauge)

### QoS & Budgeting
- `atp_router_window_tokens_remaining`: Remaining tokens in window (gauge)
- `atp_router_budget_burn_rate_usd_per_min`: Budget burn rate (gauge)

### Federation & Security
- `atp_router_federation_updates_total`: Federation route updates (counter)
- `atp_router_waf_blocks_total`: WAF blocks by rule and severity (counter)
- `atp_router_pii_redactions_total`: PII redactions performed (counter)

## Usage

### Generating the Catalog

```bash
# Generate metrics catalog
python tools/metrics_catalog_generator.py

# Validate existing catalog
python tools/metrics_catalog_generator.py --validate docs/metrics_catalog.json

# Generate to custom location
python tools/metrics_catalog_generator.py --output custom/path/catalog.json
```

### Integration

The catalog generator integrates with the metrics registry to:
- Discover runtime metrics not in the known catalog
- Validate metric definitions against schema
- Generate sorted, documented catalog files
- Support both programmatic and CLI usage

## Schema Validation

All metrics are validated against a JSON schema that ensures:
- Required fields: name, type, description
- Valid types: counter, histogram, gauge
- Proper structure for buckets and labels
- Consistent formatting and documentation

## Testing

Comprehensive tests cover:
- Catalog generation and structure validation
- Schema compliance and error handling
- File I/O operations and error recovery
- Registry integration and metric discovery
- CLI interface functionality

Run tests with:
```bash
python -m pytest tests/test_metrics_catalog_generator.py -v
```

## Maintenance

The catalog should be regenerated whenever:
- New metrics are added to the system
- Metric definitions change (units, labels, descriptions)
- Schema updates are required
- Registry integration needs validation

This ensures the documentation stays synchronized with the actual metrics implementation.
