# GAP-368: Evidence Pack Assembly Pipeline

## Overview

The Evidence Pack Assembly Pipeline implements automated collection and packaging of compliance evidence for enterprise audits. This module bundles policies, audit logs, differential privacy (DP) ledger entries, retention logs, and Service Level Objective (SLO) reports into compressed archives for regulatory compliance.

## Features

- **Automated Evidence Collection**: Gathers data from multiple sources with configurable patterns
- **Time-Range Filtering**: Collects evidence within specified date ranges (default: last 30 days)
- **Compression**: Creates ZIP archives with configurable compression levels
- **Metrics Integration**: Prometheus metrics for monitoring pack generation
- **Error Handling**: Graceful handling of missing files and malformed data
- **Configurable Patterns**: Flexible file matching patterns for different data sources

## Architecture

### Core Components

1. **EvidencePackConfig**: Configuration class for data source directories and file patterns
2. **EvidencePackAssembler**: Main assembler class that orchestrates evidence collection
3. **EvidencePack**: Data structure containing all collected evidence
4. **EvidencePackManifest**: Metadata describing the pack contents and collection parameters

### Data Sources

The pipeline collects evidence from the following sources:

- **Policies**: YAML/JSON policy files defining access rules
- **Audit Chain**: JSONL audit logs of system activities
- **DP Ledger**: Differential privacy budget usage records
- **Retention Logs**: Data lifecycle and retention events
- **SLO Reports**: Service level objective metrics and observations

## Usage

### Basic Usage

```python
from router_service.evidence_pack_assembler import create_evidence_pack

# Create an evidence pack with default settings
pack = create_evidence_pack("audit-2024-q1")

# The pack is automatically saved to disk as a ZIP file
```

### Advanced Usage

```python
from router_service.evidence_pack_assembler import EvidencePackAssembler, EvidencePackConfig

# Configure custom data sources
config = EvidencePackConfig(
    policies_dir="/path/to/policies",
    audit_logs_dir="/path/to/audit",
    dp_ledger_dir="/path/to/dp",
    retention_logs_dir="/path/to/retention",
    slo_reports_dir="/path/to/slo",
    days_back=90,  # Collect last 90 days of data
    compression_level=9  # Maximum compression
)

assembler = EvidencePackAssembler(config)

# Create pack with custom time range
time_range = {
    "start": "2024-01-01T00:00:00",
    "end": "2024-03-31T23:59:59"
}

pack = assembler.assemble_pack("quarterly-audit-2024-q1", time_range)
pack_path = assembler.save_pack(pack)
```

### Custom File Patterns

```python
config = EvidencePackConfig(
    policy_patterns=["custom-policies/*.yaml", "rules/*.json"],
    audit_patterns=["logs/audit-*.jsonl", "security-events/*.jsonl"],
    dp_patterns=["privacy/dp-*.jsonl"],
    retention_patterns=["lifecycle/*.jsonl"],
    slo_patterns=["metrics/slm_observations*.jsonl", "counters/*.json"]
)
```

## Configuration

### EvidencePackConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `policies_dir` | `str` | `"tools"` | Directory containing policy files |
| `audit_logs_dir` | `str` | `"data"` | Directory containing audit logs |
| `dp_ledger_dir` | `str` | `"data"` | Directory containing DP ledger |
| `retention_logs_dir` | `str` | `"data"` | Directory containing retention logs |
| `slo_reports_dir` | `str` | `"data"` | Directory containing SLO reports |
| `output_dir` | `str` | `"evidence_packs"` | Output directory for packs |
| `policy_patterns` | `list[str]` | `["policy*.yaml", "policy*.json"]` | Policy file patterns |
| `audit_patterns` | `list[str]` | `["*audit*.jsonl", "admin_audit.jsonl"]` | Audit log patterns |
| `dp_patterns` | `list[str]` | `["*dp*.jsonl", "*privacy*.jsonl"]` | DP ledger patterns |
| `retention_patterns` | `list[str]` | `["lifecycle*.jsonl", "*retention*.jsonl"]` | Retention log patterns |
| `slo_patterns` | `list[str]` | `["slm_observations*.jsonl", "*counters.json", "*slo*.json"]` | SLO report patterns |
| `days_back` | `int` | `30` | Days of data to collect |
| `compression_level` | `int` | `6` | ZIP compression level (0-9) |

## File Formats

### Policy Files
- **Format**: YAML or JSON
- **Example**:
```yaml
rules:
  - match:
      tenant: "acme"
    effect: "allow"
  - match:
      tenant: "*"
    effect: "deny"
```

### Audit Logs
- **Format**: JSONL (one JSON object per line)
- **Fields**: `timestamp`, `event`, `user`, `action`, etc.
- **Example**:
```json
{"timestamp": "2024-01-15T10:30:00", "event": "login", "user": "alice", "ip": "192.168.1.100"}
{"timestamp": "2024-01-15T10:45:00", "event": "access", "user": "alice", "resource": "/api/data"}
```

### DP Ledger
- **Format**: JSONL
- **Fields**: `timestamp`, `privacy_budget_used`, `query_type`, etc.
- **Example**:
```json
{"timestamp": "2024-01-15T11:00:00", "privacy_budget_used": 0.1, "query_type": "count", "epsilon": 0.5}
```

### Retention Logs
- **Format**: JSONL
- **Fields**: `timestamp`, `action`, `data_type`, `age_days`, etc.
- **Example**:
```json
{"timestamp": "2024-01-15T12:00:00", "action": "delete", "data_type": "logs", "age_days": 90}
```

