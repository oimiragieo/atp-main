# GAP-302: Artifact / Binary Blob Tier Guide

## Overview

The Artifact Storage Tier provides secure, signed storage for binary data and artifacts with integrity verification, size limits, and pluggable backends supporting both local filesystem and S3-compatible cloud storage.

## Key Features

- **Signed Metadata Schema**: HMAC-signed metadata with integrity verification
- **Pluggable Backends**: Local filesystem and S3-compatible storage
- **Size Limits & Quotas**: Configurable size limits and enforcement
- **Integrity Verification**: SHA256 checksums and signature validation
- **Expiration Support**: Optional artifact expiration with automatic cleanup
- **Metrics Integration**: Prometheus metrics for operations and storage tracking

## Architecture

### Core Components

1. **ArtifactMetadata**: Signed metadata schema with integrity verification
2. **ArtifactStorageBackend**: Abstract protocol for storage implementations
3. **LocalArtifactStorageBackend**: Filesystem-based storage for development
4. **S3ArtifactStorageBackend**: Cloud storage with S3 compatibility
5. **ArtifactStorageFactory**: Factory for backend creation
6. **Metrics Integration**: Prometheus metrics collection

### Data Flow

```
Upload Flow:
Client → ArtifactStorageBackend → Generate Checksum/Signature → Store Data + Metadata → Metrics

Download Flow:
Client → ArtifactStorageBackend → Load Metadata → Verify Signature → Load Data → Integrity Check → Metrics
```

## Quick Start

### Basic Usage

```python
import asyncio
from tools.artifact_backend import ArtifactStorageFactory, get_artifact_storage

async def example():
    # Create local backend
    config = {
        'base_path': './artifacts',
        'max_size_bytes': 10 * 1024 * 1024,  # 10MB limit
        'signing_key': 'your-secret-key'
    }
    backend = ArtifactStorageFactory.create_local_backend(config)

    # Upload artifact
    data = b"Hello, World!"
    metadata = {
        'name': 'hello.txt',
        'content_type': 'text/plain',
        'description': 'Example artifact'
    }

    upload_result = await backend.upload_artifact('hello-artifact', data, metadata)
    if upload_result.success:
        print(f"Uploaded: {upload_result.metadata.id}")

    # Download artifact
    download_result = await backend.download_artifact('hello-artifact')
    if download_result.success:
        print(f"Downloaded: {download_result.data.decode()}")

    # Context manager usage
    async with get_artifact_storage('local', config) as storage:
        result = await storage.upload_artifact('test', b'data', {})
        print(f"Context manager result: {result.success}")

asyncio.run(example())
```

### S3 Backend Configuration

```python
# S3 backend configuration
s3_config = {
    'bucket_name': 'my-artifacts-bucket',
    'region': 'us-east-1',
    'max_size_bytes': 100 * 1024 * 1024,  # 100MB
    'signing_key': 'your-secret-key',
    'aws_access_key_id': 'your-access-key',
    'aws_secret_access_key': 'your-secret-key'
}

backend = ArtifactStorageFactory.create_s3_backend(s3_config)
```

## API Reference

### ArtifactMetadata

```python
@dataclass
class ArtifactMetadata:
    id: str                           # Unique artifact identifier
    name: str                         # Human-readable name
    content_type: str                 # MIME content type
    size_bytes: int                   # Size in bytes
    checksum_sha256: str             # SHA256 checksum
    signature: str                    # HMAC signature
    created_at: float                 # Creation timestamp
    expires_at: Optional[float]       # Optional expiration
    metadata: dict[str, Any]          # Custom metadata

    def is_expired(self) -> bool:
        """Check if artifact has expired"""

    def verify_integrity(self, data: bytes) -> bool:
        """Verify data integrity using checksum"""
```

### ArtifactStorageBackend Protocol

```python
class ArtifactStorageBackend(Protocol):
    async def health_check(self) -> bool:
        """Check backend connectivity and accessibility"""

    async def upload_artifact(self, artifact_id: str, data: bytes,
                            metadata: dict[str, Any]) -> ArtifactUploadResult:
        """Upload artifact with metadata"""

    async def download_artifact(self, artifact_id: str) -> ArtifactDownloadResult:
        """Download artifact data and metadata"""

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact and metadata"""

    async def list_artifacts(self, prefix: Optional[str] = None,
                           limit: int = 100) -> list[ArtifactMetadata]:
        """List artifacts with optional prefix filter"""

    async def get_artifact_metadata(self, artifact_id: str) -> Optional[ArtifactMetadata]:
        """Get metadata without downloading data"""
```

### Result Types

```python
@dataclass
class ArtifactUploadResult:
    metadata: Optional[ArtifactMetadata]
    upload_duration_ms: float
    success: bool
    error_message: Optional[str] = None

@dataclass
class ArtifactDownloadResult:
    data: Optional[bytes]
    metadata: Optional[ArtifactMetadata]
    download_duration_ms: float
    success: bool
    error_message: Optional[str] = None
```

## Security Model

### Integrity Verification

1. **SHA256 Checksums**: Data integrity verification
2. **HMAC Signatures**: Metadata authenticity using shared signing key
3. **Signature Scope**: Covers both metadata and data content

