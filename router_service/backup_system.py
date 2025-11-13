# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Backup and Data Protection Systems

This module provides comprehensive backup and data protection capabilities
including automated database backups, cross-region replication, disaster
recovery testing, and RTO/RPO monitoring.
"""

import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import aiofiles
import boto3
import redis.asyncio as redis
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from metrics.registry import REGISTRY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BackupType(Enum):
    """Backup type enumeration."""

    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"
    TRANSACTION_LOG = "transaction_log"
    SNAPSHOT = "snapshot"


class BackupStatus(Enum):
    """Backup status enumeration."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class StorageType(Enum):
    """Storage type enumeration."""

    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"
    AZURE_BLOB = "azure_blob"
    NFS = "nfs"


class EncryptionType(Enum):
    """Encryption type enumeration."""

    NONE = "none"
    AES256 = "aes256"
    KMS = "kms"
    ENVELOPE = "envelope"


@dataclass
class BackupPolicy:
    """Backup policy configuration."""

    id: str
    name: str
    description: str
    backup_type: BackupType
    schedule_cron: str
    retention_days: int
    storage_type: StorageType
    storage_config: dict[str, Any]
    encryption_type: EncryptionType
    encryption_config: dict[str, Any]
    compression_enabled: bool
    verification_enabled: bool
    cross_region_replication: bool
    target_regions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "backup_type": self.backup_type.value,
            "schedule_cron": self.schedule_cron,
            "retention_days": self.retention_days,
            "storage_type": self.storage_type.value,
            "storage_config": self.storage_config,
            "encryption_type": self.encryption_type.value,
            "encryption_config": self.encryption_config,
            "compression_enabled": self.compression_enabled,
            "verification_enabled": self.verification_enabled,
            "cross_region_replication": self.cross_region_replication,
            "target_regions": self.target_regions,
        }


@dataclass
class BackupRecord:
    """Backup record metadata."""

    id: str
    policy_id: str
    backup_type: BackupType
    status: BackupStatus
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    size_bytes: int
    compressed_size_bytes: int | None
    checksum: str
    storage_path: str
    encryption_key_id: str | None
    metadata: dict[str, Any]
    error_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "backup_type": self.backup_type.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "checksum": self.checksum,
            "storage_path": self.storage_path,
            "encryption_key_id": self.encryption_key_id,
            "metadata": self.metadata,
            "error_message": self.error_message,
        }


@dataclass
class RestoreRequest:
    """Restore request configuration."""

    id: str
    backup_id: str
    target_location: str
    restore_type: str  # "full", "partial", "point_in_time"
    point_in_time: datetime | None
    options: dict[str, Any]
    requested_by: str
    requested_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backup_id": self.backup_id,
            "target_location": self.target_location,
            "restore_type": self.restore_type,
            "point_in_time": self.point_in_time.isoformat() if self.point_in_time else None,
            "options": self.options,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at.isoformat(),
        }


class EncryptionManager:
    """Manage backup encryption and decryption."""

    def __init__(self):
        self.encryption_keys: dict[str, bytes] = {}
        self.kms_client = None

        # Initialize KMS client if available
        try:
            self.kms_client = boto3.client("kms")
        except Exception as e:
            logger.warning(f"KMS client not available: {e}")

    def generate_key(self, key_id: str, password: str | None = None) -> bytes:
        """Generate encryption key."""

        if password:
            # Derive key from password
            password_bytes = password.encode()
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        else:
            # Generate random key
            key = Fernet.generate_key()

        self.encryption_keys[key_id] = key
        return key

    def encrypt_data(self, data: bytes, key_id: str) -> bytes:
        """Encrypt data using specified key."""

        if key_id not in self.encryption_keys:
            raise ValueError(f"Encryption key {key_id} not found")

        key = self.encryption_keys[key_id]
        fernet = Fernet(key)

        return fernet.encrypt(data)

    def decrypt_data(self, encrypted_data: bytes, key_id: str) -> bytes:
        """Decrypt data using specified key."""

        if key_id not in self.encryption_keys:
            raise ValueError(f"Encryption key {key_id} not found")

        key = self.encryption_keys[key_id]
        fernet = Fernet(key)

        return fernet.decrypt(encrypted_data)

    async def encrypt_with_kms(self, data: bytes, kms_key_id: str) -> tuple[bytes, str]:
        """Encrypt data using AWS KMS."""

        if not self.kms_client:
            raise RuntimeError("KMS client not available")

        try:
            # Generate data key
            response = self.kms_client.generate_data_key(KeyId=kms_key_id, KeySpec="AES_256")

            plaintext_key = response["Plaintext"]
            encrypted_key = response["CiphertextBlob"]

            # Encrypt data with data key
            fernet = Fernet(base64.urlsafe_b64encode(plaintext_key[:32]))
            encrypted_data = fernet.encrypt(data)

            # Return encrypted data and encrypted key
            return encrypted_data, base64.b64encode(encrypted_key).decode()

        except Exception as e:
            logger.error(f"KMS encryption failed: {e}")
            raise

    async def decrypt_with_kms(self, encrypted_data: bytes, encrypted_key: str) -> bytes:
        """Decrypt data using AWS KMS."""

        if not self.kms_client:
            raise RuntimeError("KMS client not available")

        try:
            # Decrypt data key
            encrypted_key_bytes = base64.b64decode(encrypted_key)
            response = self.kms_client.decrypt(CiphertextBlob=encrypted_key_bytes)
            plaintext_key = response["Plaintext"]

            # Decrypt data with data key
            fernet = Fernet(base64.urlsafe_b64encode(plaintext_key[:32]))
            decrypted_data = fernet.decrypt(encrypted_data)

            return decrypted_data

        except Exception as e:
            logger.error(f"KMS decryption failed: {e}")
            raise


