"""Tests for GAP-370: Evidence Pack Signature & Notarization."""

import base64
import os
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from router_service.evidence_pack_signer import (
    EvidencePackNotary,
    EvidencePackSignatureManager,
    EvidencePackSigner,
    NotarizationRecord,
    SignatureInfo,
    get_evidence_pack_signature_manager,
    initialize_evidence_pack_signature_manager,
)


class TestSignatureInfo(unittest.TestCase):
    """Test cases for SignatureInfo."""

    def test_signature_info_creation(self):
        """Test signature info creation."""
        timestamp = datetime.now()
        signer_info = {"name": "Test Signer", "role": "admin"}

        sig_info = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id="test-key-001",
            signature="base64signature",
            timestamp=timestamp,
            signer_info=signer_info,
        )

        self.assertEqual(sig_info.algorithm, "RSASSA-PSS-SHA256")
        self.assertEqual(sig_info.key_id, "test-key-001")
        self.assertEqual(sig_info.signature, "base64signature")
        self.assertEqual(sig_info.signer_info, signer_info)

    def test_signature_info_serialization(self):
        """Test signature info serialization."""
        original = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id="test-key-001",
            signature="base64signature",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            signer_info={"name": "Test Signer"},
            metadata={"version": "1.0"},
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = SignatureInfo.from_dict(data)

        # Verify
        self.assertEqual(original.algorithm, restored.algorithm)
        self.assertEqual(original.key_id, restored.key_id)
        self.assertEqual(original.signature, restored.signature)
        self.assertEqual(original.signer_info, restored.signer_info)
        self.assertEqual(original.metadata, restored.metadata)


