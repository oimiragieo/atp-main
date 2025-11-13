#!/usr/bin/env python3
"""GAP-370: Evidence Pack Signature & Notarization

Provides cryptographic signing and notarization services for evidence packs.
Ensures tamper-evident integrity and provides audit trails for compliance.
"""

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import MGF1, PSS
from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# GAP-370: Evidence pack signature metrics
EVIDENCE_PACK_SIGNATURES_TOTAL = REGISTRY.counter("evidence_pack_signatures_total")
EVIDENCE_PACK_NOTARIZATIONS_TOTAL = REGISTRY.counter("evidence_pack_notarizations_total")
EVIDENCE_PACK_SIGNATURE_VERIFICATIONS_TOTAL = REGISTRY.counter("evidence_pack_signature_verifications_total")
EVIDENCE_PACK_TAMPER_DETECTED_TOTAL = REGISTRY.counter("evidence_pack_tamper_detected_total")


@dataclass
class SignatureInfo:
    """Information about a digital signature."""

    algorithm: str
    key_id: str
    signature: str
    timestamp: datetime
    signer_info: dict[str, Any]
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert signature info to dictionary."""
        result = {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signature": self.signature,
            "timestamp": self.timestamp.isoformat(),
            "signer_info": self.signer_info,
        }

        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignatureInfo":
        """Create signature info from dictionary."""
        return cls(
            algorithm=data["algorithm"],
            key_id=data["key_id"],
            signature=data["signature"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signer_info=data["signer_info"],
            metadata=data.get("metadata"),
        )


@dataclass
class NotarizationRecord:
    """Notarization record for an evidence pack."""

    pack_id: str
    notary_id: str
    timestamp: datetime
    evidence_hash: str
    signature_info: SignatureInfo
    certificate_chain: list[str]
    notary_statement: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert notarization record to dictionary."""
        return {
            "pack_id": self.pack_id,
            "notary_id": self.notary_id,
            "timestamp": self.timestamp.isoformat(),
            "evidence_hash": self.evidence_hash,
            "signature_info": self.signature_info.to_dict(),
            "certificate_chain": self.certificate_chain,
            "notary_statement": self.notary_statement,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotarizationRecord":
        """Create notarization record from dictionary."""
        return cls(
            pack_id=data["pack_id"],
            notary_id=data["notary_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            evidence_hash=data["evidence_hash"],
            signature_info=SignatureInfo.from_dict(data["signature_info"]),
            certificate_chain=data["certificate_chain"],
            notary_statement=data["notary_statement"],
            metadata=data.get("metadata"),
        )


class EvidencePackSigner:
    """Handles digital signing of evidence packs."""

    def __init__(self, private_key_path: str | None = None, key_id: str = "default"):
        self.key_id = key_id
        self.private_key = None
        self.public_key = None

        if private_key_path:
            self._load_private_key(private_key_path)
        else:
            self._generate_keypair()

    def _generate_keypair(self):
        """Generate a new RSA keypair for signing."""
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        self.public_key = self.private_key.public_key()
        logger.info(f"Generated new RSA keypair with key_id: {self.key_id}")

    def _load_private_key(self, key_path: str):
        """Load private key from file."""
        with open(key_path, "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        self.public_key = self.private_key.public_key()
        logger.info(f"Loaded private key from {key_path}")

    def sign_evidence_pack(self, pack_path: str, signer_info: dict[str, Any] | None = None) -> SignatureInfo:
        """Sign an evidence pack and return signature information.

        Args:
            pack_path: Path to the evidence pack zip file
            signer_info: Information about the signer

        Returns:
            Signature information
        """
        if not self.private_key:
            raise ValueError("No private key available for signing")

        # Calculate hash of the evidence pack
        pack_hash = self._calculate_pack_hash(pack_path)

        # Create signature
        signature_bytes = self.private_key.sign(
            pack_hash.encode("utf-8"),
            PSS(mgf=MGF1(algorithm=hashes.SHA256()), salt_length=PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

        # Encode signature as base64
        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

        signature_info = SignatureInfo(
            algorithm="RSASSA-PSS-SHA256",
            key_id=self.key_id,
            signature=signature_b64,
            timestamp=datetime.now(),
            signer_info=signer_info or {"signer": "ATP Router Service"},
            metadata={"pack_hash": pack_hash},
        )

        EVIDENCE_PACK_SIGNATURES_TOTAL.inc()
        logger.info(f"Signed evidence pack {Path(pack_path).name} with key {self.key_id}")

        return signature_info

    def _calculate_pack_hash(self, pack_path: str) -> str:
        """Calculate SHA-256 hash of the evidence pack contents."""
        import zipfile

        hasher = hashlib.sha256()

        with zipfile.ZipFile(pack_path, "r") as zf:
            # Sort files for deterministic hashing
            for file_info in sorted(zf.filelist, key=lambda x: x.filename):
                # Hash filename
                hasher.update(file_info.filename.encode("utf-8"))

                # Hash file contents
                with zf.open(file_info) as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)

        return hasher.hexdigest()

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format."""
        if not self.public_key:
            raise ValueError("No public key available")

        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")

    def verify_signature(self, pack_path: str, signature_info: SignatureInfo) -> bool:
        """Verify a signature against an evidence pack.

        Args:
            pack_path: Path to the evidence pack
            signature_info: Signature information to verify

        Returns:
            True if signature is valid
        """
        if not self.public_key:
            raise ValueError("No public key available for verification")

        try:
            # Recalculate pack hash
            pack_hash = self._calculate_pack_hash(pack_path)

            # Decode signature
            signature_bytes = base64.b64decode(signature_info.signature)

            # Verify signature
            self.public_key.verify(
                signature_bytes,
                pack_hash.encode("utf-8"),
                PSS(mgf=MGF1(algorithm=hashes.SHA256()), salt_length=PSS.DIGEST_LENGTH),
                hashes.SHA256(),
            )

            EVIDENCE_PACK_SIGNATURE_VERIFICATIONS_TOTAL.inc()
            logger.info(f"Signature verification successful for pack {Path(pack_path).name}")
            return True

        except Exception as e:
            EVIDENCE_PACK_TAMPER_DETECTED_TOTAL.inc()
            logger.error(f"Signature verification failed for pack {Path(pack_path).name}: {e}")
            return False


class EvidencePackNotary:
    """Handles notarization of evidence packs."""

    def __init__(self, notary_id: str = "atp-notary", signer: EvidencePackSigner | None = None):
        self.notary_id = notary_id
        self.signer = signer or EvidencePackSigner(key_id=f"{notary_id}-signer")

    def notarize_pack(
        self,
        pack_path: str,
        pack_id: str,
        certificate_chain: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotarizationRecord:
        """Notarize an evidence pack.

        Args:
            pack_path: Path to the evidence pack
            pack_id: Unique identifier for the pack
            certificate_chain: Optional certificate chain for the notary
            metadata: Additional metadata for notarization

        Returns:
            Notarization record
        """
        # Calculate evidence hash
        evidence_hash = self.signer._calculate_pack_hash(pack_path)

        # Sign the pack
        signature_info = self.signer.sign_evidence_pack(
            pack_path,
            signer_info={
                "notary_id": self.notary_id,
                "role": "evidence_pack_notary",
                "organization": "ATP Router Service",
            },
        )

        # Create certificate chain if not provided
        if certificate_chain is None:
            certificate_chain = [self.signer.get_public_key_pem()]

        # Create notary statement
        notary_statement = (
            f"This evidence pack ({pack_id}) has been notarized by {self.notary_id} "
            f"on {datetime.now().isoformat()}. The pack contains compliance evidence "
            f"and has been cryptographically signed to ensure integrity."
        )

        notarization_record = NotarizationRecord(
            pack_id=pack_id,
            notary_id=self.notary_id,
            timestamp=datetime.now(),
            evidence_hash=evidence_hash,
            signature_info=signature_info,
            certificate_chain=certificate_chain,
            notary_statement=notary_statement,
            metadata=metadata,
        )

        EVIDENCE_PACK_NOTARIZATIONS_TOTAL.inc()
        logger.info(f"Notarized evidence pack {pack_id} with notary {self.notary_id}")

        return notarization_record

    def save_notarization_record(self, record: NotarizationRecord, output_path: str) -> str:
        """Save notarization record to a file.

        Args:
            record: Notarization record to save
            output_path: Path to save the record

        Returns:
            Path to the saved record
        """
        record_data = record.to_dict()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(record_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved notarization record to {output_path}")
        return output_path

    def load_notarization_record(self, record_path: str) -> NotarizationRecord:
        """Load notarization record from a file.

        Args:
            record_path: Path to the notarization record file

        Returns:
            Notarization record
        """
        with open(record_path, encoding="utf-8") as f:
            record_data = json.load(f)

        return NotarizationRecord.from_dict(record_data)

    def verify_notarization(self, pack_path: str, record: NotarizationRecord) -> dict[str, Any]:
        """Verify a notarization record against an evidence pack.

        Args:
            pack_path: Path to the evidence pack
            record: Notarization record to verify

        Returns:
            Verification result dictionary
        """
        result = {"valid": False, "signature_valid": False, "hash_valid": False, "notary_valid": False, "errors": []}

        try:
            # Verify notary identity
            if record.notary_id != self.notary_id:
                result["errors"].append(f"Notary ID mismatch: expected {self.notary_id}, got {record.notary_id}")
            else:
                result["notary_valid"] = True

            # Verify evidence hash
            current_hash = self.signer._calculate_pack_hash(pack_path)
            if current_hash != record.evidence_hash:
                result["errors"].append("Evidence hash mismatch - pack may have been tampered with")
                EVIDENCE_PACK_TAMPER_DETECTED_TOTAL.inc()
            else:
                result["hash_valid"] = True

            # Verify signature
            if self.signer.verify_signature(pack_path, record.signature_info):
                result["signature_valid"] = True
            else:
                result["errors"].append("Signature verification failed")

            # Overall validity
            result["valid"] = all([result["notary_valid"], result["hash_valid"], result["signature_valid"]])

            if result["valid"]:
                logger.info(f"Notarization verification successful for pack {record.pack_id}")
            else:
                logger.error(f"Notarization verification failed for pack {record.pack_id}: {result['errors']}")

        except Exception as e:
            result["errors"].append(f"Verification error: {str(e)}")
            logger.error(f"Notarization verification error for pack {record.pack_id}: {e}")

        return result


class EvidencePackSignatureManager:
    """Manages signatures and notarization for evidence packs."""

    def __init__(self, notary_id: str = "atp-notary"):
        self.notary = EvidencePackNotary(notary_id)
        self.signatures: dict[str, SignatureInfo] = {}
        self.notarizations: dict[str, NotarizationRecord] = {}

    def sign_and_notarize_pack(
        self, pack_path: str, pack_id: str, output_dir: str = "./evidence_packs"
    ) -> dict[str, Any]:
        """Sign and notarize an evidence pack.

        Args:
            pack_path: Path to the evidence pack
            pack_id: Unique identifier for the pack
            output_dir: Directory to save notarization records

        Returns:
            Dictionary with signature and notarization information
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Notarize the pack
        notarization_record = self.notary.notarize_pack(pack_path, pack_id)

        # Save notarization record
        record_path = output_path / f"{pack_id}_notarization.json"
        self.notary.save_notarization_record(notarization_record, str(record_path))

        # Store in memory
        self.signatures[pack_id] = notarization_record.signature_info
        self.notarizations[pack_id] = notarization_record

        result = {
            "pack_id": pack_id,
            "pack_path": pack_path,
            "signature_info": notarization_record.signature_info.to_dict(),
            "notarization_record": notarization_record.to_dict(),
            "record_path": str(record_path),
            "evidence_hash": notarization_record.evidence_hash,
        }

        logger.info(f"Successfully signed and notarized evidence pack {pack_id}")
        return result

    def verify_pack_integrity(self, pack_path: str, pack_id: str) -> dict[str, Any]:
        """Verify the integrity of a signed and notarized evidence pack.

        Args:
            pack_path: Path to the evidence pack
            pack_id: Pack identifier

        Returns:
            Verification result
        """
        if pack_id not in self.notarizations:
            return {"valid": False, "error": f"No notarization record found for pack {pack_id}"}

        record = self.notarizations[pack_id]
        return self.notary.verify_notarization(pack_path, record)

    def get_pack_signature_info(self, pack_id: str) -> SignatureInfo | None:
        """Get signature information for a pack.

        Args:
            pack_id: Pack identifier

        Returns:
            Signature information or None if not found
        """
        return self.signatures.get(pack_id)

    def get_pack_notarization(self, pack_id: str) -> NotarizationRecord | None:
        """Get notarization record for a pack.

        Args:
            pack_id: Pack identifier

        Returns:
            Notarization record or None if not found
        """
        return self.notarizations.get(pack_id)

    def list_signed_packs(self) -> list[str]:
        """List all signed pack IDs.

        Returns:
            List of pack IDs
        """
        return list(self.signatures.keys())


# Global signature manager instance
_signature_manager: EvidencePackSignatureManager | None = None


def get_evidence_pack_signature_manager() -> EvidencePackSignatureManager | None:
    """Get the global evidence pack signature manager instance."""
    return _signature_manager


def initialize_evidence_pack_signature_manager(notary_id: str = "atp-notary") -> EvidencePackSignatureManager:
    """Initialize the global evidence pack signature manager."""
    global _signature_manager
    _signature_manager = EvidencePackSignatureManager(notary_id)
    return _signature_manager