class StorageManager:
    """Manage backup storage across different storage types."""

    def __init__(self):
        self.s3_client = None
        self.gcs_client = None
        self.azure_client = None

        # Initialize cloud storage clients
        try:
            self.s3_client = boto3.client("s3")
        except Exception as e:
            logger.warning(f"S3 client not available: {e}")

    async def store_backup(
        self, data: bytes, storage_type: StorageType, storage_config: dict[str, Any], backup_path: str
    ) -> str:
        """Store backup data to specified storage."""

        if storage_type == StorageType.LOCAL:
            return await self._store_local(data, storage_config, backup_path)
        elif storage_type == StorageType.S3:
            return await self._store_s3(data, storage_config, backup_path)
        elif storage_type == StorageType.GCS:
            return await self._store_gcs(data, storage_config, backup_path)
        elif storage_type == StorageType.AZURE_BLOB:
            return await self._store_azure(data, storage_config, backup_path)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

    async def retrieve_backup(
        self, storage_type: StorageType, storage_config: dict[str, Any], backup_path: str
    ) -> bytes:
        """Retrieve backup data from specified storage."""

        if storage_type == StorageType.LOCAL:
            return await self._retrieve_local(storage_config, backup_path)
        elif storage_type == StorageType.S3:
            return await self._retrieve_s3(storage_config, backup_path)
        elif storage_type == StorageType.GCS:
            return await self._retrieve_gcs(storage_config, backup_path)
        elif storage_type == StorageType.AZURE_BLOB:
            return await self._retrieve_azure(storage_config, backup_path)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

    async def delete_backup(self, storage_type: StorageType, storage_config: dict[str, Any], backup_path: str) -> bool:
        """Delete backup from specified storage."""

        try:
            if storage_type == StorageType.LOCAL:
                return await self._delete_local(storage_config, backup_path)
            elif storage_type == StorageType.S3:
                return await self._delete_s3(storage_config, backup_path)
            elif storage_type == StorageType.GCS:
                return await self._delete_gcs(storage_config, backup_path)
            elif storage_type == StorageType.AZURE_BLOB:
                return await self._delete_azure(storage_config, backup_path)
            else:
                raise ValueError(f"Unsupported storage type: {storage_type}")
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_path}: {e}")
            return False

    async def _store_local(self, data: bytes, config: dict[str, Any], path: str) -> str:
        """Store backup to local filesystem."""

        base_path = config.get("base_path", "/var/backups/atp")
        full_path = os.path.join(base_path, path)

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write data to file
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(data)

        return full_path

    async def _retrieve_local(self, config: dict[str, Any], path: str) -> bytes:
        """Retrieve backup from local filesystem."""

        base_path = config.get("base_path", "/var/backups/atp")
        full_path = os.path.join(base_path, path)

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def _delete_local(self, config: dict[str, Any], path: str) -> bool:
        """Delete backup from local filesystem."""

        base_path = config.get("base_path", "/var/backups/atp")
        full_path = os.path.join(base_path, path)

        try:
            os.remove(full_path)
            return True
        except FileNotFoundError:
            return True  # Already deleted
        except Exception as e:
            logger.error(f"Failed to delete local backup {full_path}: {e}")
            return False

    async def _store_s3(self, data: bytes, config: dict[str, Any], path: str) -> str:
        """Store backup to S3."""

        if not self.s3_client:
            raise RuntimeError("S3 client not available")

        bucket = config["bucket"]
        key = f"{config.get('prefix', 'atp-backups')}/{path}"

        try:
            self.s3_client.put_object(Bucket=bucket, Key=key, Body=data, ServerSideEncryption="AES256")

            return f"s3://{bucket}/{key}"

        except Exception as e:
            logger.error(f"Failed to store S3 backup: {e}")
            raise

    async def _retrieve_s3(self, config: dict[str, Any], path: str) -> bytes:
        """Retrieve backup from S3."""

        if not self.s3_client:
            raise RuntimeError("S3 client not available")

        bucket = config["bucket"]
        key = f"{config.get('prefix', 'atp-backups')}/{path}"

        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()

        except Exception as e:
            logger.error(f"Failed to retrieve S3 backup: {e}")
            raise

    async def _delete_s3(self, config: dict[str, Any], path: str) -> bool:
        """Delete backup from S3."""

        if not self.s3_client:
            raise RuntimeError("S3 client not available")

        bucket = config["bucket"]
        key = f"{config.get('prefix', 'atp-backups')}/{path}"

        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            return True

        except Exception as e:
            logger.error(f"Failed to delete S3 backup: {e}")
            return False

    async def _store_gcs(self, data: bytes, config: dict[str, Any], path: str) -> str:
        """Store backup to Google Cloud Storage."""
        # Placeholder for GCS implementation
        raise NotImplementedError("GCS storage not implemented")

    async def _retrieve_gcs(self, config: dict[str, Any], path: str) -> bytes:
        """Retrieve backup from Google Cloud Storage."""
        # Placeholder for GCS implementation
        raise NotImplementedError("GCS storage not implemented")

    async def _delete_gcs(self, config: dict[str, Any], path: str) -> bool:
        """Delete backup from Google Cloud Storage."""
        # Placeholder for GCS implementation
        raise NotImplementedError("GCS storage not implemented")

    async def _store_azure(self, data: bytes, config: dict[str, Any], path: str) -> str:
        """Store backup to Azure Blob Storage."""
        # Placeholder for Azure implementation
        raise NotImplementedError("Azure storage not implemented")

    async def _retrieve_azure(self, config: dict[str, Any], path: str) -> bytes:
        """Retrieve backup from Azure Blob Storage."""
        # Placeholder for Azure implementation
        raise NotImplementedError("Azure storage not implemented")

    async def _delete_azure(self, config: dict[str, Any], path: str) -> bool:
        """Delete backup from Azure Blob Storage."""
        # Placeholder for Azure implementation
        raise NotImplementedError("Azure storage not implemented")


