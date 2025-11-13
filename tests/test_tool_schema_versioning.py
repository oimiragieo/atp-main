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

"""Tests for tool schema versioning strategy (GAP-133)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from client.tool_schema_versioning import ToolSchemaVersioning


class TestToolSchemaVersioning:
    """Test tool schema versioning functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.versioning = ToolSchemaVersioning(self.temp_dir)

        # Create test schema directories and files
        self._create_test_schemas()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def _create_test_schemas(self):
        """Create test schema files."""
        # Create v1.0 directory
        v1_dir = Path(self.temp_dir) / "v1.0"
        v1_dir.mkdir(parents=True)

        # Create v1.1 directory
        v11_dir = Path(self.temp_dir) / "v1.1"
        v11_dir.mkdir(parents=True)

        # Create v2.0 directory
        v2_dir = Path(self.temp_dir) / "v2.0"
        v2_dir.mkdir(parents=True)

        # Create test schemas
        test_schema_v1 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Test Tool Output v1.0",
            "type": "object",
            "properties": {"tool_call_id": {"type": "string"}, "content": {"type": "string"}},
            "required": ["tool_call_id", "content"],
        }

        test_schema_v11 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Test Tool Output v1.1",
            "type": "object",
            "properties": {
                "tool_call_id": {"type": "string"},
                "content": {"type": "string"},
                "sequence": {"type": "integer"},  # New field
            },
            "required": ["tool_call_id", "content"],
        }

        test_schema_v2 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Test Tool Output v2.0",
            "type": "object",
            "properties": {
                "tool_call_id": {"type": "string"},
                "content": {"type": "string"},
                "sequence": {"type": "integer"},
                "metadata": {"type": "object"},  # Breaking change
            },
            "required": ["tool_call_id", "content", "metadata"],
        }

        # Write schema files
        with open(v1_dir / "toolOutput.json", "w") as f:
            json.dump(test_schema_v1, f)

        with open(v11_dir / "toolOutput.json", "w") as f:
            json.dump(test_schema_v11, f)

        with open(v2_dir / "toolOutput.json", "w") as f:
            json.dump(test_schema_v2, f)

    def test_get_available_versions(self):
        """Test getting available versions for a schema type."""
        versions = self.versioning.get_available_versions("toolOutput")
        expected = ["v2.0", "v1.1", "v1.0"]  # Should be sorted latest first
        assert versions == expected

    def test_get_latest_version(self):
        """Test getting the latest version."""
        latest = self.versioning.get_latest_version("toolOutput")
        assert latest == "v2.0"

    def test_get_latest_version_no_versions(self):
        """Test getting latest version when none exist."""
        latest = self.versioning.get_latest_version("nonexistent")
        assert latest is None

    def test_load_schema_specific_version(self):
        """Test loading a specific schema version."""
        schema = self.versioning.load_schema("toolOutput", "v1.0")
        assert schema["title"] == "Test Tool Output v1.0"
        assert "sequence" not in schema["properties"]

    def test_load_schema_latest_version(self):
        """Test loading latest version when none specified."""
        schema = self.versioning.load_schema("toolOutput")
        assert schema["title"] == "Test Tool Output v2.0"
        assert "metadata" in schema["properties"]

    def test_load_schema_fallback_to_latest(self):
        """Test fallback to latest version when requested version not found."""
        # Create versioning instance with only v1.0 and v2.0 (no v1.5)
        schema = self.versioning.load_schema("toolOutput", "v1.5")
        # Should fallback to v2.0 (latest)
        assert schema["title"] == "Test Tool Output v2.0"

    def test_load_schema_not_found(self):
        """Test error when schema type doesn't exist."""
        with pytest.raises(FileNotFoundError, match="No versions available"):
            self.versioning.load_schema("nonexistent")

    def test_validate_message_valid(self):
        """Test validating a valid message."""
        message = {"tool_call_id": "test-123", "content": "test content"}
        is_valid, error = self.versioning.validate_message(message, "toolOutput", "v1.0")
        assert is_valid
        assert error is None

    def test_validate_message_invalid(self):
        """Test validating an invalid message."""
        message = {
            "tool_call_id": "test-123"
            # Missing required "content" field
        }
        is_valid, error = self.versioning.validate_message(message, "toolOutput", "v1.0")
        assert not is_valid
        assert "content" in error

    def test_negotiate_version_exact_match(self):
        """Test version negotiation with exact match."""
        negotiated = self.versioning.negotiate_version("v1.0", "toolOutput")
        assert negotiated == "v1.0"

    def test_negotiate_version_compatible(self):
        """Test version negotiation with compatible version."""
        negotiated = self.versioning.negotiate_version("v1.2", "toolOutput")
        # Should find v1.1 as compatible
        assert negotiated == "v1.1"

    def test_negotiate_version_fallback(self):
        """Test version negotiation fallback to latest."""
        negotiated = self.versioning.negotiate_version("v3.0", "toolOutput")
        # Should fallback to latest (v2.0)
        assert negotiated == "v2.0"

    def test_negotiate_version_no_versions(self):
        """Test version negotiation when no versions available."""
        with pytest.raises(ValueError, match="No versions available"):
            self.versioning.negotiate_version("v1.0", "nonexistent")

    def test_get_schema_info(self):
        """Test getting schema information."""
        info = self.versioning.get_schema_info("toolOutput", "v1.0")
        assert info["type"] == "toolOutput"
        assert info["version"] == "v1.0"
        assert info["title"] == "Test Tool Output v1.0"
        assert "capabilities" in info

    def test_get_schema_info_latest(self):
        """Test getting schema info for latest version."""
        info = self.versioning.get_schema_info("toolOutput")
        assert info["version"] == "v2.0"

    def test_extract_capabilities(self):
        """Test capability extraction from schema."""
        schema = {
            "properties": {
                "sequence": {"type": "integer"},
                "experiment_id": {"type": "string"},
                "error_code": {"type": "string"},
            }
        }
        capabilities = self.versioning._extract_capabilities(schema)
        assert "streaming" in capabilities
        assert "experiment_metadata" in capabilities
        assert "error_handling" in capabilities

    def test_cache_functionality(self):
        """Test that schemas are cached properly."""
        # First call should load from file
        schema1 = self.versioning.load_schema("toolOutput", "v1.0")

        # Modify the file (simulate external change)
        v1_file = Path(self.temp_dir) / "v1.0" / "toolOutput.json"
        with open(v1_file, "w") as f:
            json.dump({"modified": True}, f)

        # Second call should return cached version
        schema2 = self.versioning.load_schema("toolOutput", "v1.0")
        assert schema1 == schema2
        assert "modified" not in schema2

    @patch("client.tool_schema_versioning.jsonschema.validate")
    def test_validate_message_jsonschema_error(self, mock_validate):
        """Test handling of JSON schema validation errors."""
        mock_validate.side_effect = Exception("Schema validation failed")

        message = {"test": "data"}
        is_valid, error = self.versioning.validate_message(message, "toolOutput")

        assert not is_valid
        assert "Schema validation failed" in error