### Access Control

- **Backend-Level**: Configurable credentials and permissions
- **Application-Level**: Implement your own access control logic
- **Audit Trail**: All operations logged with metrics

### Size Limits

- **Hard Limits**: Configurable maximum artifact size
- **Quota Enforcement**: Automatic rejection of oversized uploads
- **Metrics Tracking**: Size distribution monitoring

## Configuration

### Local Backend

```python
config = {
    'base_path': './artifacts',           # Storage directory
    'max_size_bytes': 100 * 1024 * 1024, # 100MB limit
    'signing_key': 'your-secret-key'      # HMAC signing key
}
```

### S3 Backend

```python
config = {
    'bucket_name': 'artifacts-bucket',
    'region': 'us-east-1',
    'max_size_bytes': 100 * 1024 * 1024,
    'signing_key': 'your-secret-key',
    'aws_access_key_id': 'ACCESS_KEY',
    'aws_secret_access_key': 'SECRET_KEY'
}
```

## Metrics & Monitoring

### Prometheus Metrics

- `artifact_operation_duration_seconds`: Operation duration by type
- `artifact_operations_total`: Operation count by type and status
- `artifact_bytes_stored_total`: Total bytes stored
- `artifact_count_total`: Total artifact count
- `artifact_operation_errors_total`: Error count by type

### Metrics Integration

```python
from tools.artifact_metrics import get_artifact_metrics_collector

collector = get_artifact_metrics_collector()
stats = collector.get_stats()
print(f"Success rate: {stats['success_rate']:.2%}")
```

## Error Handling

### Common Error Scenarios

1. **Size Limit Exceeded**:
   ```python
   result = await backend.upload_artifact('large-file', large_data, {})
   if not result.success and 'exceeds limit' in result.error_message:
       print("File too large")
   ```

2. **Artifact Not Found**:
   ```python
   result = await backend.download_artifact('missing-id')
   if not result.success and 'not found' in result.error_message:
       print("Artifact not found")
   ```

3. **Integrity Check Failed**:
   ```python
   result = await backend.download_artifact('artifact-id')
   if not result.success and 'integrity check' in result.error_message:
       print("Data corrupted")
   ```

4. **Signature Verification Failed**:
   ```python
   result = await backend.download_artifact('artifact-id')
   if not result.success and 'signature' in result.error_message:
       print("Signature invalid")
   ```

## Best Practices

### Security

1. **Signing Key Management**: Use strong, rotated signing keys
2. **Access Control**: Implement application-level authorization
3. **Network Security**: Use HTTPS/TLS for S3 communications
4. **Audit Logging**: Enable comprehensive operation logging

### Performance

1. **Size Limits**: Set appropriate size limits based on use case
2. **Batch Operations**: Use list operations efficiently
3. **Caching**: Cache frequently accessed metadata
4. **Cleanup**: Implement expiration-based cleanup jobs

### Reliability

1. **Error Handling**: Always check operation results
2. **Retry Logic**: Implement retry for transient failures
3. **Monitoring**: Monitor error rates and performance
4. **Backup**: Regular backup of critical artifacts

## Deployment

### Local Development

```bash
# Create storage directory
mkdir -p ./artifacts/{data,metadata}

# Run with local backend
python your_app.py
```

### Production with S3

```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret

# Run with S3 backend
python your_app.py
```

### Docker Deployment

```dockerfile
FROM python:3.11

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Create artifact storage directory
RUN mkdir -p /app/artifacts/{data,metadata}

# Set signing key
ENV ARTIFACT_SIGNING_KEY=your-production-key

COPY . .
CMD ["python", "your_app.py"]
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Check file/directory permissions
2. **S3 Connection Failed**: Verify AWS credentials and region
3. **Size Limit Errors**: Adjust `max_size_bytes` configuration
4. **Integrity Failures**: Check for data corruption or key mismatches

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Health Checks

```python
# Check backend health
is_healthy = await backend.health_check()
if not is_healthy:
    print("Backend is not healthy")
```

## Migration Guide

### From Local to S3

1. **Export existing artifacts**:
   ```python
   artifacts = await local_backend.list_artifacts()
   for artifact in artifacts:
       data_result = await local_backend.download_artifact(artifact.id)
       if data_result.success:
           await s3_backend.upload_artifact(
               artifact.id, data_result.data, artifact.metadata
           )
   ```

2. **Update configuration**:
   ```python
   # Switch from local to S3 config
   config = {
       'bucket_name': 'production-artifacts',
       # ... S3 credentials
   }
   ```

3. **Update application code**:
   ```python
   # Change backend type
   backend = ArtifactStorageFactory.create_backend('s3', config)
   ```

## API Compatibility

- **Version**: 1.0.0
- **Python**: 3.9+
- **Dependencies**: Optional boto3 for S3 support
- **Async/Await**: Full async support required

## Contributing

1. **Tests**: Add tests for new features
2. **Documentation**: Update this guide for API changes
3. **Security**: Review security implications of changes
4. **Performance**: Consider performance impact of changes

## License

This implementation is part of the ATP project and follows the project's licensing terms.</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\artifact_tier_guide.md
