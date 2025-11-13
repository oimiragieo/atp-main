# GAP-303: Row-level Encryption & Key Scoping Guide

## Overview

This document describes the implementation of **GAP-303: Row-level encryption & key scoping**, which provides per-row data encryption keys (DEK) with KMS envelope encryption. Each database row gets its own unique DEK, wrapped by a master key from KMS, enabling fine-grained access control and secure key management.

## Architecture

### Core Components

1. **RowLevelEncryption**: Core encryption service that manages per-row DEKs
2. **RowEncryptionStore**: Storage layer with tenant-based access control
3. **RowEncryptionMetricsCollector**: Prometheus metrics integration
4. **EncryptedRow**: Data structure representing encrypted row data

### Key Features

- **Per-Row DEKs**: Each row gets a unique 256-bit data encryption key
- **KMS Envelope Encryption**: DEKs are wrapped using master keys from KMS
- **Tenant Isolation**: Multi-tenant key scoping with access control
- **Key Rotation**: Support for rotating encryption keys
- **AAD Support**: Additional authenticated data for enhanced security
- **Metrics Integration**: Comprehensive monitoring and observability

## Security Model

### Encryption Flow

```
Plaintext Data → DEK → Encrypted Data
       ↓
     KMS
       ↓
   Wrapped DEK → Storage
```

1. **Data Encryption**: Each row's data is encrypted with a unique DEK
2. **Key Wrapping**: The DEK is encrypted (wrapped) using a master key from KMS
3. **Storage**: Both encrypted data and wrapped DEK are stored together
4. **Access Control**: Only authorized tenants can unwrap and use the DEK

### Authorization

- **Tenant-Based**: Each row is associated with a specific tenant
- **Access Control**: Only the owning tenant can decrypt their data
- **Audit Trail**: All access attempts are logged and metered

## API Reference

### RowLevelEncryption

```python
from tools.row_level_encryption import RowLevelEncryption
from tools.kms_poc import KMS

# Initialize
kms = KMS(master_key)
encryption = RowLevelEncryption(kms, key_version="v1")

# Encrypt a row
encrypted_row = encryption.encrypt_row(
    row_id="user_123",
    data={"name": "John", "email": "john@example.com"},
    tenant_id="tenant_a",
    aad=b"additional_auth_data"
)

# Decrypt a row
data = encryption.decrypt_row(encrypted_row, tenant_id="tenant_a")
```

### RowEncryptionStore

```python
from tools.row_level_encryption import RowEncryptionStore

# Initialize store
store = RowEncryptionStore(encryption)

# Store encrypted data
store.store_row("user_123", user_data, "tenant_a")

# Retrieve and decrypt
user_data = store.get_row("user_123", "tenant_a")

# List tenant's rows
row_ids = store.list_rows_for_tenant("tenant_a")

# Delete row (with authorization)
store.delete_row("user_123", "tenant_a")
```

## Configuration

### KMS Configuration

```python
# Initialize KMS with master key
master_key = b"32_byte_master_key_for_production_use"
kms = KMS(master_key)
```

### Encryption Service Configuration

```python
# Create encryption service
encryption = RowLevelEncryption(
    kms=kms,
    key_version="v1"  # Track key versions for rotation
)
```

## Key Rotation

### Manual Key Rotation

```python
# Rotate keys for a specific tenant
rotated_count = store.rotate_keys(
    old_key_version="v1",
    new_key_version="v2",
    tenant_id="tenant_a"
)

print(f"Rotated {rotated_count} rows")
```

### Automated Key Rotation

```python
# Example: Rotate keys older than 90 days
import time

current_time = time.time()
ninety_days_ago = current_time - (90 * 24 * 60 * 60)

for row_id, encrypted_row in store.rows.items():
    if encrypted_row.created_at < ninety_days_ago:
        # Rotate this row's key
        new_row = encryption.re_encrypt_row(
            encrypted_row, "v2", encrypted_row.tenant_id
        )
        store.rows[row_id] = new_row
```

## Metrics & Monitoring

### Prometheus Metrics

The implementation provides comprehensive metrics:

- `row_encryption_operation_duration_seconds`: Operation duration by type and tenant
- `row_encryption_operations_total`: Total operations with success/failure status
- `row_encryption_rows_processed_total`: Rows processed by operation type

