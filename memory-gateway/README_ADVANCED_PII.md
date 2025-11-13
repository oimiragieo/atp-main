# Advanced PII Detection and Redaction System

This document describes the advanced PII (Personally Identifiable Information) detection and redaction system integrated into the ATP Memory Gateway.

## Overview

The Advanced PII System provides enterprise-grade PII detection using both rule-based and machine learning approaches, with configurable redaction policies, comprehensive audit trails, and GDPR/CCPA compliance features.

## Features

### 🔍 Multi-Method PII Detection
- **Rule-based Detection**: Fast regex patterns for common PII types
- **ML-based Detection**: BERT and spaCy NER models for advanced detection
- **Custom Patterns**: Configurable regex patterns for organization-specific PII
- **Confidence Scoring**: Each detection includes confidence scores

### 🛡️ Configurable Redaction Policies
- **Data Classification Aware**: Different policies for public, internal, confidential, restricted, and top-secret data
- **Multiple Redaction Actions**: Mask, replace, remove, hash, tokenize, or encrypt
- **Format Preservation**: Maintain original format while redacting sensitive data
- **Granular Control**: Per-PII-type and per-classification policies

### 📋 Comprehensive Audit Trail
- **Immutable Logging**: Tamper-evident audit logs with hash chaining
- **Before/After Tracking**: Complete record of redaction operations
- **Searchable History**: Query audit trail by tenant, user, date range
- **Compliance Reporting**: Automated reports for SOC 2, GDPR, HIPAA

### 🌍 GDPR/CCPA Compliance
- **Data Subject Requests**: Automated handling of export and deletion requests
- **Right to be Forgotten**: Systematic data deletion capabilities
- **Data Lineage**: Track data flow and transformations
- **Retention Policies**: Automated data lifecycle management

## Supported PII Types

| PII Type | Rule-based | ML-based | Examples |
|----------|------------|----------|----------|
| Email | ✅ | ✅ | john.doe@example.com |
| Phone | ✅ | ✅ | (555) 123-4567 |
| SSN | ✅ | ❌ | 123-45-6789 |
| Credit Card | ✅ | ❌ | 4532 1234 5678 9012 |
| Person Name | ❌ | ✅ | John Doe |
| Address | ❌ | ✅ | 123 Main St, Anytown |
| IP Address | ✅ | ❌ | 192.168.1.1 |
| MAC Address | ✅ | ❌ | 00:1B:44:11:3A:B7 |
| IBAN | ✅ | ❌ | GB82 WEST 1234 5698 7654 32 |
| Date of Birth | ✅ | ✅ | 01/15/1990 |
| Custom | ✅ | ❌ | Organization-specific patterns |

## Installation

### Basic Installation

```bash
# Install core dependencies
pip install -r requirements.txt

# Install PII detection dependencies
pip install -r requirements-pii.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### Docker Installation

```bash
# Build enhanced memory gateway
docker build -f Dockerfile.enhanced -t atp-memory-gateway-enhanced .

# Run with PII protection
docker run -p 8080:8080 -e ENABLE_PII_PROTECTION=true atp-memory-gateway-enhanced
```

## Configuration

### Basic Configuration (`pii_config.json`)

```json
{
  "enable_ml_detection": true,
  "enable_rule_detection": true,
  "ml_model_name": "dbmdz/bert-large-cased-finetuned-conll03-english",
  "confidence_threshold": 0.8,
  "context_window": 50,
  "max_text_length": 10000,
  
  "redaction_policies": {
    "confidential": {
      "email": {
        "action": "replace",
        "replacement_text": "[REDACTED-EMAIL]"
      },
      "phone": {
        "action": "mask",
        "visible_chars": 4,
        "preserve_format": true
      }
    }
  }
}
```

### Environment Variables

```bash
# Enable/disable PII protection
ENABLE_PII_PROTECTION=true

# PII configuration file path
PII_CONFIG_PATH=/app/pii_config.json

# Audit log storage path
PII_AUDIT_PATH=/app/pii_audit_logs

