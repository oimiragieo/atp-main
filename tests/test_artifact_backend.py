#!/usr/bin/env python3
"""Comprehensive tests for GAP-302: Artifact / Binary Blob Tier Backend."""

import tempfile
import time
from pathlib import Path

import pytest

from tools.artifact_backend import (
    ArtifactMetadata,
    ArtifactStorageFactory,
    LocalArtifactStorageBackend,
    S3ArtifactStorageBackend,
    get_artifact_storage,
)
from tools.artifact_metrics import ArtifactStorageMetricsCollector, get_artifact_metrics_collector


class TestArtifactMetadata:
    """Test ArtifactMetadata dataclass."""

    def test_creation(self):
        """Test basic metadata creation."""
        metadata = ArtifactMetadata(
            id="test-artifact",
            name="Test Artifact",
            content_type="application/json",
            size_bytes=1024,
            checksum_sha256="abc123",
            signature="sig123",
            created_at=1234567890.0,
            metadata={"key": "value"},
        )

        assert metadata.id == "test-artifact"
        assert metadata.name == "Test Artifact"
        assert metadata.content_type == "application/json"
        assert metadata.size_bytes == 1024
        assert metadata.checksum_sha256 == "abc123"
        assert metadata.signature == "sig123"
        assert metadata.created_at == 1234567890.0
        assert metadata.metadata == {"key": "value"}

    def test_auto_created_at(self):
        """Test automatic created_at timestamp."""
        before = time.time()
        metadata = ArtifactMetadata(
            id="test", name="test", content_type="text/plain", size_bytes=100, checksum_sha256="hash", signature="sig"
        )
        after = time.time()

        assert before <= metadata.created_at <= after

    def test_auto_metadata_dict(self):
        """Test automatic metadata dict initialization."""
        metadata = ArtifactMetadata(
            id="test", name="test", content_type="text/plain", size_bytes=100, checksum_sha256="hash", signature="sig"
        )

        assert metadata.metadata == {}

    def test_is_expired_no_expiry(self):
        """Test expiration check when no expiry is set."""
        metadata = ArtifactMetadata(
            id="test", name="test", content_type="text/plain", size_bytes=100, checksum_sha256="hash", signature="sig"
        )

        assert not metadata.is_expired()

    def test_is_expired_future(self):
        """Test expiration check with future expiry."""
        future_time = time.time() + 3600  # 1 hour from now
        metadata = ArtifactMetadata(
            id="test",
            name="test",
            content_type="text/plain",
            size_bytes=100,
            checksum_sha256="hash",
            signature="sig",
            expires_at=future_time,
        )

        assert not metadata.is_expired()

    def test_is_expired_past(self):
        """Test expiration check with past expiry."""
        past_time = time.time() - 3600  # 1 hour ago
        metadata = ArtifactMetadata(
            id="test",
            name="test",
            content_type="text/plain",
            size_bytes=100,
            checksum_sha256="hash",
            signature="sig",
            expires_at=past_time,
        )

        assert metadata.is_expired()

    def test_verify_integrity_valid(self):
        """Test integrity verification with valid data."""
        import hashlib

        test_data = b"Hello, World!"
        checksum = hashlib.sha256(test_data).hexdigest()

        metadata = ArtifactMetadata(
            id="test",
            name="test",
            content_type="text/plain",
            size_bytes=len(test_data),
            checksum_sha256=checksum,
            signature="sig",
        )

        assert metadata.verify_integrity(test_data)

    def test_verify_integrity_invalid(self):
        """Test integrity verification with invalid data."""
        metadata = ArtifactMetadata(
            id="test",
            name="test",
            content_type="text/plain",
            size_bytes=100,
            checksum_sha256="invalid_hash",
            signature="sig",
        )

        assert not metadata.verify_integrity(b"different data")