### Metrics Collection

```python
from tools.row_encryption_metrics import get_row_encryption_metrics_collector

collector = get_row_encryption_metrics_collector()
stats = collector.get_operation_stats(tenant_id="tenant_a")

print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Average duration: {stats['average_duration_ms']:.2f}ms")
```

## Security Best Practices

### Key Management

1. **Master Key Security**: Store master keys in HSM or secure vault
2. **Key Rotation**: Rotate master keys regularly (quarterly/yearly)
3. **Key Versions**: Track key versions for audit and rotation
4. **Access Logging**: Log all key access and rotation events

### Data Protection

1. **AAD Usage**: Always use additional authenticated data
2. **Tenant Isolation**: Enforce strict tenant boundaries
3. **Access Control**: Implement least-privilege access
4. **Audit Logging**: Log all encryption/decryption operations

### Operational Security

1. **Monitoring**: Monitor encryption operation metrics
2. **Alerting**: Alert on high failure rates or unusual patterns
3. **Backup**: Secure backup of encrypted data and key metadata
4. **Recovery**: Document key recovery procedures

## Performance Considerations

### Encryption Overhead

- **Per-Row DEK**: Minimal storage overhead (~32 bytes per row)
- **KMS Operations**: Network latency for key wrapping/unwrapping
- **CPU Usage**: AES-256 encryption/decryption overhead

### Optimization Strategies

1. **Batch Operations**: Process multiple rows together
2. **Caching**: Cache unwrapped DEKs for short periods
3. **Async Processing**: Use async operations for bulk encryption
4. **Connection Pooling**: Pool KMS connections

## Testing

### Unit Tests

```bash
# Run row-level encryption tests
python -m pytest tests/test_row_level_encryption.py -v
```

### Integration Tests

```python
# Example integration test
def test_tenant_isolation():
    # Setup
    kms = KMS(b"test_key_32_bytes_long_for_testing")
    store = RowEncryptionStore(RowLevelEncryption(kms))

    # Test data
    tenant_a_data = {"secret": "tenant_a_data"}
    tenant_b_data = {"secret": "tenant_b_data"}

    # Store data for different tenants
    store.store_row("row1", tenant_a_data, "tenant_a")
    store.store_row("row1", tenant_b_data, "tenant_b")

    # Verify isolation
    assert store.get_row("row1", "tenant_a") == tenant_a_data
    assert store.get_row("row1", "tenant_b") == tenant_b_data
```

## Deployment Guide

### Production Setup

1. **KMS Integration**: Configure production KMS (AWS KMS, HashiCorp Vault, etc.)
2. **Key Management**: Set up master key rotation policies
3. **Monitoring**: Configure Prometheus metrics collection
4. **Backup**: Set up encrypted data backup procedures

### Configuration Example

```python
# Production configuration
config = {
    'kms_master_key': os.environ['KMS_MASTER_KEY'],
    'key_rotation_days': 90,
    'metrics_enabled': True,
    'audit_log_enabled': True
}
```

## Troubleshooting

### Common Issues

1. **Access Denied**: Check tenant authorization
2. **Decryption Failures**: Verify AAD consistency
3. **Key Rotation Issues**: Ensure old keys are still available during rotation
4. **Performance Issues**: Monitor metrics and optimize batch operations

### Debug Mode

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check metrics
collector = get_row_encryption_metrics_collector()
stats = collector.get_operation_stats()
print("Operation stats:", stats)
```

## Future Enhancements

- **Hardware Security Modules (HSM)**: Direct HSM integration
- **Key Derivation Functions**: Advanced key derivation
- **Multi-Region Keys**: Cross-region key replication
- **Quantum-Resistant Algorithms**: Post-quantum cryptography support
- **Automated Key Rotation**: Scheduled key rotation policies

## Compliance

This implementation supports:
- **GDPR**: Data encryption at rest and in transit
- **HIPAA**: Protected health information encryption
- **PCI DSS**: Cardholder data protection
- **SOX**: Financial data security requirements

## Conclusion

GAP-303 provides a robust, scalable solution for row-level encryption with strong security guarantees, comprehensive monitoring, and production-ready features. The implementation ensures tenant isolation, supports key rotation, and provides detailed observability for security operations.</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\row_level_encryption_guide.md
