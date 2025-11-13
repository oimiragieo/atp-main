# Audit Hash Verification Tool

## Overview

The Audit Hash Verification Tool is a command-line utility that verifies the integrity of tamper-evident audit logs used throughout the ATP (Autonomous Trust Platform) system. It ensures that audit logs have not been modified, tampered with, or corrupted by checking cryptographic hash chains and HMAC signatures.

## Purpose

Audit logs in ATP are designed to be tamper-evident, meaning any unauthorized modification will be detectable. This tool provides:

- **Integrity Verification**: Confirms that audit logs have not been altered
- **Tamper Detection**: Identifies if logs have been modified or corrupted
- **Batch Processing**: Can verify multiple log files at once
- **Compliance**: Supports regulatory requirements for audit trail integrity

## How It Works

The tool uses the existing `audit_log.verify_log()` function which:

1. **Reads each audit record** from the log file
2. **Validates HMAC signatures** (if present) using the provided secret
3. **Verifies hash chain continuity** by ensuring each record's hash matches the previous record's hash
4. **Detects tampering** by identifying any inconsistencies in the chain

## Installation

The tool is located at `tools/audit_verifier.py` and requires Python 3.6+.

### Dependencies

- Python 3.6+
- `memory_gateway.audit_log` module (included in ATP)

## Usage

### Basic Usage

```bash
# Verify a single audit log file
python tools/audit_verifier.py /path/to/audit.log

# Verify with custom secret key
python tools/audit_verifier.py /path/to/audit.log --secret my-secret-key

# Batch verify all logs in a directory
python tools/audit_verifier.py --batch /path/to/logs/

# Show help and usage information
python tools/audit_verifier.py --help
```

### Command Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `log_path` | Path to audit log file to verify | `/var/log/audit.log` |
| `--secret` | Secret key for HMAC verification | `--secret my-key` |
| `--batch` | Directory containing multiple log files | `--batch /logs/` |
| `--verbose` | Show detailed verification information | `--verbose` |

### Exit Codes

- `0`: Verification successful (all logs valid)
- `1`: Verification failed (tampering detected or errors)

## Examples

### Example 1: Verify Single Log

```bash
$ python tools/audit_verifier.py /var/log/atp-audit.log
✅ Audit log integrity verified: /var/log/atp-audit.log
   📝 Events: 1,247
   🔗 Latest hash: a1b2c3d4e5f6...
```

### Example 2: Batch Verification

```bash
$ python tools/audit_verifier.py --batch /var/log/atp/
🔍 Verifying 5 audit log files in /var/log/atp/...
✅ Audit log integrity verified: /var/log/atp/router.log
   📝 Events: 892
   🔗 Latest hash: f9e8d7c6b5a4...
✅ Audit log integrity verified: /var/log/atp/gateway.log
   📝 Events: 1,156
   🔗 Latest hash: 9a8b7c6d5e4f...
✅ Audit log integrity verified: /var/log/atp/memory.log
   📝 Events: 2,034
   🔗 Latest hash: 3d2e1f0a9b8...
✅ Audit log integrity verified: /var/log/atp/metrics.log
   📝 Events: 567
   🔗 Latest hash: 7h6g5f4e3d2...
✅ Audit log integrity verified: /var/log/atp/observability.log
   📝 Events: 1,789
   🔗 Latest hash: 1k2j3i4h5g6...

📊 Batch verification complete:
   ✅ Verified: 5
   ❌ Failed: 0
   📁 Total: 5
```

### Example 3: Tamper Detection

```bash
$ python tools/audit_verifier.py /var/log/suspicious.log
❌ Audit log verification FAILED: /var/log/suspicious.log
   Possible tampering detected!
```

## Integration with ATP Components

The audit verification tool integrates with various ATP components:

### Memory Gateway
- Verifies audit logs for memory operations
- Location: `memory-gateway/audit_logs/`

### Router Service
- Verifies routing decision audit trails
- Location: `router_service/logs/`

### Metrics Service
- Verifies metrics collection audit logs
- Location: `metrics/audit/`

### Observability
- Verifies monitoring and alerting audit logs
- Location: `observability/audit/`

## Security Considerations

### Secret Key Management
- Store secret keys securely (e.g., environment variables, key management systems)
- Never hardcode secrets in configuration files
- Rotate keys periodically according to security policies

### Access Control
- Limit access to the verification tool to authorized personnel
- Use principle of least privilege
- Log verification operations for audit purposes

### File Permissions
- Ensure audit log files have appropriate permissions
- Prevent unauthorized write access to log directories
- Use immutable storage where possible

## Troubleshooting

### Common Issues

**"Audit log file not found"**
- Verify the file path is correct
- Check file permissions
- Ensure the file exists

**"Error verifying audit log: Invalid HMAC"**
- Verify the secret key is correct
- Check if the secret has been rotated
- Ensure consistent key usage across log generation and verification

**"Hash chain verification failed"**
- Log file may have been tampered with
- Check for file corruption
- Verify no unauthorized modifications occurred

### Debug Mode

Enable verbose output for detailed verification information:

```bash
python tools/audit_verifier.py /path/to/audit.log --verbose
```

## Testing

Comprehensive tamper detection tests are available in `tests/test_audit_log.py`:

```bash
# Run audit log tests
python tests/test_audit_log.py

# Run specific tamper detection tests
python -m pytest tests/test_audit_log.py::test_tamper_detection_comprehensive -v
```

## API Reference

### AuditVerifier Class

```python
class AuditVerifier:
    def __init__(self, secret: Optional[bytes] = None):
        """Initialize with optional secret key."""

    def verify_single_log(self, log_path: str) -> bool:
        """Verify single audit log file."""

    def verify_batch_logs(self, directory: str) -> tuple[int, int]:
        """Verify all logs in directory, returns (verified, failed) count."""
```

## Contributing

When contributing to the audit verification tool:

1. Add tests for new tamper detection scenarios
2. Update documentation for new features
3. Ensure backward compatibility
4. Follow security best practices

## Related Documentation

- [ATP Audit Logging Specification](../docs/audit_spec.md)
- [Cryptographic Hash Chain Implementation](../memory-gateway/audit_log.py)
- [Security Hardening Guide](../docs/security.md)
