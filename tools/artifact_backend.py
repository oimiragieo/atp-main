#!/usr/bin/env python3
"""GAP-302: Artifact / Binary Blob Tier Backend Interfaces and Implementations.

Provides signed artifact metadata schema and pluggable storage backends for:
- Local filesystem storage for development/testing
- S3-compatible storage for production
- Signed metadata with integrity verification
- Size limits and quota enforcement
"""

import abc
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .artifact_metrics import artifact_storage_metrics_callback

# Setup logger
logger = logging.getLogger(__name__)


@dataclass
class ArtifactMetadata:
    """Metadata for stored artifacts with integrity verification."""

    id: str
    name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    signature: str
    created_at: float | None = None
    expires_at: float | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.metadata is None:
            self.metadata = {}

    def is_expired(self) -> bool:
        """Check if artifact has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def verify_integrity(self, data: bytes) -> bool:
        """Verify data integrity using stored checksum."""
        computed_checksum = hashlib.sha256(data).hexdigest()
        return hmac.compare_digest(computed_checksum, self.checksum_sha256)


@dataclass
class ArtifactUploadResult:
    """Result of artifact upload operation."""

    metadata: ArtifactMetadata
    upload_duration_ms: float
    success: bool
    error_message: str | None = None


@dataclass
class ArtifactDownloadResult:
    """Result of artifact download operation."""

    data: bytes | None
    metadata: ArtifactMetadata | None
    download_duration_ms: float
    success: bool
    error_message: str | None = None


class ArtifactStorageBackend(Protocol):
    """Abstract protocol for artifact storage backends."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Check backend health and connectivity."""
        pass

    @abc.abstractmethod
    async def upload_artifact(self, artifact_id: str, data: bytes, metadata: dict[str, Any]) -> ArtifactUploadResult:
        """Upload artifact data with metadata."""
        pass

    @abc.abstractmethod
    async def download_artifact(self, artifact_id: str) -> ArtifactDownloadResult:
        """Download artifact data and metadata."""
        pass

    @abc.abstractmethod
    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact and its metadata."""
        pass

    @abc.abstractmethod
    async def list_artifacts(self, prefix: str | None = None, limit: int = 100) -> list[ArtifactMetadata]:
        """List artifacts with optional prefix filter."""
        pass

    @abc.abstractmethod
    async def get_artifact_metadata(self, artifact_id: str) -> ArtifactMetadata | None:
        """Get artifact metadata without downloading data."""
        pass


class LocalArtifactStorageBackend:
    """Local filesystem backend for artifact storage (development/testing)."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.base_path = Path(config.get("base_path", "./artifacts"))
        self.max_size_bytes = config.get("max_size_bytes", 100 * 1024 * 1024)  # 100MB default
        self.signing_key = config.get("signing_key", "default-key").encode()

        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.base_path / "metadata"
        self.data_path = self.base_path / "data"
        self.metadata_path.mkdir(exist_ok=True)
        self.data_path.mkdir(exist_ok=True)

    async def health_check(self) -> bool:
        """Check if storage directories are accessible."""
        try:
            # Test write access
            test_file = self.metadata_path / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def _generate_signature(self, data: bytes, metadata: dict[str, Any]) -> str:
        """Generate HMAC signature for artifact integrity."""
        content = json.dumps(metadata, sort_keys=True).encode() + data
        return hmac.new(self.signing_key, content, hashlib.sha256).hexdigest()

    def _verify_signature(self, data: bytes, metadata: dict[str, Any], signature: str) -> bool:
        """Verify HMAC signature for artifact integrity."""
        expected = self._generate_signature(data, metadata)
        return hmac.compare_digest(expected, signature)

    async def upload_artifact(self, artifact_id: str, data: bytes, metadata: dict[str, Any]) -> ArtifactUploadResult:
        """Upload artifact to local filesystem."""
        start_time = time.time()

        try:
            # Check size limits
            if len(data) > self.max_size_bytes:
                error_result = ArtifactUploadResult(
                    metadata=None,
                    upload_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact size {len(data)} exceeds limit {self.max_size_bytes}",
                )
                # Record metrics
                artifact_storage_metrics_callback(
                    "upload", error_result.upload_duration_ms, False, len(data), "size_limit"
                )
                return error_result

            # Generate checksum and signature
            checksum = hashlib.sha256(data).hexdigest()
            signature = self._generate_signature(data, metadata)

            # Create metadata
            artifact_metadata = ArtifactMetadata(
                id=artifact_id,
                name=metadata.get("name", artifact_id),
                content_type=metadata.get("content_type", "application/octet-stream"),
                size_bytes=len(data),
                checksum_sha256=checksum,
                signature=signature,
                created_at=time.time(),
                expires_at=metadata.get("expires_at"),
                metadata=metadata,
            )

            # Save data file
            data_file = self.data_path / f"{artifact_id}.data"
            data_file.write_bytes(data)

            # Save metadata file
            metadata_file = self.metadata_path / f"{artifact_id}.json"
            metadata_dict = {
                "id": artifact_metadata.id,
                "name": artifact_metadata.name,
                "content_type": artifact_metadata.content_type,
                "size_bytes": artifact_metadata.size_bytes,
                "checksum_sha256": artifact_metadata.checksum_sha256,
                "signature": artifact_metadata.signature,
                "created_at": artifact_metadata.created_at,
                "expires_at": artifact_metadata.expires_at,
                "metadata": artifact_metadata.metadata,
            }
            metadata_file.write_text(json.dumps(metadata_dict, indent=2))

            upload_result = ArtifactUploadResult(
                metadata=artifact_metadata, upload_duration_ms=(time.time() - start_time) * 1000, success=True
            )
            # Record metrics
            artifact_storage_metrics_callback("upload", upload_result.upload_duration_ms, True, len(data))
            return upload_result

        except Exception as e:
            logger.error(f"Upload failed for {artifact_id}: {e}")
            error_result = ArtifactUploadResult(
                metadata=None, upload_duration_ms=(time.time() - start_time) * 1000, success=False, error_message=str(e)
            )
            # Record metrics
            artifact_storage_metrics_callback("upload", error_result.upload_duration_ms, False, 0, "exception")
            return error_result

    async def download_artifact(self, artifact_id: str) -> ArtifactDownloadResult:
        """Download artifact from local filesystem."""
        start_time = time.time()

        try:
            # Load metadata
            metadata_file = self.metadata_path / f"{artifact_id}.json"
            if not metadata_file.exists():
                return ArtifactDownloadResult(
                    data=None,
                    metadata=None,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact {artifact_id} not found",
                )

            metadata_dict = json.loads(metadata_file.read_text())
            metadata = ArtifactMetadata(**metadata_dict)

            # Check expiration
            if metadata.is_expired():
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact {artifact_id} has expired",
                )

            # Load data
            data_file = self.data_path / f"{artifact_id}.data"
            if not data_file.exists():
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact data file for {artifact_id} not found",
                )

            data = data_file.read_bytes()

            # Verify integrity
            if not metadata.verify_integrity(data):
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Integrity check failed for {artifact_id}",
                )

            # Verify signature
            if not self._verify_signature(data, metadata.metadata, metadata.signature):
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Signature verification failed for {artifact_id}",
                )

            return ArtifactDownloadResult(
                data=data, metadata=metadata, download_duration_ms=(time.time() - start_time) * 1000, success=True
            )

        except Exception as e:
            logger.error(f"Download failed for {artifact_id}: {e}")
            error_result = ArtifactDownloadResult(
                data=None,
                metadata=None,
                download_duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message=str(e),
            )
            # Record metrics
            artifact_storage_metrics_callback("download", error_result.download_duration_ms, False, 0, "exception")
            return error_result

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact and its metadata."""
        try:
            # Delete data file
            data_file = self.data_path / f"{artifact_id}.data"
            if data_file.exists():
                data_file.unlink()

            # Delete metadata file
            metadata_file = self.metadata_path / f"{artifact_id}.json"
            if metadata_file.exists():
                metadata_file.unlink()

            return True
        except Exception as e:
            logger.error(f"Delete failed for {artifact_id}: {e}")
            return False

    async def list_artifacts(self, prefix: str | None = None, limit: int = 100) -> list[ArtifactMetadata]:
        """List artifacts with optional prefix filter."""
        try:
            artifacts = []
            for metadata_file in self.metadata_path.glob("*.json"):
                if len(artifacts) >= limit:
                    break

                try:
                    metadata_dict = json.loads(metadata_file.read_text())
                    metadata = ArtifactMetadata(**metadata_dict)

                    # Apply prefix filter
                    if prefix and not metadata.id.startswith(prefix):
                        continue

                    artifacts.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to load metadata from {metadata_file}: {e}")
                    continue

            return artifacts
        except Exception as e:
            logger.error(f"List artifacts failed: {e}")
            return []

    async def get_artifact_metadata(self, artifact_id: str) -> ArtifactMetadata | None:
        """Get artifact metadata without downloading data."""
        try:
            metadata_file = self.metadata_path / f"{artifact_id}.json"
            if not metadata_file.exists():
                return None

            metadata_dict = json.loads(metadata_file.read_text())
            return ArtifactMetadata(**metadata_dict)
        except Exception as e:
            logger.error(f"Get metadata failed for {artifact_id}: {e}")
            return None


class S3ArtifactStorageBackend:
    """S3-compatible backend for artifact storage (production)."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.bucket_name = config.get("bucket_name", "artifacts")
        self.region = config.get("region", "us-east-1")
        self.max_size_bytes = config.get("max_size_bytes", 100 * 1024 * 1024)  # 100MB default
        self.signing_key = config.get("signing_key", "default-key").encode()

        # S3 client would be initialized here if boto3 is available
        self.s3_client = None
        try:
            import boto3

            self.s3_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=config.get("aws_access_key_id"),
                aws_secret_access_key=config.get("aws_secret_access_key"),
            )
        except ImportError:
            logger.warning("boto3 not available, S3 backend will not function")

    async def health_check(self) -> bool:
        """Check S3 connectivity."""
        if not self.s3_client:
            return False

        try:
            # Test connectivity by listing objects (with max 1)
            self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)
            return True
        except Exception as e:
            logger.error(f"S3 health check failed: {e}")
            return False

    def _generate_signature(self, data: bytes, metadata: dict[str, Any]) -> str:
        """Generate HMAC signature for artifact integrity."""
        content = json.dumps(metadata, sort_keys=True).encode() + data
        return hmac.new(self.signing_key, content, hashlib.sha256).hexdigest()

    def _verify_signature(self, data: bytes, metadata: dict[str, Any], signature: str) -> bool:
        """Verify HMAC signature for artifact integrity."""
        expected = self._generate_signature(data, metadata)
        return hmac.compare_digest(expected, signature)

    async def upload_artifact(self, artifact_id: str, data: bytes, metadata: dict[str, Any]) -> ArtifactUploadResult:
        """Upload artifact to S3."""
        start_time = time.time()

        if not self.s3_client:
            return ArtifactUploadResult(
                metadata=None,
                upload_duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message="S3 client not available",
            )

        try:
            # Check size limits
            if len(data) > self.max_size_bytes:
                return ArtifactUploadResult(
                    metadata=None,
                    upload_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact size {len(data)} exceeds limit {self.max_size_bytes}",
                )

            # Generate checksum and signature
            checksum = hashlib.sha256(data).hexdigest()
            signature = self._generate_signature(data, metadata)

            # Create metadata
            artifact_metadata = ArtifactMetadata(
                id=artifact_id,
                name=metadata.get("name", artifact_id),
                content_type=metadata.get("content_type", "application/octet-stream"),
                size_bytes=len(data),
                checksum_sha256=checksum,
                signature=signature,
                created_at=time.time(),
                expires_at=metadata.get("expires_at"),
                metadata=metadata,
            )

            # Prepare S3 metadata
            s3_metadata = {
                "id": artifact_metadata.id,
                "name": artifact_metadata.name,
                "content_type": artifact_metadata.content_type,
                "size_bytes": str(artifact_metadata.size_bytes),
                "checksum_sha256": artifact_metadata.checksum_sha256,
                "signature": artifact_metadata.signature,
                "created_at": str(artifact_metadata.created_at),
                "expires_at": str(artifact_metadata.expires_at) if artifact_metadata.expires_at else "",
                "custom_metadata": json.dumps(artifact_metadata.metadata),
            }

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"artifacts/{artifact_id}",
                Body=data,
                ContentType=artifact_metadata.content_type,
                Metadata=s3_metadata,
            )

            return ArtifactUploadResult(
                metadata=artifact_metadata, upload_duration_ms=(time.time() - start_time) * 1000, success=True
            )

        except Exception as e:
            logger.error(f"S3 upload failed for {artifact_id}: {e}")
            return ArtifactUploadResult(
                metadata=None, upload_duration_ms=(time.time() - start_time) * 1000, success=False, error_message=str(e)
            )

    async def download_artifact(self, artifact_id: str) -> ArtifactDownloadResult:
        """Download artifact from S3."""
        start_time = time.time()

        if not self.s3_client:
            return ArtifactDownloadResult(
                data=None,
                metadata=None,
                download_duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message="S3 client not available",
            )

        try:
            # Download from S3
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=f"artifacts/{artifact_id}")

            data = response["Body"].read()
            s3_metadata = response.get("Metadata", {})

            # Reconstruct metadata
            metadata = ArtifactMetadata(
                id=s3_metadata.get("id", artifact_id),
                name=s3_metadata.get("name", artifact_id),
                content_type=s3_metadata.get("content_type", "application/octet-stream"),
                size_bytes=int(s3_metadata.get("size_bytes", 0)),
                checksum_sha256=s3_metadata.get("checksum_sha256", ""),
                signature=s3_metadata.get("signature", ""),
                created_at=float(s3_metadata.get("created_at", time.time())),
                expires_at=float(s3_metadata["expires_at"]) if s3_metadata.get("expires_at") else None,
                metadata=json.loads(s3_metadata.get("custom_metadata", "{}")),
            )

            # Check expiration
            if metadata.is_expired():
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Artifact {artifact_id} has expired",
                )

            # Verify integrity
            if not metadata.verify_integrity(data):
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Integrity check failed for {artifact_id}",
                )

            # Verify signature
            if not self._verify_signature(data, metadata.metadata, metadata.signature):
                return ArtifactDownloadResult(
                    data=None,
                    metadata=metadata,
                    download_duration_ms=(time.time() - start_time) * 1000,
                    success=False,
                    error_message=f"Signature verification failed for {artifact_id}",
                )

            return ArtifactDownloadResult(
                data=data, metadata=metadata, download_duration_ms=(time.time() - start_time) * 1000, success=True
            )

        except self.s3_client.exceptions.NoSuchKey:
            return ArtifactDownloadResult(
                data=None,
                metadata=None,
                download_duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message=f"Artifact {artifact_id} not found",
            )
        except Exception as e:
            logger.error(f"S3 download failed for {artifact_id}: {e}")
            return ArtifactDownloadResult(
                data=None,
                metadata=None,
                download_duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message=str(e),
            )

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact from S3."""
        if not self.s3_client:
            return False

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=f"artifacts/{artifact_id}")
            return True
        except Exception as e:
            logger.error(f"S3 delete failed for {artifact_id}: {e}")
            return False

    async def list_artifacts(self, prefix: str | None = None, limit: int = 100) -> list[ArtifactMetadata]:
        """List artifacts in S3 with optional prefix filter."""
        if not self.s3_client:
            return []

        try:
            # List objects with prefix
            s3_prefix = f"artifacts/{prefix}" if prefix else "artifacts/"
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=s3_prefix, MaxKeys=limit)

            artifacts = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    try:
                        # Get object metadata
                        head_response = self.s3_client.head_object(Bucket=self.bucket_name, Key=obj["Key"])

                        s3_metadata = head_response.get("Metadata", {})
                        artifact_id = obj["Key"].replace("artifacts/", "")

                        metadata = ArtifactMetadata(
                            id=artifact_id,
                            name=s3_metadata.get("name", artifact_id),
                            content_type=s3_metadata.get("content_type", "application/octet-stream"),
                            size_bytes=int(s3_metadata.get("size_bytes", obj["Size"])),
                            checksum_sha256=s3_metadata.get("checksum_sha256", ""),
                            signature=s3_metadata.get("signature", ""),
                            created_at=float(s3_metadata.get("created_at", obj["LastModified"].timestamp())),
                            expires_at=float(s3_metadata["expires_at"]) if s3_metadata.get("expires_at") else None,
                            metadata=json.loads(s3_metadata.get("custom_metadata", "{}")),
                        )

                        artifacts.append(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to load metadata for {obj['Key']}: {e}")
                        continue

            return artifacts
        except Exception as e:
            logger.error(f"S3 list artifacts failed: {e}")
            return []

    async def get_artifact_metadata(self, artifact_id: str) -> ArtifactMetadata | None:
        """Get artifact metadata from S3 without downloading data."""
        if not self.s3_client:
            return None

        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=f"artifacts/{artifact_id}")

            s3_metadata = response.get("Metadata", {})

            return ArtifactMetadata(
                id=artifact_id,
                name=s3_metadata.get("name", artifact_id),
                content_type=s3_metadata.get("content_type", "application/octet-stream"),
                size_bytes=int(s3_metadata.get("size_bytes", response.get("ContentLength", 0))),
                checksum_sha256=s3_metadata.get("checksum_sha256", ""),
                signature=s3_metadata.get("signature", ""),
                created_at=float(s3_metadata.get("created_at", response["LastModified"].timestamp())),
                expires_at=float(s3_metadata["expires_at"]) if s3_metadata.get("expires_at") else None,
                metadata=json.loads(s3_metadata.get("custom_metadata", "{}")),
            )
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.error(f"S3 get metadata failed for {artifact_id}: {e}")
            return None


class ArtifactStorageFactory:
    """Factory for creating artifact storage backends."""

    @staticmethod
    def create_local_backend(config: dict[str, Any] | None = None) -> ArtifactStorageBackend:
        """Create a local filesystem backend."""
        if config is None:
            config = {}
        return LocalArtifactStorageBackend(config)

    @staticmethod
    def create_s3_backend(config: dict[str, Any]) -> ArtifactStorageBackend:
        """Create an S3 backend."""
        return S3ArtifactStorageBackend(config)

    @staticmethod
    def create_backend(backend_type: str, config: dict[str, Any]) -> ArtifactStorageBackend:
        """Create a backend by type."""
        if backend_type == "local":
            return ArtifactStorageFactory.create_local_backend(config)
        elif backend_type == "s3":
            return ArtifactStorageFactory.create_s3_backend(config)
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")


# Context manager for artifact storage
class ArtifactStorageContext:
    """Context manager for artifact storage backends."""

    def __init__(self, backend: ArtifactStorageBackend):
        self.backend = backend

    async def __aenter__(self):
        return self.backend

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cleanup if needed
        pass


def get_artifact_storage(backend_type: str = "local", config: dict[str, Any] | None = None) -> ArtifactStorageContext:
    """Context manager for artifact storage connections."""
    if config is None:
        config = {}
    backend = ArtifactStorageFactory.create_backend(backend_type, config)
    return ArtifactStorageContext(backend)


# Demo function
async def demo():
    """Demonstrate artifact storage functionality."""
    print("=== Artifact Storage Demo ===")

    # Create local backend
    config = {
        "base_path": "./demo_artifacts",
        "max_size_bytes": 10 * 1024 * 1024,  # 10MB
        "signing_key": "demo-key",
    }
    backend = ArtifactStorageFactory.create_local_backend(config)

    # Test data
    test_data = b"Hello, this is test artifact data!"
    metadata = {"name": "test_artifact.txt", "content_type": "text/plain", "description": "Demo artifact for testing"}

    # Upload artifact
    print("Uploading artifact...")
    upload_result = await backend.upload_artifact("test-artifact-1", test_data, metadata)
    if upload_result.success:
        print(f"✅ Upload successful: {upload_result.metadata.id}")
        print(f"   Size: {upload_result.metadata.size_bytes} bytes")
        print(f"   Checksum: {upload_result.metadata.checksum_sha256[:16]}...")
    else:
        print(f"❌ Upload failed: {upload_result.error_message}")
        return

    # Download artifact
    print("\nDownloading artifact...")
    download_result = await backend.download_artifact("test-artifact-1")
    if download_result.success:
        print(f"✅ Download successful: {len(download_result.data)} bytes")
        print(f"   Data matches: {download_result.data == test_data}")
    else:
        print(f"❌ Download failed: {download_result.error_message}")

    # List artifacts
    print("\nListing artifacts...")
    artifacts = await backend.list_artifacts()
    print(f"Found {len(artifacts)} artifacts:")
    for artifact in artifacts:
        print(f"  - {artifact.id}: {artifact.name} ({artifact.size_bytes} bytes)")

    # Get metadata
    print("\nGetting metadata...")
    meta = await backend.get_artifact_metadata("test-artifact-1")
    if meta:
        print(f"✅ Metadata: {meta.name}, expires: {meta.expires_at}")

    # Cleanup
    print("\nCleaning up...")
    deleted = await backend.delete_artifact("test-artifact-1")
    print(f"✅ Deleted: {deleted}")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo())