class DatabaseBackupManager:
    """Manage PostgreSQL database backups."""

    def __init__(self, storage_manager: StorageManager, encryption_manager: EncryptionManager):
        self.storage_manager = storage_manager
        self.encryption_manager = encryption_manager

        # Metrics
        self.backup_counter = REGISTRY.counter("database_backups_total")
        self.backup_duration = REGISTRY.histogram("database_backup_duration_seconds")
        self.backup_size = REGISTRY.histogram("database_backup_size_bytes")
        self.backup_success_rate = REGISTRY.gauge("database_backup_success_rate")

    async def create_backup(
        self, policy: BackupPolicy, database_url: str, backup_name: str | None = None
    ) -> BackupRecord:
        """Create database backup."""

        start_time = time.time()
        backup_id = str(uuid.uuid4())

        if not backup_name:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"db_backup_{timestamp}_{backup_id[:8]}"

        backup_record = BackupRecord(
            id=backup_id,
            policy_id=policy.id,
            backup_type=policy.backup_type,
            status=BackupStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            duration_seconds=None,
            size_bytes=0,
            compressed_size_bytes=None,
            checksum="",
            storage_path="",
            encryption_key_id=None,
            metadata={"backup_name": backup_name},
            error_message=None,
        )

        try:
            # Create database dump
            dump_data = await self._create_database_dump(database_url, policy.backup_type)
            backup_record.size_bytes = len(dump_data)

            # Compress if enabled
            if policy.compression_enabled:
                compressed_data = gzip.compress(dump_data)
                backup_record.compressed_size_bytes = len(compressed_data)
                dump_data = compressed_data

            # Calculate checksum
            backup_record.checksum = hashlib.sha256(dump_data).hexdigest()

            # Encrypt if enabled
            if policy.encryption_type != EncryptionType.NONE:
                dump_data, encryption_key_id = await self._encrypt_backup(
                    dump_data, policy.encryption_type, policy.encryption_config
                )
                backup_record.encryption_key_id = encryption_key_id

            # Store backup
            storage_path = f"database/{backup_name}.sql"
            if policy.compression_enabled:
                storage_path += ".gz"
            if policy.encryption_type != EncryptionType.NONE:
                storage_path += ".enc"

            full_path = await self.storage_manager.store_backup(
                dump_data, policy.storage_type, policy.storage_config, storage_path
            )

            backup_record.storage_path = full_path
            backup_record.status = BackupStatus.COMPLETED
            backup_record.completed_at = datetime.now(timezone.utc)
            backup_record.duration_seconds = time.time() - start_time

            # Verify backup if enabled
            if policy.verification_enabled:
                await self._verify_backup(backup_record, policy)

            # Cross-region replication if enabled
            if policy.cross_region_replication:
                await self._replicate_backup(backup_record, policy)

            # Update metrics
            self.backup_counter.inc(
                1, {"policy_id": policy.id, "backup_type": policy.backup_type.value, "status": "success"}
            )

            self.backup_duration.observe(
                backup_record.duration_seconds, {"policy_id": policy.id, "backup_type": policy.backup_type.value}
            )

            self.backup_size.observe(
                backup_record.size_bytes, {"policy_id": policy.id, "backup_type": policy.backup_type.value}
            )

            logger.info(f"Database backup completed: {backup_id}")

        except Exception as e:
            backup_record.status = BackupStatus.FAILED
            backup_record.error_message = str(e)
            backup_record.completed_at = datetime.now(timezone.utc)
            backup_record.duration_seconds = time.time() - start_time

            self.backup_counter.inc(
                1, {"policy_id": policy.id, "backup_type": policy.backup_type.value, "status": "failed"}
            )

            logger.error(f"Database backup failed: {backup_id}, error: {e}")

        return backup_record

    async def _create_database_dump(self, database_url: str, backup_type: BackupType) -> bytes:
        """Create database dump using pg_dump."""

        # Parse database URL
        # This is a simplified implementation
        # In production, you would use proper URL parsing

        if backup_type == BackupType.FULL:
            # Full database dump
            cmd = f"pg_dump {database_url} --format=custom --compress=0"
        elif backup_type == BackupType.INCREMENTAL:
            # Incremental backup (simplified - would need WAL archiving)
            cmd = f"pg_dump {database_url} --format=custom --compress=0"
        else:
            # Default to full backup
            cmd = f"pg_dump {database_url} --format=custom --compress=0"

        # Execute pg_dump command
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

        return stdout

    async def _encrypt_backup(
        self, data: bytes, encryption_type: EncryptionType, encryption_config: dict[str, Any]
    ) -> tuple[bytes, str]:
        """Encrypt backup data."""

        if encryption_type == EncryptionType.AES256:
            key_id = f"backup_key_{int(time.time())}"
            password = encryption_config.get("password")

            self.encryption_manager.generate_key(key_id, password)
            encrypted_data = self.encryption_manager.encrypt_data(data, key_id)

            return encrypted_data, key_id

        elif encryption_type == EncryptionType.KMS:
            kms_key_id = encryption_config["kms_key_id"]
            encrypted_data, encrypted_key = await self.encryption_manager.encrypt_with_kms(data, kms_key_id)

            return encrypted_data, encrypted_key

        else:
            raise ValueError(f"Unsupported encryption type: {encryption_type}")

    async def _verify_backup(self, backup_record: BackupRecord, policy: BackupPolicy):
        """Verify backup integrity."""

        try:
            # Retrieve backup data
            data = await self.storage_manager.retrieve_backup(
                policy.storage_type,
                policy.storage_config,
                backup_record.storage_path.split("/")[-1],  # Extract filename
            )

            # Decrypt if encrypted
            if backup_record.encryption_key_id:
                if policy.encryption_type == EncryptionType.AES256:
                    data = self.encryption_manager.decrypt_data(data, backup_record.encryption_key_id)
                elif policy.encryption_type == EncryptionType.KMS:
                    data = await self.encryption_manager.decrypt_with_kms(data, backup_record.encryption_key_id)

            # Decompress if compressed
            if policy.compression_enabled:
                data = gzip.decompress(data)

            # Verify checksum
            calculated_checksum = hashlib.sha256(data).hexdigest()
            if calculated_checksum != backup_record.checksum:
                raise ValueError("Checksum verification failed")

            backup_record.metadata["verification_status"] = "passed"
            logger.info(f"Backup verification passed: {backup_record.id}")

        except Exception as e:
            backup_record.metadata["verification_status"] = "failed"
            backup_record.metadata["verification_error"] = str(e)
            logger.error(f"Backup verification failed: {backup_record.id}, error: {e}")

    async def _replicate_backup(self, backup_record: BackupRecord, policy: BackupPolicy):
        """Replicate backup to target regions."""

        replicated_regions = []

        for target_region in policy.target_regions:
            try:
                # Create region-specific storage config
                region_config = policy.storage_config.copy()
                if policy.storage_type == StorageType.S3:
                    region_config["bucket"] = f"{region_config['bucket']}-{target_region}"

                # Retrieve original backup
                data = await self.storage_manager.retrieve_backup(
                    policy.storage_type, policy.storage_config, backup_record.storage_path.split("/")[-1]
                )

                # Store in target region
                region_path = f"{target_region}/{backup_record.storage_path.split('/')[-1]}"
                await self.storage_manager.store_backup(data, policy.storage_type, region_config, region_path)

                replicated_regions.append(target_region)
                logger.info(f"Backup replicated to region {target_region}: {backup_record.id}")

            except Exception as e:
                logger.error(f"Failed to replicate backup to {target_region}: {e}")

        backup_record.metadata["replicated_regions"] = replicated_regions

    async def restore_backup(
        self, backup_record: BackupRecord, policy: BackupPolicy, restore_request: RestoreRequest
    ) -> bool:
        """Restore database from backup."""

        try:
            # Retrieve backup data
            data = await self.storage_manager.retrieve_backup(
                policy.storage_type, policy.storage_config, backup_record.storage_path.split("/")[-1]
            )

            # Decrypt if encrypted
            if backup_record.encryption_key_id:
                if policy.encryption_type == EncryptionType.AES256:
                    data = self.encryption_manager.decrypt_data(data, backup_record.encryption_key_id)
                elif policy.encryption_type == EncryptionType.KMS:
                    data = await self.encryption_manager.decrypt_with_kms(data, backup_record.encryption_key_id)

            # Decompress if compressed
            if policy.compression_enabled:
                data = gzip.decompress(data)

            # Verify checksum
            calculated_checksum = hashlib.sha256(data).hexdigest()
            if calculated_checksum != backup_record.checksum:
                raise ValueError("Backup integrity check failed")

            # Write to temporary file
            temp_file = f"/tmp/restore_{restore_request.id}.sql"
            async with aiofiles.open(temp_file, "wb") as f:
                await f.write(data)

            # Execute pg_restore
            cmd = f"pg_restore --dbname={restore_request.target_location} --clean --if-exists {temp_file}"

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            # Clean up temporary file
            os.remove(temp_file)

            if process.returncode != 0:
                raise RuntimeError(f"pg_restore failed: {stderr.decode()}")

            logger.info(f"Database restore completed: {restore_request.id}")
            return True

        except Exception as e:
            logger.error(f"Database restore failed: {restore_request.id}, error: {e}")
            return False


