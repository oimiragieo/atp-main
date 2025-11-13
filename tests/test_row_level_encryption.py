#!/usr/bin/env python3
"""Comprehensive tests for GAP-303: Row-level encryption & key scoping."""

import time

import pytest

from tools.kms_poc import KMS
from tools.row_level_encryption import RowEncryptionStore, RowLevelEncryption


class TestRowLevelEncryption:
    """Test row-level encryption functionality."""

    @pytest.fixture
    def kms(self):
        """Create a KMS instance for testing."""
        master_key = b"test_master_key_32_bytes_long!!"
        return KMS(master_key)

    @pytest.fixture
    def encryption(self, kms):
        """Create a RowLevelEncryption instance."""
        return RowLevelEncryption(kms, "v1")

    @pytest.fixture
    def store(self, encryption):
        """Create a RowEncryptionStore instance."""
        return RowEncryptionStore(encryption)

    def test_encrypt_decrypt_roundtrip(self, encryption):
        """Test basic encrypt/decrypt roundtrip."""
        row_id = "test_row_1"
        data = {"name": "John Doe", "age": 30, "email": "john@example.com"}
        tenant_id = "tenant_123"
        aad = b"test_aad"

        # Encrypt
        encrypted_row = encryption.encrypt_row(row_id, data, tenant_id, aad)

        # Verify encrypted row structure
        assert encrypted_row.row_id == row_id
        assert encrypted_row.tenant_id == tenant_id
        assert encrypted_row.key_version == "v1"
        assert encrypted_row.wrapped_dek
        assert encrypted_row.encrypted_data
        assert encrypted_row.created_at > 0

        # Decrypt
        decrypted_data = encryption.decrypt_row(encrypted_row, tenant_id, aad)

        # Verify data integrity
        assert decrypted_data == data

    def test_tenant_authorization(self, encryption):
        """Test that tenants can only access their own data."""
        data = {"secret": "classified"}
        tenant_a = "tenant_a"
        tenant_b = "tenant_b"

        # Tenant A encrypts data
        encrypted_row = encryption.encrypt_row("row1", data, tenant_a)

        # Tenant A can decrypt
        decrypted = encryption.decrypt_row(encrypted_row, tenant_a)
        assert decrypted == data

        # Tenant B cannot decrypt
        with pytest.raises(ValueError, match="Access denied"):
            encryption.decrypt_row(encrypted_row, tenant_b)

    def test_unique_deks_per_row(self, encryption):
        """Test that each row gets a unique DEK."""
        data1 = {"value": 1}
        data2 = {"value": 2}
        tenant_id = "tenant_123"

        row1 = encryption.encrypt_row("row1", data1, tenant_id)
        row2 = encryption.encrypt_row("row2", data2, tenant_id)

        # DEKs should be different
        assert row1.wrapped_dek != row2.wrapped_dek

        # But both should decrypt correctly
        assert encryption.decrypt_row(row1, tenant_id) == data1
        assert encryption.decrypt_row(row2, tenant_id) == data2

    def test_key_rotation(self, kms, encryption):
        """Test key rotation functionality."""
        data = {"sensitive": "data"}
        tenant_id = "tenant_123"
        old_version = "v1"
        new_version = "v2"

        # Encrypt with old key
        old_encryption = RowLevelEncryption(kms, old_version)
        encrypted_row = old_encryption.encrypt_row("row1", data, tenant_id)

        # Re-encrypt with new key
        new_row = old_encryption.re_encrypt_row(encrypted_row, new_version, tenant_id)

        # Verify new row has new key version
        assert new_row.key_version == new_version
        assert new_row.wrapped_dek != encrypted_row.wrapped_dek

        # Can still decrypt with new encryption instance
        new_encryption = RowLevelEncryption(kms, new_version)
        decrypted = new_encryption.decrypt_row(new_row, tenant_id)
        assert decrypted == data

    def test_aad_integrity(self, encryption):
        """Test additional authenticated data (AAD) integrity."""
        data = {"message": "hello"}
        tenant_id = "tenant_123"
        correct_aad = b"correct_aad"
        wrong_aad = b"wrong_aad"

        # Encrypt with AAD
        encrypted_row = encryption.encrypt_row("row1", data, tenant_id, correct_aad)

        # Decrypt with correct AAD should work
        decrypted = encryption.decrypt_row(encrypted_row, tenant_id, correct_aad)
        assert decrypted == data

        # Decrypt with wrong AAD should fail
        with pytest.raises(ValueError):
            encryption.decrypt_row(encrypted_row, tenant_id, wrong_aad)