# ML model cache directory
TRANSFORMERS_CACHE=/app/model_cache
```

## API Usage

### Memory Storage with PII Protection

```bash
# Store data with automatic PII protection
curl -X PUT "http://localhost:8080/v1/memory/user_data/profile" \
  -H "x-tenant-id: acme-corp" \
  -H "x-user-id: john.doe" \
  -H "Content-Type: application/json" \
  -d '{
    "object": {
      "name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "(555) 123-4567"
    }
  }'

# Response includes PII detection results
{
  "ok": true,
  "pii_detected": true,
  "pii_matches_count": 3,
  "pii_types": ["person_name", "email", "phone"],
  "pii_audit_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Retrieve Data with PII Metadata

```bash
# Get data with PII analysis
curl "http://localhost:8080/v1/memory/user_data/profile?include_pii_metadata=true" \
  -H "x-tenant-id: acme-corp"

# Response includes PII metadata
{
  "object": {
    "name": "[REDACTED-NAME]",
    "email": "[REDACTED-EMAIL]",
    "phone": "***-***-4567"
  },
  "pii_metadata": {
    "pii_detected": true,
    "pii_matches_count": 3,
    "pii_types": ["person_name", "email", "phone"]
  }
}
```

### Direct PII Detection

```bash
# Detect PII in text
curl -X POST "http://localhost:8080/v1/pii/detect" \
  -H "x-tenant-id: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Contact John Doe at john.doe@example.com",
    "data_classification": "confidential",
    "return_matches": true
  }'
```

### PII Redaction

```bash
# Redact PII from text
curl -X POST "http://localhost:8080/v1/pii/redact" \
  -H "x-tenant-id: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Call me at (555) 123-4567",
    "data_classification": "confidential"
  }'
```

### Audit Trail

```bash
# Get PII audit trail
curl "http://localhost:8080/v1/pii/audit?days=7&limit=50" \
  -H "x-tenant-id: acme-corp"
```

### Data Subject Requests

```bash
# Handle GDPR export request
curl -X POST "http://localhost:8080/v1/pii/data-subject-request" \
  -H "x-tenant-id: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_identifier": "john.doe@example.com",
    "request_type": "export"
  }'
```

## CLI Usage

The system includes a comprehensive CLI tool for management and testing:

### Basic Detection

```bash
# Detect PII in text
python pii_cli.py detect "Contact John Doe at john.doe@example.com"

# Redact PII from text
python pii_cli.py redact "Call me at (555) 123-4567" --classification confidential
```

### File Processing

```bash
# Process entire file
python pii_cli.py test-file input.txt --output results.json --classification confidential
```

### Audit Management

```bash
# View audit trail
python pii_cli.py audit --tenant acme-corp --days 7 --format table

# Handle data subject request
python pii_cli.py data-subject-request john.doe@example.com export --output export.json
```

### Custom Patterns

```bash
# Add custom pattern
python pii_cli.py add-pattern employee_id "EMP\\d{6}" --type custom

# Validate configuration
python pii_cli.py validate pii_config.json
```

### Performance Testing

```bash
# Run benchmarks
python pii_cli.py benchmark --text-size 5000 --iterations 100 --methods both
```

## Data Classifications

The system supports five data classification levels with different redaction policies:

### Public
- **Email**: Masked with 3 visible characters
- **Phone**: Masked with 4 visible characters  
- **Names**: Replaced with `[NAME]`

### Internal
- **Email**: Masked with 2 visible characters
- **Phone**: Masked with 4 visible characters
- **SSN**: Replaced with `[SSN]`
- **Names**: Replaced with `[NAME]`

### Confidential (Default)
- **Email**: Replaced with `[REDACTED-EMAIL]`
- **Phone**: Replaced with `[REDACTED-PHONE]`
- **SSN**: Replaced with `[REDACTED-SSN]`
- **Credit Card**: Replaced with `[REDACTED-CC]`
- **Names**: Replaced with `[REDACTED-NAME]`
- **Addresses**: Replaced with `[REDACTED-ADDRESS]`

### Restricted
- **All PII**: Hashed with SHA-256 (first 8 characters shown)

### Top Secret
- **All PII**: Completely removed from text

## Performance Considerations

### Rule-based Detection
- **Speed**: ~1ms per 1KB of text
- **Memory**: Minimal memory usage
- **Accuracy**: High precision, may miss context-dependent PII

### ML-based Detection
- **Speed**: ~50-100ms per 1KB of text (first run), ~10-20ms (cached)
- **Memory**: ~500MB for BERT model, ~100MB for spaCy
- **Accuracy**: Higher recall, better context understanding

### Recommendations
- Use rule-based detection for high-throughput scenarios
- Use ML-based detection for higher accuracy requirements
- Enable both methods for optimal balance
- Configure text length limits for ML processing
- Use caching for repeated content

## Security Considerations

### Audit Log Security
- Audit logs are stored with hash chaining for tamper detection
- Original text is never stored in audit logs (only hashes)
- Audit logs can be encrypted at rest
- Access to audit logs is logged and monitored

### Data Protection
- PII is redacted before storage by default
- Redaction policies are configurable per data classification
- Original data can be preserved if explicitly disabled
- All PII operations are audited

### Access Control
- All endpoints require tenant authentication
- User context is captured for audit trails
- Data subject requests are logged and tracked
- Configuration access is restricted

## Compliance Features

### GDPR Compliance
- **Right to Access**: Export all data related to a subject
- **Right to Rectification**: Update incorrect personal data
- **Right to Erasure**: Delete personal data on request
- **Data Portability**: Export data in machine-readable format
- **Privacy by Design**: PII protection enabled by default

### CCPA Compliance
- **Right to Know**: Detailed audit trails of data processing
- **Right to Delete**: Systematic deletion of personal information
- **Right to Opt-Out**: Disable PII processing for specific users
- **Non-Discrimination**: No service degradation for privacy requests

### SOC 2 Compliance
- **Security**: Comprehensive audit trails and access controls
- **Availability**: High availability and disaster recovery
- **Processing Integrity**: Data validation and error handling
- **Confidentiality**: PII redaction and encryption
- **Privacy**: Data subject rights and consent management

## Monitoring and Alerting

### Metrics
- PII detection rates by type and method
- Redaction operation counts and latency
- Audit trail growth and retention
- ML model performance and accuracy
- System health and availability

### Alerts
- High PII detection rates (potential data breach)
- Audit log integrity violations
- ML model failures or degraded performance
- Data subject request processing delays
- System resource exhaustion

### Dashboards
- Real-time PII detection statistics
- Audit trail visualization
- Compliance reporting metrics
- System performance monitoring
- Cost and resource utilization

## Troubleshooting

### Common Issues

#### ML Models Not Loading
```bash
# Check model availability
python -c "from transformers import pipeline; print('Transformers available')"
python -c "import spacy; print('spaCy available')"

# Download models manually
python -m spacy download en_core_web_sm
```

#### High Memory Usage
```bash
# Reduce ML model usage
export ENABLE_ML_DETECTION=false

# Limit text processing length
export MAX_TEXT_LENGTH=5000
```

#### Slow Performance
```bash
# Enable only rule-based detection
export ENABLE_RULE_DETECTION=true
export ENABLE_ML_DETECTION=false

# Increase confidence threshold
export CONFIDENCE_THRESHOLD=0.9
```

### Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Test PII detection
python pii_cli.py detect "test text" --verbose

# Validate configuration
python pii_cli.py validate pii_config.json

# Check system health
curl http://localhost:8080/v1/pii/health
```

## Migration Guide

### From Basic PII System

1. **Install Dependencies**
   ```bash
   pip install -r requirements-pii.txt
   ```

2. **Update Configuration**
   ```bash
   cp pii_config.json.example pii_config.json
   # Edit configuration as needed
   ```

3. **Switch to Enhanced App**
   ```bash
   # Update Docker Compose or deployment scripts
   # Change from app.py to enhanced_app.py
   ```

4. **Test Migration**
   ```bash
   python pii_cli.py validate pii_config.json
   curl http://localhost:8080/v1/pii/health
   ```

### Backward Compatibility

The enhanced system maintains full backward compatibility with the original memory gateway API. Existing clients will continue to work without modification, with PII protection automatically enabled.

## Support

For issues, questions, or feature requests:

1. Check the troubleshooting section above
2. Review the audit logs for error details
3. Test with the CLI tool for debugging
4. Check system health endpoints
5. Consult the configuration documentation

## License

This advanced PII system is part of the ATP project and is licensed under the Apache License 2.0.