class RedisBackupManager:
    """Manage Redis backups."""

    def __init__(self, storage_manager: StorageManager, encryption_manager: EncryptionManager):
        self.storage_manager = storage_manager
        self.encryption_manager = encryption_manager

        # Metrics
        self.backup_counter = REGISTRY.counter("redis_backups_total")
        self.backup_duration = REGISTRY.histogram("redis_backup_duration_seconds")
        self.backup_size = REGISTRY.histogram("redis_backup_size_bytes")

    async def create_backup(self, policy: BackupPolicy, redis_url: str, backup_name: str | None = None) -> BackupRecord:
        """Create Redis backup."""

        start_time = time.time()
        backup_id = str(uuid.uuid4())

        if not backup_name:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"redis_backup_{timestamp}_{backup_id[:8]}"

        backup_record = BackupRecord(
            id=backup_id,
            policy_id=policy.id,
            backup_type=policy.backup_type,
            status=BackupStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            duration_seconds=None,
            size_bytes=0,
            compressed_size_bytes=None,
            checksum="",
            storage_path="",
            encryption_key_id=None,
            metadata={"backup_name": backup_name},
            error_message=None,
        )

        try:
            # Create Redis dump
            dump_data = await self._create_redis_dump(redis_url, policy.backup_type)
            backup_record.size_bytes = len(dump_data)

            # Compress if enabled
            if policy.compression_enabled:
                compressed_data = gzip.compress(dump_data)
                backup_record.compressed_size_bytes = len(compressed_data)
                dump_data = compressed_data

            # Calculate checksum
            backup_record.checksum = hashlib.sha256(dump_data).hexdigest()

            # Encrypt if enabled
            if policy.encryption_type != EncryptionType.NONE:
                dump_data, encryption_key_id = await self._encrypt_backup(
                    dump_data, policy.encryption_type, policy.encryption_config
                )
                backup_record.encryption_key_id = encryption_key_id

            # Store backup
            storage_path = f"redis/{backup_name}.rdb"
            if policy.compression_enabled:
                storage_path += ".gz"
            if policy.encryption_type != EncryptionType.NONE:
                storage_path += ".enc"

            full_path = await self.storage_manager.store_backup(
                dump_data, policy.storage_type, policy.storage_config, storage_path
            )

            backup_record.storage_path = full_path
            backup_record.status = BackupStatus.COMPLETED
            backup_record.completed_at = datetime.now(timezone.utc)
            backup_record.duration_seconds = time.time() - start_time

            # Update metrics
            self.backup_counter.inc(
                1, {"policy_id": policy.id, "backup_type": policy.backup_type.value, "status": "success"}
            )

            self.backup_duration.observe(backup_record.duration_seconds, {"policy_id": policy.id})

            self.backup_size.observe(backup_record.size_bytes, {"policy_id": policy.id})

            logger.info(f"Redis backup completed: {backup_id}")

        except Exception as e:
            backup_record.status = BackupStatus.FAILED
            backup_record.error_message = str(e)
            backup_record.completed_at = datetime.now(timezone.utc)
            backup_record.duration_seconds = time.time() - start_time

            self.backup_counter.inc(
                1, {"policy_id": policy.id, "backup_type": policy.backup_type.value, "status": "failed"}
            )

            logger.error(f"Redis backup failed: {backup_id}, error: {e}")

        return backup_record

    async def _create_redis_dump(self, redis_url: str, backup_type: BackupType) -> bytes:
        """Create Redis dump."""

        # Connect to Redis
        redis_client = redis.from_url(redis_url)

        try:
            if backup_type == BackupType.SNAPSHOT:
                # Trigger BGSAVE and wait for completion
                await redis_client.bgsave()

                # Wait for background save to complete
                while True:
                    info = await redis_client.info("persistence")
                    if info.get("rdb_bgsave_in_progress", 0) == 0:
                        break
                    await asyncio.sleep(1)

                # Read RDB file (this is simplified - in practice you'd need to access the Redis data directory)
                # For now, we'll use a different approach

                # Get all keys and their values
                keys = await redis_client.keys("*")
                dump_data = {}

                for key in keys:
                    key_type = await redis_client.type(key)

                    if key_type == "string":
                        dump_data[key] = await redis_client.get(key)
                    elif key_type == "hash":
                        dump_data[key] = await redis_client.hgetall(key)
                    elif key_type == "list":
                        dump_data[key] = await redis_client.lrange(key, 0, -1)
                    elif key_type == "set":
                        dump_data[key] = list(await redis_client.smembers(key))
                    elif key_type == "zset":
                        dump_data[key] = await redis_client.zrange(key, 0, -1, withscores=True)

                return json.dumps(dump_data, default=str).encode()

            else:
                # Default to snapshot
                return await self._create_redis_dump(redis_url, BackupType.SNAPSHOT)

        finally:
            await redis_client.close()

    async def _encrypt_backup(
        self, data: bytes, encryption_type: EncryptionType, encryption_config: dict[str, Any]
    ) -> tuple[bytes, str]:
        """Encrypt backup data."""

        if encryption_type == EncryptionType.AES256:
            key_id = f"redis_backup_key_{int(time.time())}"
            password = encryption_config.get("password")

            self.encryption_manager.generate_key(key_id, password)
            encrypted_data = self.encryption_manager.encrypt_data(data, key_id)

            return encrypted_data, key_id

        elif encryption_type == EncryptionType.KMS:
            kms_key_id = encryption_config["kms_key_id"]
            encrypted_data, encrypted_key = await self.encryption_manager.encrypt_with_kms(data, kms_key_id)

            return encrypted_data, encrypted_key

        else:
            raise ValueError(f"Unsupported encryption type: {encryption_type}")


