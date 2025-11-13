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

"""Tool Schema Versioning Strategy (GAP-133).

This module implements versioning strategy for MCP tool schemas, providing:
- Semantic versioning with fallback to latest compatible version
- Schema discovery and validation
- Version negotiation between client and server
"""

import json
from pathlib import Path
from typing import Any, Optional

import jsonschema


class ToolSchemaVersioning:
    """Manages MCP tool schema versioning and compatibility."""

    def __init__(self, schemas_dir: str = "schemas/mcp"):
        """Initialize schema versioning manager.

        Args:
            schemas_dir: Directory containing schema versions
        """
        self.schemas_dir = Path(schemas_dir)
        self._schema_cache: dict[str, dict[str, Any]] = {}
        self._version_cache: dict[str, list[str]] = {}

    def get_available_versions(self, schema_type: str) -> list[str]:
        """Get all available versions for a schema type.

        Args:
            schema_type: Type of schema (e.g., 'toolOutput', 'callTool')

        Returns:
            List of available version strings, sorted by semantic version
        """
        if schema_type in self._version_cache:
            return self._version_cache[schema_type]

        versions = []
        if self.schemas_dir.exists():
            for version_dir in self.schemas_dir.iterdir():
                if version_dir.is_dir() and version_dir.name.startswith("v"):
                    schema_file = version_dir / f"{schema_type}.json"
                    if schema_file.exists():
                        versions.append(version_dir.name)

        # Sort by semantic version (simple string sort for now)
        versions.sort(reverse=True)  # Latest first
        self._version_cache[schema_type] = versions
        return versions

    def get_latest_version(self, schema_type: str) -> Optional[str]:
        """Get the latest available version for a schema type.

        Args:
            schema_type: Type of schema

        Returns:
            Latest version string or None if no versions available
        """
        versions = self.get_available_versions(schema_type)
        return versions[0] if versions else None

    def load_schema(self, schema_type: str, version: str | None = None) -> dict[str, Any]:
        """Load a schema with fallback to latest version.

        Args:
            schema_type: Type of schema to load
            version: Specific version to load, or None for latest

        Returns:
            Schema dictionary

        Raises:
            FileNotFoundError: If schema not found and no fallback available
        """
        cache_key = f"{schema_type}:{version or 'latest'}"

        if cache_key in self._schema_cache:
            return self._schema_cache[cache_key]

        # If no version specified, use latest
        if version is None:
            version = self.get_latest_version(schema_type)
            if version is None:
                raise FileNotFoundError(f"No versions available for schema type: {schema_type}")

        # Try requested version first
        schema_path = self.schemas_dir / version / f"{schema_type}.json"
        if not schema_path.exists():
            # Fallback to latest available version
            latest_version = self.get_latest_version(schema_type)
            if latest_version and latest_version != version:
                schema_path = self.schemas_dir / latest_version / f"{schema_type}.json"
                if schema_path.exists():
                    print(f"Warning: Schema {schema_type} version {version} not found, "
                          f"falling back to {latest_version}")
                else:
                    raise FileNotFoundError(f"Schema {schema_type} not found in any version")
            else:
                raise FileNotFoundError(f"Schema {schema_type} version {version} not found")

        with open(schema_path) as f:
            schema = json.load(f)

        self._schema_cache[cache_key] = schema
        return schema

    def validate_message(self, message: dict[str, Any], schema_type: str,
                        version: str | None = None) -> tuple[bool, str | None]:
        """Validate a message against a schema with version fallback.

        Args:
            message: Message to validate
            schema_type: Schema type to validate against
            version: Schema version to use, or None for latest

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            schema = self.load_schema(schema_type, version)
            jsonschema.validate(message, schema)
            return True, None
        except (FileNotFoundError, jsonschema.ValidationError) as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def negotiate_version(self, requested_version: str, schema_type: str) -> str:
        """Negotiate schema version with fallback logic.

        Args:
            requested_version: Version requested by client
            schema_type: Schema type

        Returns:
            Negotiated version string
        """
        available_versions = self.get_available_versions(schema_type)

        if not available_versions:
            raise ValueError(f"No versions available for schema type: {schema_type}")

        # Exact match
        if requested_version in available_versions:
            return requested_version

        # Try major version compatibility (e.g., 1.2 requested, 1.1 available)
        requested_parts = requested_version.lstrip('v').split('.')
        if len(requested_parts) >= 2:
            major_minor = f"{requested_parts[0]}.{requested_parts[1]}"
            for available in available_versions:
                available_parts = available.lstrip('v').split('.')
                if len(available_parts) >= 2 and f"{available_parts[0]}.{available_parts[1]}" == major_minor:
                    return available

        # Try compatible versions (same major version)
        if len(requested_parts) >= 1:
            major = requested_parts[0]
            for available in available_versions:
                available_parts = available.lstrip('v').split('.')
                if available_parts[0] == major:
                    return available

        # Fallback to latest
        return available_versions[0]

    def get_schema_info(self, schema_type: str, version: str | None = None) -> dict[str, Any]:
        """Get schema metadata and capabilities.

        Args:
            schema_type: Schema type
            version: Specific version or None for latest

        Returns:
            Schema information dictionary
        """
        schema = self.load_schema(schema_type, version)
        actual_version = version or self.get_latest_version(schema_type)

        return {
            "type": schema_type,
            "version": actual_version,
            "title": schema.get("title", ""),
            "description": schema.get("description", ""),
            "capabilities": self._extract_capabilities(schema)
        }

    def _extract_capabilities(self, schema: dict[str, Any]) -> list[str]:
        """Extract capability flags from schema.

        Args:
            schema: Schema dictionary

        Returns:
            List of capability strings
        """
        capabilities = []

        # Check for streaming support
        if "properties" in schema:
            props = schema["properties"]
            if "partial" in props or "sequence" in props:
                capabilities.append("streaming")

            # Check for experiment metadata
            if any("experiment" in str(prop).lower() for prop in props.keys()):
                capabilities.append("experiment_metadata")

            # Check for error handling
            if "error" in props or "error_code" in props:
                capabilities.append("error_handling")

        return capabilities


# Global instance for easy access
schema_versioning = ToolSchemaVersioning()