class TestNotarizationRecord(unittest.TestCase):
    """Test cases for NotarizationRecord."""

    def test_notarization_record_creation(self):
        """Test notarization record creation."""
        timestamp = datetime.now()
        signature_info = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id="test-key",
            signature="signature",
            timestamp=timestamp,
            signer_info={"name": "Notary"},
        )

        record = NotarizationRecord(
            pack_id="test-pack-001",
            notary_id="test-notary",
            timestamp=timestamp,
            evidence_hash="abc123",
            signature_info=signature_info,
            certificate_chain=["cert1", "cert2"],
            notary_statement="Test statement",
        )

        self.assertEqual(record.pack_id, "test-pack-001")
        self.assertEqual(record.notary_id, "test-notary")
        self.assertEqual(record.evidence_hash, "abc123")
        self.assertEqual(record.notary_statement, "Test statement")

    def test_notarization_record_serialization(self):
        """Test notarization record serialization."""
        signature_info = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id="test-key",
            signature="signature",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            signer_info={"name": "Notary"},
        )

        original = NotarizationRecord(
            pack_id="test-pack-001",
            notary_id="test-notary",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            evidence_hash="abc123",
            signature_info=signature_info,
            certificate_chain=["cert1"],
            notary_statement="Test statement",
            metadata={"version": "1.0"},
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = NotarizationRecord.from_dict(data)

        # Verify
        self.assertEqual(original.pack_id, restored.pack_id)
        self.assertEqual(original.notary_id, restored.notary_id)
        self.assertEqual(original.evidence_hash, restored.evidence_hash)
        self.assertEqual(original.notary_statement, restored.notary_statement)


class TestEvidencePackSigner(unittest.TestCase):
    """Test cases for EvidencePackSigner."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.signer = EvidencePackSigner(key_id="test-signer")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_signer_initialization(self):
        """Test signer initialization."""
        self.assertIsNotNone(self.signer.private_key)
        self.assertIsNotNone(self.signer.public_key)
        self.assertEqual(self.signer.key_id, "test-signer")

    def test_sign_evidence_pack(self):
        """Test signing an evidence pack."""
        # Create a test zip file
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        # Sign the pack
        signature_info = self.signer.sign_evidence_pack(str(pack_path))

        # Verify signature info
        self.assertEqual(signature_info.algorithm, "RSASSA-PSS-SHA256")
        self.assertEqual(signature_info.key_id, "test-signer")
        self.assertIsInstance(signature_info.signature, str)
        self.assertIsInstance(signature_info.timestamp, datetime)

        # Verify signature is base64
        try:
            base64.b64decode(signature_info.signature)
        except Exception:
            self.fail("Signature is not valid base64")

    def test_verify_signature_valid(self):
        """Test verifying a valid signature."""
        # Create and sign a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        signature_info = self.signer.sign_evidence_pack(str(pack_path))

        # Verify the signature
        is_valid = self.signer.verify_signature(str(pack_path), signature_info)

        self.assertTrue(is_valid)

    def test_verify_signature_invalid(self):
        """Test verifying an invalid signature."""
        # Create a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        # Create fake signature info
        fake_signature = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id="test-signer",
            signature=base64.b64encode(b"fake_signature").decode(),
            timestamp=datetime.now(),
            signer_info={"name": "Fake"},
        )

        # Verify should fail
        is_valid = self.signer.verify_signature(str(pack_path), fake_signature)

        self.assertFalse(is_valid)

    def test_pack_hash_determinism(self):
        """Test that pack hash is deterministic."""
        # Create identical packs
        pack1_path = self.temp_dir / "pack1.zip"
        pack2_path = self.temp_dir / "pack2.zip"

        for pack_path in [pack1_path, pack2_path]:
            with zipfile.ZipFile(pack_path, "w") as zf:
                zf.writestr("test.txt", "test content")
                zf.writestr("data.json", '{"key": "value"}')

        # Hash both packs
        hash1 = self.signer._calculate_pack_hash(str(pack1_path))
        hash2 = self.signer._calculate_pack_hash(str(pack2_path))

        self.assertEqual(hash1, hash2)

    def test_pack_hash_changes_with_content(self):
        """Test that pack hash changes when content changes."""
        # Create different packs
        pack1_path = self.temp_dir / "pack1.zip"
        pack2_path = self.temp_dir / "pack2.zip"

        with zipfile.ZipFile(pack1_path, "w") as zf:
            zf.writestr("test.txt", "content 1")

        with zipfile.ZipFile(pack2_path, "w") as zf:
            zf.writestr("test.txt", "content 2")

        # Hash both packs
        hash1 = self.signer._calculate_pack_hash(str(pack1_path))
        hash2 = self.signer._calculate_pack_hash(str(pack2_path))

        self.assertNotEqual(hash1, hash2)

    def test_get_public_key_pem(self):
        """Test getting public key in PEM format."""
        pem_key = self.signer.get_public_key_pem()

        self.assertIsInstance(pem_key, str)
        self.assertIn("BEGIN PUBLIC KEY", pem_key)
        self.assertIn("END PUBLIC KEY", pem_key)


class TestEvidencePackNotary(unittest.TestCase):
    """Test cases for EvidencePackNotary."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.notary = EvidencePackNotary(notary_id="test-notary")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_notary_initialization(self):
        """Test notary initialization."""
        self.assertEqual(self.notary.notary_id, "test-notary")
        self.assertIsNotNone(self.notary.signer)

    def test_notarize_pack(self):
        """Test notarizing an evidence pack."""
        # Create a test pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        # Notarize
        record = self.notary.notarize_pack(str(pack_path), "test-pack-001")

        # Verify record
        self.assertEqual(record.pack_id, "test-pack-001")
        self.assertEqual(record.notary_id, "test-notary")
        self.assertIsInstance(record.timestamp, datetime)
        self.assertIsInstance(record.evidence_hash, str)
        self.assertEqual(len(record.evidence_hash), 64)  # SHA-256 hex
        self.assertIsInstance(record.signature_info, SignatureInfo)
        self.assertIsInstance(record.notary_statement, str)

    def test_save_and_load_notarization_record(self):
        """Test saving and loading notarization records."""
        # Create and notarize a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        original_record = self.notary.notarize_pack(str(pack_path), "test-pack-001")

        # Save record
        record_path = self.temp_dir / "notarization.json"
        saved_path = self.notary.save_notarization_record(original_record, str(record_path))

        self.assertEqual(saved_path, str(record_path))
        self.assertTrue(os.path.exists(record_path))

        # Load record
        loaded_record = self.notary.load_notarization_record(str(record_path))

        # Verify
        self.assertEqual(original_record.pack_id, loaded_record.pack_id)
        self.assertEqual(original_record.notary_id, loaded_record.notary_id)
        self.assertEqual(original_record.evidence_hash, loaded_record.evidence_hash)

    def test_verify_notarization_valid(self):
        """Test verifying a valid notarization."""
        # Create and notarize a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        record = self.notary.notarize_pack(str(pack_path), "test-pack-001")

        # Verify notarization
        result = self.notary.verify_notarization(str(pack_path), record)

        self.assertTrue(result["valid"])
        self.assertTrue(result["signature_valid"])
        self.assertTrue(result["hash_valid"])
        self.assertTrue(result["notary_valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_verify_notarization_tampered(self):
        """Test verifying a tampered pack."""
        # Create and notarize a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "original content")

        record = self.notary.notarize_pack(str(pack_path), "test-pack-001")

        # Tamper with the pack
        with zipfile.ZipFile(pack_path, "a") as zf:
            zf.writestr("test.txt", "tampered content")

        # Verify should fail
        result = self.notary.verify_notarization(str(pack_path), record)

        self.assertFalse(result["valid"])
        self.assertFalse(result["hash_valid"])
        self.assertIn("Evidence hash mismatch", str(result["errors"]))


class TestEvidencePackSignatureManager(unittest.TestCase):
    """Test cases for EvidencePackSignatureManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = EvidencePackSignatureManager(notary_id="test-manager")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_manager_initialization(self):
        """Test manager initialization."""
        self.assertEqual(self.manager.notary.notary_id, "test-manager")
        self.assertEqual(len(self.manager.signatures), 0)
        self.assertEqual(len(self.manager.notarizations), 0)

    def test_sign_and_notarize_pack(self):
        """Test signing and notarizing a pack."""
        # Create a test pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        # Sign and notarize
        result = self.manager.sign_and_notarize_pack(str(pack_path), "test-pack-001", str(self.temp_dir))

        # Verify result
        self.assertEqual(result["pack_id"], "test-pack-001")
        self.assertIn("signature_info", result)
        self.assertIn("notarization_record", result)
        self.assertIn("record_path", result)
        self.assertIn("evidence_hash", result)

        # Verify record file was created
        record_path = Path(result["record_path"])
        self.assertTrue(record_path.exists())

        # Verify stored in manager
        self.assertIn("test-pack-001", self.manager.signatures)
        self.assertIn("test-pack-001", self.manager.notarizations)

    def test_verify_pack_integrity_valid(self):
        """Test verifying integrity of a valid pack."""
        # Create and sign a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        self.manager.sign_and_notarize_pack(str(pack_path), "test-pack-001", str(self.temp_dir))

        # Verify integrity
        result = self.manager.verify_pack_integrity(str(pack_path), "test-pack-001")

        self.assertTrue(result["valid"])
        self.assertTrue(result["signature_valid"])
        self.assertTrue(result["hash_valid"])

    def test_verify_pack_integrity_unknown_pack(self):
        """Test verifying integrity of unknown pack."""
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        result = self.manager.verify_pack_integrity(str(pack_path), "unknown-pack")

        self.assertFalse(result["valid"])
        self.assertIn("No notarization record found", result["error"])

    def test_get_pack_signature_info(self):
        """Test getting signature info for a pack."""
        # Create and sign a pack
        pack_path = self.temp_dir / "test_pack.zip"
        with zipfile.ZipFile(pack_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        self.manager.sign_and_notarize_pack(str(pack_path), "test-pack-001", str(self.temp_dir))

        # Get signature info
        sig_info = self.manager.get_pack_signature_info("test-pack-001")

        self.assertIsNotNone(sig_info)
        self.assertEqual(sig_info.key_id, "test-manager-signer")

    def test_list_signed_packs(self):
        """Test listing signed packs."""
        # Create multiple packs
        for i in range(3):
            pack_path = self.temp_dir / f"pack_{i}.zip"
            with zipfile.ZipFile(pack_path, "w") as zf:
                zf.writestr("test.txt", f"content {i}")

            self.manager.sign_and_notarize_pack(str(pack_path), f"pack-{i}", str(self.temp_dir))

        # List packs
        packs = self.manager.list_signed_packs()

        self.assertEqual(len(packs), 3)
        self.assertIn("pack-0", packs)
        self.assertIn("pack-1", packs)
        self.assertIn("pack-2", packs)


class TestGlobalFunctions(unittest.TestCase):
    """Test global signature manager functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_global_manager_initialization(self):
        """Test global manager initialization."""
        manager = initialize_evidence_pack_signature_manager(notary_id="global-test")

        self.assertIsNotNone(manager)
        self.assertEqual(manager.notary.notary_id, "global-test")

        # Test getter
        global_manager = get_evidence_pack_signature_manager()
        self.assertEqual(global_manager, manager)


if __name__ == "__main__":
    unittest.main()
