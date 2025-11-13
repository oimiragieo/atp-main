#!/usr/bin/env python3
"""GAP-304: Ingestion policy & schema evolution.

Implements JSON Schema registry with version negotiation and backward-compatible evolution.
Supports schema validation, migration, and policy enforcement for data ingestion.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from tools.schema_migration_poc import MigrationRegistry

# Setup logger
logger = logging.getLogger(__name__)


@dataclass
class SchemaVersion:
    """Represents a schema version with metadata."""

    schema_id: str
    version: int
    schema: dict[str, Any]
    created_at: float
    description: str
    is_active: bool = True
    compatibility_rules: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """Result of schema validation."""

    valid: bool
    errors: list[str]
    schema_id: str
    schema_version: int
    data_version: int | None = None


class SchemaRegistry:
    """Registry for JSON schemas with version management and evolution support."""

    def __init__(self, storage_path: str | None = None):
        self.schemas: dict[str, list[SchemaVersion]] = {}
        self.migration_registries: dict[str, MigrationRegistry] = {}
        self.storage_path = Path(storage_path) if storage_path else None

        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def register_schema(
        self,
        schema_id: str,
        schema: dict[str, Any],
        description: str = "",
        compatibility_rules: dict[str, Any] | None = None,
    ) -> int:
        """Register a new schema version.

        Args:
            schema_id: Unique identifier for the schema
            schema: JSON schema definition
            description: Human-readable description
            compatibility_rules: Rules for backward compatibility

        Returns:
            The version number assigned to this schema
        """
        if schema_id not in self.schemas:
            self.schemas[schema_id] = []
            self.migration_registries[schema_id] = MigrationRegistry()

        # Determine next version
        current_version = max([sv.version for sv in self.schemas[schema_id]], default=0)
        new_version = current_version + 1

        # Create schema version
        schema_version = SchemaVersion(
            schema_id=schema_id,
            version=new_version,
            schema=schema,
            created_at=time.time(),
            description=description,
            compatibility_rules=compatibility_rules,
        )

        self.schemas[schema_id].append(schema_version)

        # Save to disk if storage path is configured
        if self.storage_path:
            self._save_to_disk()

        logger.info(f"Registered schema {schema_id} version {new_version}")
        return new_version

    def get_schema(self, schema_id: str, version: int | None = None) -> SchemaVersion | None:
        """Get a specific schema version.

        Args:
            schema_id: Schema identifier
            version: Specific version (latest if None)

        Returns:
            SchemaVersion or None if not found
        """
        if schema_id not in self.schemas:
            return None

        versions = self.schemas[schema_id]
        if not versions:
            return None

        if version is None:
            # Return latest active version
            active_versions = [sv for sv in versions if sv.is_active]
            return max(active_versions, key=lambda sv: sv.version) if active_versions else None

        # Return specific version
        for sv in versions:
            if sv.version == version:
                return sv

        return None

    def validate_data(self, schema_id: str, data: dict[str, Any], data_version: int | None = None) -> ValidationResult:
        """Validate data against a schema.

        Args:
            schema_id: Schema identifier
            data: Data to validate
            data_version: Data version (for migration)

        Returns:
            ValidationResult with validation status and errors
        """
        if not JSONSCHEMA_AVAILABLE:
            return ValidationResult(
                valid=False,
                errors=["JSON schema validation not available (jsonschema package not installed)"],
                schema_id=schema_id,
                schema_version=0,
            )

        schema_version = self.get_schema(schema_id)
        if not schema_version:
            return ValidationResult(
                valid=False, errors=[f"Schema {schema_id} not found"], schema_id=schema_id, schema_version=0
            )

        try:
            jsonschema.validate(data, schema_version.schema)
            return ValidationResult(
                valid=True,
                errors=[],
                schema_id=schema_id,
                schema_version=schema_version.version,
                data_version=data_version,
            )
        except jsonschema.ValidationError as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
                schema_id=schema_id,
                schema_version=schema_version.version,
                data_version=data_version,
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[f"Validation error: {str(e)}"],
                schema_id=schema_id,
                schema_version=schema_version.version,
                data_version=data_version,
            )

    def migrate_data(self, schema_id: str, data: dict[str, Any], from_version: int, to_version: int) -> dict[str, Any]:
        """Migrate data from one schema version to another.

        Args:
            schema_id: Schema identifier
            data: Data to migrate
            from_version: Source version
            to_version: Target version

        Returns:
            Migrated data

        Raises:
            ValueError: If migration fails
        """
        if schema_id not in self.migration_registries:
            raise ValueError(f"No migration registry for schema {schema_id}")

        registry = self.migration_registries[schema_id]
        return registry.upgrade(data, from_version, to_version)

    def register_migration(
        self,
        schema_id: str,
        from_version: int,
        to_version: int,
        migration_func: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a migration function between schema versions.

        Args:
            schema_id: Schema identifier
            from_version: Source version
            to_version: Target version
            migration_func: Function to perform the migration
        """
        from tools.schema_migration_poc import Migration

        if schema_id not in self.migration_registries:
            self.migration_registries[schema_id] = MigrationRegistry()

        registry = self.migration_registries[schema_id]
        migration = Migration(from_version, to_version, migration_func)
        registry.register(migration)

        logger.info(f"Registered migration for {schema_id}: v{from_version} -> v{to_version}")

    def negotiate_version(self, schema_id: str, client_supported_versions: list[int]) -> int | None:
        """Negotiate the best schema version based on client capabilities.

        Args:
            schema_id: Schema identifier
            client_supported_versions: Versions supported by the client

        Returns:
            Best compatible version or None
        """
        schema_versions = self.schemas.get(schema_id, [])
        if not schema_versions:
            return None

        # Get active versions sorted by preference (newest first)
        active_versions = sorted([sv.version for sv in schema_versions if sv.is_active], reverse=True)

        # Find the highest version supported by both server and client
        for version in active_versions:
            if version in client_supported_versions:
                return version

        return None

    def list_schemas(self) -> dict[str, list[int]]:
        """List all registered schemas and their versions.

        Returns:
            Dictionary mapping schema IDs to lists of versions
        """
        return {
            schema_id: [sv.version for sv in versions if sv.is_active] for schema_id, versions in self.schemas.items()
        }

    def _save_to_disk(self) -> None:
        """Save registry state to disk."""
        if not self.storage_path:
            return

        registry_data = {"schemas": {}, "migrations": {}}

        # Save schemas
        for schema_id, versions in self.schemas.items():
            registry_data["schemas"][schema_id] = [
                {
                    "version": sv.version,
                    "schema": sv.schema,
                    "created_at": sv.created_at,
                    "description": sv.description,
                    "is_active": sv.is_active,
                    "compatibility_rules": sv.compatibility_rules,
                }
                for sv in versions
            ]

        # Save migrations (simplified - actual migration functions can't be serialized)
        for schema_id, registry in self.migration_registries.items():
            registry_data["migrations"][schema_id] = list(registry.migrations.keys())

        with open(self.storage_path / "schema_registry.json", "w") as f:
            json.dump(registry_data, f, indent=2)

    def _load_from_disk(self) -> None:
        """Load registry state from disk."""
        if not self.storage_path:
            return

        registry_file = self.storage_path / "schema_registry.json"
        if not registry_file.exists():
            return

        try:
            with open(registry_file) as f:
                registry_data = json.load(f)

            # Load schemas
            for schema_id, versions_data in registry_data.get("schemas", {}).items():
                self.schemas[schema_id] = []
                for version_data in versions_data:
                    schema_version = SchemaVersion(
                        schema_id=schema_id,
                        version=version_data["version"],
                        schema=version_data["schema"],
                        created_at=version_data["created_at"],
                        description=version_data["description"],
                        is_active=version_data["is_active"],
                        compatibility_rules=version_data.get("compatibility_rules"),
                    )
                    self.schemas[schema_id].append(schema_version)

        except Exception as e:
            logger.warning(f"Failed to load schema registry from disk: {e}")