### SLO Reports
- **Format**: JSONL for observations, JSON for counters
- **SLM Observations Example**:
```json
{"timestamp": "2024-01-15T13:00:00", "service": "router", "latency_p95": 150, "error_rate": 0.02}
```
- **Counters Example**:
```json
{"requests_total": 10000, "errors_total": 200, "latency_sum": 1500000}
```

## Output Format

Evidence packs are saved as ZIP archives with the following structure:

```
evidence-pack-{id}.zip
├── manifest.json          # Pack metadata and component summary
├── policies.json          # Collected policy files
├── audit_chain.jsonl      # Filtered audit entries
├── dp_ledger.jsonl        # DP budget usage records
├── retention_logs.jsonl   # Retention events
└── slo_reports.json       # SLO metrics and observations
```

### Manifest Structure

```json
{
  "pack_id": "evidence-pack-1234567890",
  "created_at": "2024-01-15T14:00:00.123456",
  "time_range": {
    "start": "2023-12-16T14:00:00.123456",
    "end": "2024-01-15T14:00:00.123456"
  },
  "version": "1.0",
  "components": {
    "policies": {
      "count": 3,
      "sources": ["policy*.yaml", "policy*.json"]
    },
    "audit_chain": {
      "count": 1250,
      "sources": ["*audit*.jsonl", "admin_audit.jsonl"]
    },
    "dp_ledger": {
      "count": 89,
      "sources": ["*dp*.jsonl", "*privacy*.jsonl"]
    },
    "retention_logs": {
      "count": 45,
      "sources": ["lifecycle*.jsonl", "*retention*.jsonl"]
    },
    "slo_reports": {
      "count": 3,
      "sources": ["slm_observations*.jsonl", "*counters.json", "*slo*.json"]
    }
  }
}
```

## Metrics

The module integrates with Prometheus for monitoring:

- `evidence_packs_generated_total`: Counter of total packs generated
- `evidence_pack_generation_duration_seconds`: Histogram of pack generation time

## Error Handling

The assembler handles various error conditions gracefully:

- **Missing Directories**: Logs warnings and continues with available data
- **Malformed Files**: Skips invalid files and logs errors
- **Permission Issues**: Logs errors for inaccessible files
- **Empty Results**: Creates packs with empty components when no data is found

## Time Range Filtering

Evidence collection supports flexible time range filtering:

- **Default**: Last 30 days from current time
- **Custom Range**: Specify exact start/end timestamps
- **Multiple Fields**: Supports `timestamp`, `time`, and `created_at` fields
- **Inclusive Bounds**: Start time inclusive, end time exclusive

## Performance Considerations

- **File Pattern Matching**: Uses glob patterns for efficient file discovery
- **Streaming Processing**: Processes large JSONL files without loading entirely into memory
- **Compression**: Balances speed vs. size with configurable compression levels
- **Parallel Collection**: Components are collected independently for better performance

## Security Considerations

- **Data Sensitivity**: Evidence packs contain sensitive compliance data
- **Access Control**: Ensure proper file permissions on output directories
- **Encryption**: Consider encrypting packs for secure storage/transmission
- **Audit Trail**: All pack creation is logged with timestamps and component details

## Integration Examples

### With Existing Data Pipeline

```python
# Integrate with automated compliance reporting
def generate_monthly_compliance_pack():
    config = EvidencePackConfig(days_back=30)
    assembler = EvidencePackAssembler(config)

    pack_id = f"compliance-{datetime.now().strftime('%Y-%m')}"
    pack = assembler.assemble_pack(pack_id)

    # Upload to secure storage
    pack_path = assembler.save_pack(pack)
    upload_to_secure_storage(pack_path)

    return pack_id
```

### Custom Evidence Sources

```python
class CustomEvidencePackAssembler(EvidencePackAssembler):
    def _collect_custom_evidence(self, time_range):
        # Implement custom evidence collection logic
        pass

    def assemble_pack(self, pack_id, custom_time_range=None):
        pack = super().assemble_pack(pack_id, custom_time_range)
        # Add custom evidence
        pack.custom_evidence = self._collect_custom_evidence(pack.manifest.time_range)
        return pack
```

## Troubleshooting

### Common Issues

1. **No Files Found**: Check file patterns and directory paths
2. **Time Range Issues**: Verify timestamp formats in data files
3. **Permission Errors**: Ensure read access to data directories
4. **Large Pack Sizes**: Adjust compression level or time range
5. **Memory Issues**: Process large datasets in chunks

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('router_service.evidence_pack_assembler').setLevel(logging.DEBUG)
```

## API Reference

### EvidencePackAssembler

#### Methods

- `assemble_pack(pack_id, custom_time_range)`: Create evidence pack
- `save_pack(pack, output_path)`: Save pack to disk
- `_collect_policies()`: Collect policy files
- `_collect_audit_chain(time_range)`: Collect audit entries
- `_collect_dp_ledger(time_range)`: Collect DP ledger entries
- `_collect_retention_logs(time_range)`: Collect retention logs
- `_collect_slo_reports(time_range)`: Collect SLO reports

### Utility Functions

- `create_evidence_pack(pack_id, config, save_to_disk)`: Convenience function
- `get_evidence_pack_info(pack_path)`: Get pack metadata without extraction

## Future Enhancements

- **Encryption**: Built-in encryption for sensitive evidence packs
- **Digital Signatures**: Cryptographic signing of pack contents
- **Incremental Updates**: Support for updating existing packs
- **Cloud Storage**: Direct integration with cloud storage providers
- **Format Conversion**: Support for additional data formats
- **Real-time Collection**: Streaming evidence collection for continuous compliance