class TestRowEncryptionStore:
    """Test the storage layer for encrypted rows."""

    @pytest.fixture
    def kms(self):
        """Create a KMS instance for testing."""
        return KMS(b"test_master_key_32_bytes_long!!")

    @pytest.fixture
    def store(self, kms):
        """Create a RowEncryptionStore instance."""
        encryption = RowLevelEncryption(kms, "v1")
        return RowEncryptionStore(encryption)

    def test_store_and_retrieve(self, store):
        """Test storing and retrieving encrypted rows."""
        row_id = "user_123"
        data = {"name": "Alice", "role": "admin"}
        tenant_id = "company_a"

        # Store
        store.store_row(row_id, data, tenant_id)

        # Retrieve
        retrieved = store.get_row(row_id, tenant_id)
        assert retrieved == data

    def test_tenant_isolation(self, store):
        """Test that tenants cannot access each other's data."""
        tenant_a = "tenant_a"
        tenant_b = "tenant_b"

        # Tenant A stores data
        store.store_row("row1", {"data": "a"}, tenant_a)

        # Tenant B stores different data with different row ID
        store.store_row("row2", {"data": "b"}, tenant_b)

        # Each tenant gets their own data
        assert store.get_row("row1", tenant_a) == {"data": "a"}
        assert store.get_row("row2", tenant_b) == {"data": "b"}

        # Tenants cannot access each other's data
        assert store.get_row("row1", tenant_b) is None  # tenant_b cannot access tenant_a's row
        assert store.get_row("row2", tenant_a) is None  # tenant_a cannot access tenant_b's row

    def test_list_rows_for_tenant(self, store):
        """Test listing rows accessible by a tenant."""
        tenant_a = "tenant_a"
        tenant_b = "tenant_b"

        # Store rows for different tenants
        store.store_row("row1", {"data": 1}, tenant_a)
        store.store_row("row2", {"data": 2}, tenant_a)
        store.store_row("row3", {"data": 3}, tenant_b)

        # List rows for each tenant
        rows_a = store.list_rows_for_tenant(tenant_a)
        rows_b = store.list_rows_for_tenant(tenant_b)

        assert set(rows_a) == {"row1", "row2"}
        assert set(rows_b) == {"row3"}

    def test_delete_authorization(self, store):
        """Test delete authorization."""
        tenant_a = "tenant_a"
        tenant_b = "tenant_b"

        # Store row for tenant A
        store.store_row("row1", {"data": "test"}, tenant_a)

        # Tenant A can delete
        assert store.delete_row("row1", tenant_a) is True
        assert store.get_row("row1", tenant_a) is None

        # Store another row
        store.store_row("row2", {"data": "test2"}, tenant_a)

        # Tenant B cannot delete
        with pytest.raises(ValueError, match="Access denied"):
            store.delete_row("row2", tenant_b)

    def test_nonexistent_row(self, store):
        """Test accessing nonexistent rows."""
        assert store.get_row("nonexistent", "tenant_123") is None
        assert store.delete_row("nonexistent", "tenant_123") is False

    def test_key_rotation_store(self, store, kms):
        """Test key rotation at the store level."""
        tenant_id = "tenant_123"

        # Store some rows
        store.store_row("row1", {"data": 1}, tenant_id)
        store.store_row("row2", {"data": 2}, tenant_id)

        # Verify initial state
        assert store.get_row("row1", tenant_id) == {"data": 1}
        assert store.get_row("row2", tenant_id) == {"data": 2}

        # Rotate keys
        rotated_count = store.rotate_keys("v1", "v2", tenant_id)
        assert rotated_count == 2

        # Verify data is still accessible after rotation
        assert store.get_row("row1", tenant_id) == {"data": 1}
        assert store.get_row("row2", tenant_id) == {"data": 2}

    def test_encryption_metrics_collection(self, kms):
        """Test that encryption operations can be monitored."""
        encryption = RowLevelEncryption(kms, "v1")

        # Track operation timing
        start_time = time.time()
        data = {"large_field": "x" * 1000}  # Large data for timing
        tenant_id = "tenant_123"

        encrypted_row = encryption.encrypt_row("row1", data, tenant_id)
        encrypt_time = time.time() - start_time

        start_time = time.time()
        decrypted_data = encryption.decrypt_row(encrypted_row, tenant_id)
        decrypt_time = time.time() - start_time

        # Verify operations completed successfully
        assert decrypted_data == data
        assert encrypt_time >= 0
        assert decrypt_time >= 0

        # In a real implementation, these timings would be sent to metrics
        # For now, just verify they're reasonable
        assert encrypt_time < 1.0  # Should be fast
        assert decrypt_time < 1.0


class TestRowEncryptionMetrics:
    """Test metrics collection for row encryption operations."""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
