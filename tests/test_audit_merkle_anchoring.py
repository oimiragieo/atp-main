#!/usr/bin/env python3
"""Tests for Audit Merkle Root Anchoring Strategy."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tools.audit_merkle_anchoring import (
    AnchoringConfig,
    AnchoringResult,
    AuditMerkleAnchoring,
    BlockchainBackend,
    TransparencyLogBackend,
)


class TestAnchoringConfig:
    """Test AnchoringConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AnchoringConfig(audit_log_path="/tmp/audit.log")
        assert config.audit_log_path == "/tmp/audit.log"
        assert config.anchoring_backend == "transparency_log"
        assert config.publish_interval_seconds == 3600
        assert config.max_entries_per_root == 1000
        assert config.enable_verification is True
        assert config.verification_interval_seconds == 300

    def test_custom_config(self):
        """Test custom configuration values."""
        config = AnchoringConfig(
            audit_log_path="/tmp/audit.log",
            anchoring_backend="blockchain",
            publish_interval_seconds=1800,
            max_entries_per_root=500,
            enable_verification=False,
            verification_interval_seconds=600,
        )
        assert config.anchoring_backend == "blockchain"
        assert config.publish_interval_seconds == 1800
        assert config.max_entries_per_root == 500
        assert config.enable_verification is False
        assert config.verification_interval_seconds == 600


class TestAnchoringResult:
    """Test AnchoringResult dataclass."""

    def test_success_result(self):
        """Test successful anchoring result."""
        result = AnchoringResult(
            timestamp=1234567890.0, root_hash="abc123", entry_count=100, backend="transparency_log", success=True
        )
        assert result.timestamp == 1234567890.0
        assert result.root_hash == "abc123"
        assert result.entry_count == 100
        assert result.backend == "transparency_log"
        assert result.success is True
        assert result.error_message is None
        assert result.verification_status is None

    def test_failure_result(self):
        """Test failed anchoring result."""
        result = AnchoringResult(
            timestamp=1234567890.0,
            root_hash="",
            entry_count=0,
            backend="transparency_log",
            success=False,
            error_message="Backend error",
        )
        assert result.success is False
        assert result.error_message == "Backend error"


