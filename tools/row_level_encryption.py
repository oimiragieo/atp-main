#!/usr/bin/env python3
"""GAP-303: Row-level encryption & key scoping.

Implements per-row data encryption keys (DEK) with KMS envelope encryption.
Each row gets its own unique DEK, wrapped by a master key from KMS.
Supports authorization-based access control for encrypted data.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from tools.kms_poc import KMS
from tools.row_encryption_metrics import get_row_encryption_metrics_collector

# Setup logger
logger = logging.getLogger(__name__)


@dataclass
class EncryptedRow:
    """Represents an encrypted row with its wrapped DEK and encrypted data."""

    row_id: str
    wrapped_dek: str  # Hex-encoded wrapped data encryption key
    encrypted_data: str  # JSON-encoded encrypted blob
    key_version: str  # Version of the master key used
    created_at: float
    tenant_id: str  # For multi-tenant key scoping


class RowLevelEncryption:
    """Manages row-level encryption with per-row DEKs and KMS envelope encryption."""

    def __init__(self, kms: KMS, key_version: str = "v1"):
        self.kms = kms
        self.key_version = key_version

    def encrypt_row(self, row_id: str, data: dict[str, Any], tenant_id: str, aad: bytes = b"") -> EncryptedRow:
        """Encrypt a row with a unique DEK wrapped by KMS.

        Args:
            row_id: Unique identifier for the row
            data: The data to encrypt
            tenant_id: Tenant identifier for key scoping
            aad: Additional authenticated data

        Returns:
            EncryptedRow with wrapped DEK and encrypted data
        """
        start_time = time.time()
        metrics_collector = get_row_encryption_metrics_collector()

        try:
            # Generate unique DEK for this row
            dek, wrapped_dek = self.kms.generate_data_key()

            # Encrypt the data with the DEK
            plaintext = json.dumps(data, sort_keys=True).encode("utf-8")
            encrypted_blob = self.kms.encrypt(wrapped_dek, plaintext, aad)

            encrypted_row = EncryptedRow(
                row_id=row_id,
                wrapped_dek=wrapped_dek.hex(),
                encrypted_data=json.dumps(encrypted_blob),
                key_version=self.key_version,
                created_at=time.time(),
                tenant_id=tenant_id,
            )

            # Record successful encryption
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("encrypt_row", duration_ms, True, tenant_id, 1)

            return encrypted_row

        except Exception as e:
            # Record failed encryption
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("encrypt_row", duration_ms, False, tenant_id, 1, type(e).__name__)

            raise

    def decrypt_row(self, encrypted_row: EncryptedRow, tenant_id: str, aad: bytes = b"") -> dict[str, Any]:
        """Decrypt a row if authorized.

        Args:
            encrypted_row: The encrypted row to decrypt
            tenant_id: Tenant identifier for authorization
            aad: Additional authenticated data

        Returns:
            Decrypted data dictionary

        Raises:
            ValueError: If tenant is not authorized or decryption fails
        """
        start_time = time.time()
        metrics_collector = get_row_encryption_metrics_collector()

        try:
            # Check tenant authorization
            if encrypted_row.tenant_id != tenant_id:
                raise ValueError(
                    f"Access denied: tenant {tenant_id} cannot access data for tenant {encrypted_row.tenant_id}"
                )

            # Unwrap the DEK
            wrapped_dek = bytes.fromhex(encrypted_row.wrapped_dek)
            self.kms.unwrap_data_key(wrapped_dek)  # Validate DEK can be unwrapped

            # Decrypt the data
            encrypted_blob = json.loads(encrypted_row.encrypted_data)
            decrypted_bytes = self.kms.decrypt(wrapped_dek, encrypted_blob, aad)

            # Parse JSON
            result = json.loads(decrypted_bytes.decode("utf-8"))

            # Record successful decryption
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("decrypt_row", duration_ms, True, tenant_id, 1)

            return result

        except Exception as e:
            # Record failed decryption
            duration_ms = (time.time() - start_time) * 1000
            error_type = "authorization" if "Access denied" in str(e) else type(e).__name__
            metrics_collector.record_operation("decrypt_row", duration_ms, False, tenant_id, 1, error_type)

            raise

    def re_encrypt_row(
        self, encrypted_row: EncryptedRow, new_key_version: str, tenant_id: str, aad: bytes = b""
    ) -> EncryptedRow:
        """Re-encrypt a row with a new key version (for key rotation).

        Args:
            encrypted_row: The row to re-encrypt
            new_key_version: New key version to use
            tenant_id: Tenant for authorization
            aad: Additional authenticated data

        Returns:
            Re-encrypted row with new key version
        """
        # First decrypt with old key
        data = self.decrypt_row(encrypted_row, tenant_id, aad)

        # Create new encryption instance with new key version
        new_encryption = RowLevelEncryption(self.kms, new_key_version)

        # Re-encrypt with new key
        return new_encryption.encrypt_row(encrypted_row.row_id, data, tenant_id, aad)


class RowEncryptionStore:
    """Storage layer for encrypted rows with access control."""

    def __init__(self, encryption: RowLevelEncryption):
        self.encryption = encryption
        self.rows: dict[str, EncryptedRow] = {}

    def store_row(self, row_id: str, data: dict[str, Any], tenant_id: str, aad: bytes = b"") -> None:
        """Store an encrypted row."""
        start_time = time.time()
        metrics_collector = get_row_encryption_metrics_collector()

        try:
            encrypted_row = self.encryption.encrypt_row(row_id, data, tenant_id, aad)
            self.rows[row_id] = encrypted_row

            # Record successful store
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("store_row", duration_ms, True, tenant_id, 1)

        except Exception as e:
            # Record failed store
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("store_row", duration_ms, False, tenant_id, 1, type(e).__name__)

            raise

    def get_row(self, row_id: str, tenant_id: str, aad: bytes = b"") -> dict[str, Any] | None:
        """Retrieve and decrypt a row if authorized."""
        start_time = time.time()
        metrics_collector = get_row_encryption_metrics_collector()

        try:
            encrypted_row = self.rows.get(row_id)
            if not encrypted_row:
                # Record not found (successful operation)
                duration_ms = (time.time() - start_time) * 1000
                metrics_collector.record_operation("get_row", duration_ms, True, tenant_id, 1, "not_found")
                return None

            result = self.encryption.decrypt_row(encrypted_row, tenant_id, aad)

            # Record successful get
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("get_row", duration_ms, True, tenant_id, 1)

            return result

        except ValueError:
            # Record authorization failure
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("get_row", duration_ms, False, tenant_id, 1, "authorization")
            return None  # Return None for unauthorized access

        except Exception as e:
            # Record failed get
            duration_ms = (time.time() - start_time) * 1000
            error_type = type(e).__name__
            metrics_collector.record_operation("get_row", duration_ms, False, tenant_id, 1, error_type)

            raise

    def list_rows_for_tenant(self, tenant_id: str) -> list[str]:
        """List all row IDs accessible by a tenant."""
        return [row_id for row_id, row in self.rows.items() if row.tenant_id == tenant_id]

    def delete_row(self, row_id: str, tenant_id: str) -> bool:
        """Delete a row if authorized."""
        encrypted_row = self.rows.get(row_id)
        if not encrypted_row:
            return False

        if encrypted_row.tenant_id != tenant_id:
            raise ValueError(
                f"Access denied: tenant {tenant_id} cannot delete data for tenant {encrypted_row.tenant_id}"
            )

        del self.rows[row_id]
        return True

    def rotate_keys(self, old_key_version: str, new_key_version: str, tenant_id: str, aad: bytes = b"") -> int:
        """Rotate encryption keys for all rows of a tenant.

        Returns:
            Number of rows re-encrypted
        """
        start_time = time.time()
        metrics_collector = get_row_encryption_metrics_collector()
        rotated_count = 0

        try:
            for row_id, encrypted_row in list(self.rows.items()):
                if encrypted_row.tenant_id == tenant_id and encrypted_row.key_version == old_key_version:
                    try:
                        new_row = self.encryption.re_encrypt_row(encrypted_row, new_key_version, tenant_id, aad)
                        self.rows[row_id] = new_row
                        rotated_count += 1
                    except Exception as e:
                        # Log error but continue with other rows
                        logger.warning(f"Failed to rotate key for row {row_id}: {e}")
                        continue

            # Record successful rotation
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation("rotate_keys", duration_ms, True, tenant_id, rotated_count)

            return rotated_count

        except Exception as e:
            # Record failed rotation
            duration_ms = (time.time() - start_time) * 1000
            metrics_collector.record_operation(
                "rotate_keys", duration_ms, False, tenant_id, rotated_count, type(e).__name__
            )

            raise