class TestLocalArtifactStorageBackend:
    """Test LocalArtifactStorageBackend functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def backend(self, temp_dir):
        """Create a local backend instance."""
        config = {
            "base_path": str(temp_dir / "artifacts"),
            "max_size_bytes": 1024 * 1024,  # 1MB
            "signing_key": "test-key",
        }
        return LocalArtifactStorageBackend(config)

    @pytest.mark.asyncio
    async def test_health_check_success(self, backend):
        """Test successful health check."""
        assert await backend.health_check()

    @pytest.mark.asyncio
    async def test_upload_artifact_success(self, backend):
        """Test successful artifact upload."""
        test_data = b"Hello, World!"
        metadata = {"name": "test.txt", "content_type": "text/plain"}

        result = await backend.upload_artifact("test-artifact", test_data, metadata)

        assert result.success
        assert result.metadata is not None
        assert result.metadata.id == "test-artifact"
        assert result.metadata.name == "test.txt"
        assert result.metadata.content_type == "text/plain"
        assert result.metadata.size_bytes == len(test_data)
        assert result.upload_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_upload_artifact_size_limit_exceeded(self, backend):
        """Test upload failure due to size limit."""
        # Create data larger than limit
        large_data = b"x" * (1024 * 1024 + 1)  # 1MB + 1 byte
        metadata = {"name": "large.txt"}

        result = await backend.upload_artifact("large-artifact", large_data, metadata)

        assert not result.success
        assert result.metadata is None
        assert "exceeds limit" in result.error_message

    @pytest.mark.asyncio
    async def test_download_artifact_success(self, backend):
        """Test successful artifact download."""
        # First upload
        test_data = b"Hello, World!"
        metadata = {"name": "test.txt", "content_type": "text/plain"}
        upload_result = await backend.upload_artifact("test-artifact", test_data, metadata)
        assert upload_result.success

        # Then download
        download_result = await backend.download_artifact("test-artifact")

        assert download_result.success
        assert download_result.data == test_data
        assert download_result.metadata is not None
        assert download_result.metadata.id == "test-artifact"
        assert download_result.download_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_download_artifact_not_found(self, backend):
        """Test download of non-existent artifact."""
        result = await backend.download_artifact("non-existent")

        assert not result.success
        assert result.data is None
        assert result.metadata is None
        assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_download_artifact_expired(self, backend):
        """Test download of expired artifact."""
        # Upload with past expiry
        test_data = b"expired data"
        metadata = {
            "name": "expired.txt",
            "expires_at": time.time() - 3600,  # 1 hour ago
        }
        upload_result = await backend.upload_artifact("expired-artifact", test_data, metadata)
        assert upload_result.success

        # Try to download
        download_result = await backend.download_artifact("expired-artifact")

        assert not download_result.success
        assert download_result.data is None
        assert download_result.metadata is not None
        assert "expired" in download_result.error_message

    @pytest.mark.asyncio
    async def test_delete_artifact_success(self, backend):
        """Test successful artifact deletion."""
        # Upload first
        test_data = b"data to delete"
        metadata = {"name": "delete_me.txt"}
        upload_result = await backend.upload_artifact("delete-test", test_data, metadata)
        assert upload_result.success

        # Delete
        deleted = await backend.delete_artifact("delete-test")
        assert deleted

        # Verify it's gone
        download_result = await backend.download_artifact("delete-test")
        assert not download_result.success

    @pytest.mark.asyncio
    async def test_list_artifacts(self, backend):
        """Test listing artifacts."""
        # Upload multiple artifacts
        artifacts = [
            ("artifact-1", b"data 1", {"name": "file1.txt"}),
            ("artifact-2", b"data 2", {"name": "file2.txt"}),
            ("artifact-3", b"data 3", {"name": "file3.txt"}),
        ]

        for artifact_id, data, meta in artifacts:
            result = await backend.upload_artifact(artifact_id, data, meta)
            assert result.success

        # List all
        listed = await backend.list_artifacts()
        assert len(listed) == 3
        artifact_ids = {a.id for a in listed}
        assert artifact_ids == {"artifact-1", "artifact-2", "artifact-3"}

    @pytest.mark.asyncio
    async def test_list_artifacts_with_prefix(self, backend):
        """Test listing artifacts with prefix filter."""
        # Upload artifacts with different prefixes
        artifacts = [
            ("prefix1-file1", b"data 1", {"name": "file1.txt"}),
            ("prefix1-file2", b"data 2", {"name": "file2.txt"}),
            ("prefix2-file1", b"data 3", {"name": "file3.txt"}),
        ]

        for artifact_id, data, meta in artifacts:
            result = await backend.upload_artifact(artifact_id, data, meta)
            assert result.success

        # List with prefix
        listed = await backend.list_artifacts(prefix="prefix1")
        assert len(listed) == 2
        artifact_ids = {a.id for a in listed}
        assert artifact_ids == {"prefix1-file1", "prefix1-file2"}

    @pytest.mark.asyncio
    async def test_get_artifact_metadata(self, backend):
        """Test getting artifact metadata without downloading data."""
        # Upload first
        test_data = b"metadata test"
        metadata = {"name": "meta_test.txt", "custom": "value"}
        upload_result = await backend.upload_artifact("meta-test", test_data, metadata)
        assert upload_result.success

        # Get metadata
        meta = await backend.get_artifact_metadata("meta-test")
        assert meta is not None
        assert meta.id == "meta-test"
        assert meta.name == "meta_test.txt"
        assert meta.size_bytes == len(test_data)
        assert meta.metadata == metadata


class TestS3ArtifactStorageBackend:
    """Test S3ArtifactStorageBackend functionality."""

    @pytest.fixture
    def backend(self):
        """Create an S3 backend instance."""
        config = {
            "bucket_name": "test-bucket",
            "region": "us-east-1",
            "max_size_bytes": 1024 * 1024,
            "signing_key": "test-key",
        }
        return S3ArtifactStorageBackend(config)

    @pytest.mark.asyncio
    async def test_health_check_no_client(self, backend):
        """Test health check when S3 client is not available."""
        assert not await backend.health_check()

    @pytest.mark.asyncio
    async def test_operations_no_client(self, backend):
        """Test operations fail gracefully when S3 client is not available."""
        # Upload
        result = await backend.upload_artifact("test", b"data", {})
        assert not result.success
        assert "Unable to locate credentials" in result.error_message

        # Download
        result = await backend.download_artifact("test")
        assert not result.success
        assert "Unable to locate credentials" in result.error_message

        # Delete
        assert not await backend.delete_artifact("test")

        # List
        artifacts = await backend.list_artifacts()
        assert artifacts == []

        # Get metadata
        assert await backend.get_artifact_metadata("test") is None


class TestArtifactStorageFactory:
    """Test ArtifactStorageFactory functionality."""

    def test_create_local_backend(self):
        """Test creating local backend."""
        config = {"base_path": "/tmp/test"}  # noqa: S108
        backend = ArtifactStorageFactory.create_local_backend(config)
        assert isinstance(backend, LocalArtifactStorageBackend)

    def test_create_s3_backend(self):
        """Test creating S3 backend."""
        config = {"bucket_name": "test"}
        backend = ArtifactStorageFactory.create_s3_backend(config)
        assert isinstance(backend, S3ArtifactStorageBackend)

    def test_create_backend_by_type(self):
        """Test creating backend by type string."""
        # Local
        config = {"base_path": "/tmp/test"}  # noqa: S108
        backend = ArtifactStorageFactory.create_backend("local", config)
        assert isinstance(backend, LocalArtifactStorageBackend)

        # S3
        config = {"bucket_name": "test"}
        backend = ArtifactStorageFactory.create_backend("s3", config)
        assert isinstance(backend, S3ArtifactStorageBackend)

        # Invalid
        with pytest.raises(ValueError, match="Unknown backend type"):
            ArtifactStorageFactory.create_backend("invalid", {})


@pytest.mark.asyncio
class TestArtifactStorageContextManager:
    """Test artifact storage context manager."""

    async def test_context_manager(self):
        """Test context manager functionality."""
        config = {"base_path": "./test_artifacts"}
        async with get_artifact_storage("local", config) as backend:
            assert isinstance(backend, LocalArtifactStorageBackend)
            assert await backend.health_check()


class TestArtifactStorageMetricsIntegration:
    """Test metrics integration."""

    def test_metrics_callback_without_prometheus(self):
        """Test metrics callback when prometheus is not available."""
        from tools.artifact_metrics import artifact_storage_metrics_callback

        # Should not raise exception
        artifact_storage_metrics_callback("upload", 100.0, True, 1024)

    def test_metrics_collector(self):
        """Test metrics collector functionality."""
        collector = ArtifactStorageMetricsCollector()

        # Record some operations
        collector.record_operation("upload", 50.0, True, 1024)
        collector.record_operation("download", 25.0, True, 1024)
        collector.record_operation("upload", 75.0, False, 2048, "size_limit")

        stats = collector.get_stats()
        assert stats["total_operations"] == 3
        assert stats["successful_operations"] == 2
        assert stats["failed_operations"] == 1
        assert stats["total_bytes_stored"] == 1024  # Only successful uploads
        assert stats["artifact_count"] == 1
        assert stats["success_rate"] == 2 / 3

    def test_global_metrics_collector(self):
        """Test global metrics collector instance."""
        collector = get_artifact_metrics_collector()
        assert isinstance(collector, ArtifactStorageMetricsCollector)


class TestArtifactIntegrityAndSecurity:
    """Test artifact integrity and security features."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create a backend for integrity testing."""
        config = {
            "base_path": str(tmp_path / "artifacts"),
            "max_size_bytes": 1024 * 1024,
            "signing_key": "test-signing-key",
        }
        return LocalArtifactStorageBackend(config)

    @pytest.mark.asyncio
    async def test_signature_verification_valid(self, backend):
        """Test signature verification with valid data."""
        test_data = b"signed data"
        metadata = {"name": "signed.txt"}

        # Upload
        upload_result = await backend.upload_artifact("signed-test", test_data, metadata)
        assert upload_result.success

        # Download and verify signature is checked internally
        download_result = await backend.download_artifact("signed-test")
        assert download_result.success

    @pytest.mark.asyncio
    async def test_data_integrity_check(self, backend):
        """Test data integrity verification."""
        test_data = b"integrity test data"
        metadata = {"name": "integrity.txt"}

        # Upload
        upload_result = await backend.upload_artifact("integrity-test", test_data, metadata)
        assert upload_result.success

        # Download and verify integrity is checked internally
        download_result = await backend.download_artifact("integrity-test")
        assert download_result.success
        assert download_result.data == test_data

    @pytest.mark.asyncio
    async def test_size_limit_enforcement(self, backend):
        """Test strict size limit enforcement."""
        # Test exactly at limit
        limit_data = b"x" * 1024 * 1024  # Exactly 1MB
        metadata = {"name": "at_limit.txt"}

        result = await backend.upload_artifact("at-limit", limit_data, metadata)
        assert result.success  # Should succeed at exactly the limit

        # Test over limit
        over_limit_data = b"x" * (1024 * 1024 + 1)  # 1MB + 1 byte
        result = await backend.upload_artifact("over-limit", over_limit_data, metadata)
        assert not result.success
        assert "exceeds limit" in result.error_message