class TestTransparencyLogBackend:
    """Test TransparencyLogBackend functionality."""

    @pytest.mark.asyncio
    async def test_publish_root_success(self):
        """Test successful root publication to transparency log."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "transparency.log"
            backend = TransparencyLogBackend(str(log_path))

            success = await backend.publish_root("test_root_hash", {"entry_count": 100, "timestamp": time.time()})

            assert success is True
            assert log_path.exists()

            # Verify the entry was written
            with open(log_path) as f:  # noqa: ASYNC230
                content = f.read()
                data = json.loads(content.strip())
                assert data["root_hash"] == "test_root_hash"
                assert data["backend"] == "transparency_log"

    @pytest.mark.asyncio
    async def test_verify_root_success(self):
        """Test successful root verification against transparency log."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "transparency.log"
            backend = TransparencyLogBackend(str(log_path))

            # First publish a root
            test_root = "test_root_hash_123"
            await backend.publish_root(test_root, {"entry_count": 50})

            # Then verify it
            verified = await backend.verify_root(test_root)
            assert verified is True

    @pytest.mark.asyncio
    async def test_verify_root_not_found(self):
        """Test verification of non-existent root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "transparency.log"
            backend = TransparencyLogBackend(str(log_path))

            verified = await backend.verify_root("non_existent_root")
            assert verified is False


class TestBlockchainBackend:
    """Test BlockchainBackend functionality."""

    @pytest.mark.asyncio
    async def test_publish_root_simulated(self):
        """Test simulated blockchain root publication."""
        backend = BlockchainBackend()

        success = await backend.publish_root("blockchain_root_hash", {"entry_count": 200, "timestamp": time.time()})

        # Since it's simulated, it should always succeed
        assert success is True

    @pytest.mark.asyncio
    async def test_verify_root_simulated(self):
        """Test simulated blockchain root verification."""
        backend = BlockchainBackend()

        verified = await backend.verify_root("blockchain_root_hash")

        # Since it's simulated, it should always succeed
        assert verified is True


class TestAuditMerkleAnchoring:
    """Test AuditMerkleAnchoring main functionality."""

    def test_initialization_transparency_log(self):
        """Test initialization with transparency log backend."""
        config = AnchoringConfig(audit_log_path="/tmp/test_audit.log")
        anchoring = AuditMerkleAnchoring(config)

        assert config.audit_log_path in str(anchoring.config.audit_log_path)
        assert "transparency_log" in anchoring.backends
        assert isinstance(anchoring.backends["transparency_log"], TransparencyLogBackend)

    def test_initialization_blockchain(self):
        """Test initialization with blockchain backend."""
        config = AnchoringConfig(audit_log_path="/tmp/test_audit.log", anchoring_backend="blockchain")
        anchoring = AuditMerkleAnchoring(config)

        assert "blockchain" in anchoring.backends
        assert isinstance(anchoring.backends["blockchain"], BlockchainBackend)

    def test_initialization_invalid_backend(self):
        """Test initialization with invalid backend."""
        config = AnchoringConfig(audit_log_path="/tmp/test_audit.log", anchoring_backend="invalid_backend")

        with pytest.raises(ValueError, match="Unsupported anchoring backend"):
            AuditMerkleAnchoring(config)

    @pytest.mark.asyncio
    async def test_read_audit_entries_empty_file(self):
        """Test reading from empty audit log file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"
            audit_path.touch()  # Create empty file

            config = AnchoringConfig(audit_log_path=str(audit_path))
            anchoring = AuditMerkleAnchoring(config)

            entries = await anchoring._read_audit_entries()
            assert entries == []

    @pytest.mark.asyncio
    async def test_read_audit_entries_with_data(self):
        """Test reading audit entries from file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"

            # Write some test audit entries
            test_entries = [
                {"event": {"action": "login", "user": "alice"}, "hash": "hash1"},
                {"event": {"action": "access", "user": "alice"}, "hash": "hash2"},
            ]

            with open(audit_path, "w") as f:  # noqa: ASYNC230
                for entry in test_entries:
                    f.write(json.dumps(entry) + "\n")

            config = AnchoringConfig(audit_log_path=str(audit_path))
            anchoring = AuditMerkleAnchoring(config)

            entries = await anchoring._read_audit_entries()
            assert len(entries) == 2
            assert entries[0]["event"]["action"] == "login"
            assert entries[1]["event"]["action"] == "access"

    def test_compute_merkle_root_empty(self):
        """Test Merkle root computation with empty entries."""
        config = AnchoringConfig(audit_log_path="/tmp/test.log")
        anchoring = AuditMerkleAnchoring(config)

        root = anchoring._compute_merkle_root([])
        assert len(root) == 64  # SHA256 hex length

    def test_compute_merkle_root_with_entries(self):
        """Test Merkle root computation with audit entries."""
        config = AnchoringConfig(audit_log_path="/tmp/test.log")
        anchoring = AuditMerkleAnchoring(config)

        entries = [
            {"event": {"action": "login"}, "hash": "hash1"},
            {"event": {"action": "access"}, "hash": "hash2"},
        ]

        root = anchoring._compute_merkle_root(entries)
        assert len(root) == 64  # SHA256 hex length
        assert root != anchoring._compute_merkle_root([])  # Different from empty

    @pytest.mark.asyncio
    async def test_publish_root_no_entries(self):
        """Test publishing root when no audit entries exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"
            audit_path.touch()  # Create empty file

            config = AnchoringConfig(audit_log_path=str(audit_path))
            anchoring = AuditMerkleAnchoring(config)

            result = await anchoring.publish_root()

            assert result.success is False
            assert result.entry_count == 0
            assert "No audit entries found" in result.error_message

    @pytest.mark.asyncio
    async def test_publish_root_success(self):
        """Test successful root publishing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"

            # Create test audit entries
            test_entries = [
                {"event": {"action": "login", "user": "alice"}, "hash": "hash1"},
                {"event": {"action": "access", "user": "alice"}, "hash": "hash2"},
            ]

            with open(audit_path, "w") as f:  # noqa: ASYNC230
                for entry in test_entries:
                    f.write(json.dumps(entry) + "\n")

            config = AnchoringConfig(audit_log_path=str(audit_path))
            anchoring = AuditMerkleAnchoring(config)

            result = await anchoring.publish_root()

            assert result.success is True
            assert result.entry_count == 2
            assert len(result.root_hash) == 64  # SHA256 hex length
            assert result.backend == "transparency_log"

    @pytest.mark.asyncio
    async def test_verify_root_success(self):
        """Test successful root verification."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"

            # Create test audit entries
            test_entries = [
                {"event": {"action": "login"}, "hash": "hash1"},
            ]

            with open(audit_path, "w") as f:  # noqa: ASYNC230
                for entry in test_entries:
                    f.write(json.dumps(entry) + "\n")

            config = AnchoringConfig(audit_log_path=str(audit_path))
            anchoring = AuditMerkleAnchoring(config)

            # First publish
            publish_result = await anchoring.publish_root()
            assert publish_result.success is True

            # Then verify
            verified = await anchoring.verify_root(publish_result.root_hash)
            assert verified is True

    @pytest.mark.asyncio
    async def test_verify_root_failure(self):
        """Test root verification failure."""
        config = AnchoringConfig(audit_log_path="/tmp/nonexistent.log")
        anchoring = AuditMerkleAnchoring(config)

        verified = await anchoring.verify_root("fake_root_hash")
        assert verified is False