class IngestionPolicy:
    """Policy engine for data ingestion with schema validation and evolution."""

    def __init__(self, schema_registry: SchemaRegistry):
        self.schema_registry = schema_registry
        self.policies: dict[str, dict[str, Any]] = {}

    def set_policy(self, schema_id: str, policy: dict[str, Any]) -> None:
        """Set ingestion policy for a schema.

        Args:
            schema_id: Schema identifier
            policy: Policy configuration
        """
        self.policies[schema_id] = policy

    def validate_ingestion(
        self, schema_id: str, data: dict[str, Any], client_version: int | None = None
    ) -> ValidationResult:
        """Validate data for ingestion with policy enforcement.

        Args:
            schema_id: Schema identifier
            data: Data to validate
            client_version: Client's schema version

        Returns:
            ValidationResult with validation status
        """
        # Get policy for this schema
        policy = self.policies.get(schema_id, {})

        # Check if schema allows ingestion
        if not policy.get("allow_ingestion", True):
            return ValidationResult(
                valid=False, errors=["Ingestion not allowed for this schema"], schema_id=schema_id, schema_version=0
            )

        # Negotiate version if client version provided
        if client_version is not None:
            negotiated_version = self.schema_registry.negotiate_version(schema_id, [client_version])
            if negotiated_version is None:
                return ValidationResult(
                    valid=False,
                    errors=[f"Schema version {client_version} not supported"],
                    schema_id=schema_id,
                    schema_version=0,
                    data_version=client_version,
                )
        else:
            negotiated_version = None

        # Validate against schema
        result = self.schema_registry.validate_data(schema_id, data, negotiated_version)

        # Apply additional policy rules
        if result.valid:
            # Check size limits
            max_size = policy.get("max_size_bytes")
            if max_size and len(json.dumps(data).encode()) > max_size:
                return ValidationResult(
                    valid=False,
                    errors=[f"Data size exceeds limit of {max_size} bytes"],
                    schema_id=schema_id,
                    schema_version=result.schema_version,
                    data_version=result.data_version,
                )

            # Check required fields
            required_fields = policy.get("required_fields", [])
            for field in required_fields:
                if field not in data:
                    return ValidationResult(
                        valid=False,
                        errors=[f"Required field '{field}' is missing"],
                        schema_id=schema_id,
                        schema_version=result.schema_version,
                        data_version=result.data_version,
                    )

        return result