class TestArtifactStorageErrorHandling:
    """Test error handling in artifact storage."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create a backend for error testing."""
        config = {"base_path": str(tmp_path / "artifacts"), "max_size_bytes": 1024 * 1024, "signing_key": "test-key"}
        return LocalArtifactStorageBackend(config)

    @pytest.mark.asyncio
    async def test_corrupted_metadata_file(self, backend):
        """Test handling of corrupted metadata file."""
        # Create corrupted metadata file
        metadata_path = backend.metadata_path / "corrupted.json"
        metadata_path.write_text('{"invalid": json}')

        result = await backend.download_artifact("corrupted")
        assert not result.success
        assert "Expecting value" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_data_file(self, backend):
        """Test handling of missing data file."""
        # Create metadata but no data file
        test_data = b"test data"
        metadata = {"name": "missing_data.txt"}

        # Upload normally
        upload_result = await backend.upload_artifact("missing-data-test", test_data, metadata)
        assert upload_result.success

        # Manually delete data file
        data_file = backend.data_path / "missing-data-test.data"
        data_file.unlink()

        # Try to download
        download_result = await backend.download_artifact("missing-data-test")
        assert not download_result.success
        assert download_result.error_message is not None
        assert "data file" in download_result.error_message
        assert "not found" in download_result.error_message