class TestCLIIntegration:
    """Test CLI integration and argument parsing."""

    def test_create_parser(self):
        """Test argument parser creation."""
        from tools.audit_merkle_anchoring import create_parser

        parser = create_parser()
        assert parser is not None

        # Test parsing basic arguments
        args = parser.parse_args(
            ["--audit-log", "/tmp/audit.log", "--backend", "transparency_log", "--publish-interval", "1800"]
        )

        assert args.audit_log == "/tmp/audit.log"
        assert args.backend == "transparency_log"
        assert args.publish_interval == 1800
        assert args.publish_once is False
        assert args.verify is False
        assert args.compare_backends is False

    def test_parser_publish_once(self):
        """Test publish-once flag parsing."""
        from tools.audit_merkle_anchoring import create_parser

        parser = create_parser()
        args = parser.parse_args(["--audit-log", "/tmp/audit.log", "--publish-once"])

        assert args.publish_once is True

    def test_parser_compare_backends(self):
        """Test compare-backends flag parsing."""
        from tools.audit_merkle_anchoring import create_parser

        parser = create_parser()
        args = parser.parse_args(["--audit-log", "/tmp/audit.log", "--compare-backends"])

        assert args.compare_backends is True


class TestBackendComparison:
    """Test backend comparison functionality."""

    @pytest.mark.asyncio
    async def test_compare_anchoring_backends(self):
        """Test comparing different anchoring backends."""
        from tools.audit_merkle_anchoring import compare_anchoring_backends

        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"

            # Create test audit entries
            test_entries = [
                {"event": {"action": "login"}, "hash": "hash1"},
                {"event": {"action": "access"}, "hash": "hash2"},
            ]

            with open(audit_path, "w") as f:  # noqa: ASYNC230
                for entry in test_entries:
                    f.write(json.dumps(entry) + "\n")

            # This should not raise an exception
            await compare_anchoring_backends(str(audit_path))


class TestErrorHandling:
    """Test error handling in anchoring system."""

    @pytest.mark.asyncio
    async def test_publish_with_backend_error(self):
        """Test publishing when backend fails."""
        config = AnchoringConfig(audit_log_path="/tmp/test.log")
        anchoring = AuditMerkleAnchoring(config)

        # Mock backend to fail
        mock_backend = AsyncMock()
        mock_backend.publish_root.return_value = False
        anchoring.backends["transparency_log"] = mock_backend

        # Create a temporary audit file with entries
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.log"
            with open(audit_path, "w") as f:  # noqa: ASYNC230
                f.write('{"event": {"action": "test"}, "hash": "testhash"}\n')

            config.audit_log_path = str(audit_path)
            anchoring.config = config

            result = await anchoring.publish_root()

            assert result.success is False
            assert result.error_message == "Backend publish failed"

    @pytest.mark.asyncio
    async def test_verify_with_backend_error(self):
        """Test verification when backend fails."""
        config = AnchoringConfig(audit_log_path="/tmp/test.log")
        anchoring = AuditMerkleAnchoring(config)

        # Mock backend to fail
        mock_backend = AsyncMock()
        mock_backend.verify_root.side_effect = Exception("Backend error")
        anchoring.backends["transparency_log"] = mock_backend

        verified = await anchoring.verify_root("test_hash")
        assert verified is False


class TestMetricsIntegration:
    """Test metrics integration."""

    @pytest.mark.asyncio
    async def test_publish_records_metrics(self):
        """Test that publishing records metrics."""
        with (
            patch("tools.audit_merkle_anchoring.MERKLE_ROOT_PUBLISH_TOTAL") as mock_counter,
            patch("tools.audit_merkle_anchoring.MERKLE_ROOT_PUBLISH_LATENCY") as mock_histogram,
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                audit_path = Path(temp_dir) / "audit.log"

                # Create test audit entries
                with open(audit_path, "w") as f:  # noqa: ASYNC230
                    f.write('{"event": {"action": "test"}, "hash": "testhash"}\n')

                config = AnchoringConfig(audit_log_path=str(audit_path))
                anchoring = AuditMerkleAnchoring(config)

                result = await anchoring.publish_root()

                assert result.success is True
                mock_counter.inc.assert_called_once()
                mock_histogram.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_records_metrics(self):
        """Test that verification records metrics."""
        with (
            patch("tools.audit_merkle_anchoring.MERKLE_ROOT_VERIFICATION_TOTAL") as mock_total,
            patch("tools.audit_merkle_anchoring.MERKLE_ROOT_VERIFICATION_FAILED_TOTAL") as mock_failed,
        ):
            config = AnchoringConfig(audit_log_path="/tmp/test.log")
            anchoring = AuditMerkleAnchoring(config)

            # Mock backend to fail
            mock_backend = AsyncMock()
            mock_backend.verify_root.return_value = False
            anchoring.backends["transparency_log"] = mock_backend

            verified = await anchoring.verify_root("test_hash")

            assert verified is False
            mock_total.inc.assert_called_once()
            mock_failed.inc.assert_called_once()