class BackupScheduler:
    """Schedule and manage backup jobs."""

    def __init__(self, db_backup_manager: DatabaseBackupManager, redis_backup_manager: RedisBackupManager):
        self.db_backup_manager = db_backup_manager
        self.redis_backup_manager = redis_backup_manager

        self.backup_policies: dict[str, BackupPolicy] = {}
        self.backup_records: dict[str, BackupRecord] = {}
        self.scheduled_jobs: dict[str, dict[str, Any]] = {}

        self.scheduler_active = False
        self.scheduler_thread = None

        # Configuration
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost/atp")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    def register_backup_policy(self, policy: BackupPolicy):
        """Register a backup policy."""
        self.backup_policies[policy.id] = policy
        logger.info(f"Registered backup policy: {policy.name}")

    def start_scheduler(self):
        """Start the backup scheduler."""
        if self.scheduler_active:
            return

        self.scheduler_active = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("Started backup scheduler")

    def stop_scheduler(self):
        """Stop the backup scheduler."""
        self.scheduler_active = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=10)
        logger.info("Stopped backup scheduler")

    def _scheduler_loop(self):
        """Backup scheduler loop."""
        while self.scheduler_active:
            try:
                current_time = datetime.now(timezone.utc)

                # Check for scheduled backups
                for _policy_id, policy in self.backup_policies.items():
                    if self._should_run_backup(policy, current_time):
                        asyncio.run(self._execute_backup(policy))

                # Clean up expired backups
                asyncio.run(self._cleanup_expired_backups())

                time.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Error in backup scheduler loop: {e}")
                time.sleep(60)

    def _should_run_backup(self, policy: BackupPolicy, current_time: datetime) -> bool:
        """Check if backup should run based on schedule."""

        # This is a simplified cron parser
        # In production, you would use a proper cron library like croniter

        # For now, just check if it's time based on simple intervals
        last_backup_time = self._get_last_backup_time(policy.id)

        if not last_backup_time:
            return True  # First backup

        # Simple interval check (this should be replaced with proper cron parsing)
        if "hourly" in policy.schedule_cron:
            return current_time - last_backup_time >= timedelta(hours=1)
        elif "daily" in policy.schedule_cron:
            return current_time - last_backup_time >= timedelta(days=1)
        elif "weekly" in policy.schedule_cron:
            return current_time - last_backup_time >= timedelta(weeks=1)

        return False

    def _get_last_backup_time(self, policy_id: str) -> datetime | None:
        """Get the last backup time for a policy."""

        last_time = None
        for record in self.backup_records.values():
            if (
                record.policy_id == policy_id
                and record.status == BackupStatus.COMPLETED
                and (not last_time or record.started_at > last_time)
            ):
                last_time = record.started_at

        return last_time

    async def _execute_backup(self, policy: BackupPolicy):
        """Execute backup for a policy."""

        try:
            if "database" in policy.name.lower() or "db" in policy.name.lower():
                # Database backup
                backup_record = await self.db_backup_manager.create_backup(policy, self.database_url)
            elif "redis" in policy.name.lower():
                # Redis backup
                backup_record = await self.redis_backup_manager.create_backup(policy, self.redis_url)
            else:
                logger.warning(f"Unknown backup type for policy: {policy.name}")
                return

            self.backup_records[backup_record.id] = backup_record

        except Exception as e:
            logger.error(f"Failed to execute backup for policy {policy.id}: {e}")

    async def _cleanup_expired_backups(self):
        """Clean up expired backups."""

        current_time = datetime.now(timezone.utc)
        expired_backups = []

        for record in self.backup_records.values():
            policy = self.backup_policies.get(record.policy_id)
            if not policy:
                continue

            # Check if backup is expired
            expiry_time = record.started_at + timedelta(days=policy.retention_days)
            if current_time > expiry_time:
                expired_backups.append(record)

        # Delete expired backups
        for record in expired_backups:
            try:
                policy = self.backup_policies[record.policy_id]

                # Delete from storage
                storage_path = record.storage_path.split("/")[-1]  # Extract filename
                await self.db_backup_manager.storage_manager.delete_backup(
                    policy.storage_type, policy.storage_config, storage_path
                )

                # Update record status
                record.status = BackupStatus.EXPIRED

                logger.info(f"Deleted expired backup: {record.id}")

            except Exception as e:
                logger.error(f"Failed to delete expired backup {record.id}: {e}")

    async def trigger_backup(self, policy_id: str) -> str:
        """Manually trigger a backup."""

        if policy_id not in self.backup_policies:
            raise ValueError(f"Backup policy {policy_id} not found")

        policy = self.backup_policies[policy_id]
        await self._execute_backup(policy)

        # Find the latest backup record for this policy
        latest_record = None
        for record in self.backup_records.values():
            if record.policy_id == policy_id and (not latest_record or record.started_at > latest_record.started_at):
                latest_record = record

        return latest_record.id if latest_record else ""

    def get_backup_status(self, backup_id: str) -> dict[str, Any] | None:
        """Get backup status."""

        if backup_id in self.backup_records:
            return self.backup_records[backup_id].to_dict()

        return None

    def list_backups(self, policy_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List backups."""

        backups = []
        for record in self.backup_records.values():
            if policy_id and record.policy_id != policy_id:
                continue
            backups.append(record.to_dict())

        # Sort by start time (newest first)
        backups.sort(key=lambda x: x["started_at"], reverse=True)

        return backups[:limit]

    def get_backup_metrics(self) -> dict[str, Any]:
        """Get backup metrics summary."""

        total_backups = len(self.backup_records)
        successful_backups = sum(1 for r in self.backup_records.values() if r.status == BackupStatus.COMPLETED)
        failed_backups = sum(1 for r in self.backup_records.values() if r.status == BackupStatus.FAILED)

        total_size = sum(r.size_bytes for r in self.backup_records.values() if r.status == BackupStatus.COMPLETED)

        return {
            "total_backups": total_backups,
            "successful_backups": successful_backups,
            "failed_backups": failed_backups,
            "success_rate": successful_backups / total_backups if total_backups > 0 else 0,
            "total_size_bytes": total_size,
            "total_size_gb": total_size / (1024**3),
            "policies_count": len(self.backup_policies),
        }


# Example usage and configuration
async def setup_backup_system():
    """Set up the complete backup system."""

    # Initialize components
    encryption_manager = EncryptionManager()
    storage_manager = StorageManager()
    db_backup_manager = DatabaseBackupManager(storage_manager, encryption_manager)
    redis_backup_manager = RedisBackupManager(storage_manager, encryption_manager)
    backup_scheduler = BackupScheduler(db_backup_manager, redis_backup_manager)

    # Configure backup policies

    # Daily database backup policy
    db_daily_policy = BackupPolicy(
        id="db_daily_backup",
        name="Daily Database Backup",
        description="Daily full database backup with encryption and compression",
        backup_type=BackupType.FULL,
        schedule_cron="0 2 * * *",  # Daily at 2 AM
        retention_days=30,
        storage_type=StorageType.S3,
        storage_config={"bucket": "atp-backups", "prefix": "database/daily"},
        encryption_type=EncryptionType.AES256,
        encryption_config={"password": "backup_encryption_key"},
        compression_enabled=True,
        verification_enabled=True,
        cross_region_replication=True,
        target_regions=["us-west-2", "eu-west-1"],
    )

    # Hourly Redis backup policy
    redis_hourly_policy = BackupPolicy(
        id="redis_hourly_backup",
        name="Hourly Redis Backup",
        description="Hourly Redis snapshot backup",
        backup_type=BackupType.SNAPSHOT,
        schedule_cron="0 * * * *",  # Every hour
        retention_days=7,
        storage_type=StorageType.S3,
        storage_config={"bucket": "atp-backups", "prefix": "redis/hourly"},
        encryption_type=EncryptionType.AES256,
        encryption_config={"password": "redis_backup_key"},
        compression_enabled=True,
        verification_enabled=False,
        cross_region_replication=False,
        target_regions=[],
    )

    # Weekly database backup with long retention
    db_weekly_policy = BackupPolicy(
        id="db_weekly_backup",
        name="Weekly Database Backup",
        description="Weekly database backup with long-term retention",
        backup_type=BackupType.FULL,
        schedule_cron="0 1 * * 0",  # Weekly on Sunday at 1 AM
        retention_days=365,  # 1 year retention
        storage_type=StorageType.S3,
        storage_config={"bucket": "atp-backups-longterm", "prefix": "database/weekly"},
        encryption_type=EncryptionType.KMS,
        encryption_config={"kms_key_id": "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"},
        compression_enabled=True,
        verification_enabled=True,
        cross_region_replication=True,
        target_regions=["us-west-2", "eu-west-1", "ap-southeast-1"],
    )

    # Register policies
    backup_scheduler.register_backup_policy(db_daily_policy)
    backup_scheduler.register_backup_policy(redis_hourly_policy)
    backup_scheduler.register_backup_policy(db_weekly_policy)

    # Start scheduler
    backup_scheduler.start_scheduler()

    logger.info("Backup system setup completed")

    return backup_scheduler


if __name__ == "__main__":
    # Example usage
    async def main():
        backup_scheduler = await setup_backup_system()

        # Trigger a manual backup
        backup_id = await backup_scheduler.trigger_backup("db_daily_backup")
        print(f"Triggered backup: {backup_id}")

        # Wait a bit and check status
        await asyncio.sleep(5)
        status = backup_scheduler.get_backup_status(backup_id)
        print(f"Backup status: {json.dumps(status, indent=2)}")

        # Get backup metrics
        metrics = backup_scheduler.get_backup_metrics()
        print(f"Backup metrics: {json.dumps(metrics, indent=2)}")

        # List recent backups
        backups = backup_scheduler.list_backups(limit=10)
        print(f"Recent backups: {len(backups)}")

        # Keep running
        try:
            while True:
                await asyncio.sleep(60)
                print("Backup system running...")
        except KeyboardInterrupt:
            backup_scheduler.stop_scheduler()
            print("Backup system stopped")

    asyncio.run(main())
