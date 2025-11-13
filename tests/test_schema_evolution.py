#!/usr/bin/env python3
"""GAP-304: Comprehensive tests for schema evolution and backward compatibility.

Tests schema registry, version negotiation, migration, and ingestion policies.
"""

from unittest.mock import patch

import pytest

from tools.schema_registry import IngestionPolicy, SchemaRegistry

# from tools.schema_metrics import SchemaMetricsCollector  # Temporarily disabled


class TestSchemaRegistry:
    """Test cases for SchemaRegistry functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = SchemaRegistry()

    def test_register_schema(self):
        """Test schema registration."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }

        version = self.registry.register_schema("user", schema, "User schema v1")
        assert version == 1

        # Register another version
        schema_v2 = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}, "email": {"type": "string"}},
            "required": ["name", "email"],
        }

        version2 = self.registry.register_schema("user", schema_v2, "User schema v2")
        assert version2 == 2

    def test_get_schema(self):
        """Test schema retrieval."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Register schema
        self.registry.register_schema("test", schema)

        # Get latest version
        latest = self.registry.get_schema("test")
        assert latest is not None
        assert latest.version == 1
        assert latest.schema == schema

        # Get specific version
        specific = self.registry.get_schema("test", 1)
        assert specific is not None
        assert specific.version == 1

        # Get non-existent schema
        nonexistent = self.registry.get_schema("nonexistent")
        assert nonexistent is None

    @patch("tools.schema_registry.JSONSCHEMA_AVAILABLE", True)
    def test_validate_data_valid(self):
        """Test valid data validation."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer", "minimum": 0}},
            "required": ["name"],
        }

        self.registry.register_schema("person", schema)
        valid_data = {"name": "John", "age": 30}

        result = self.registry.validate_data("person", valid_data)
        assert result.valid
        assert result.errors == []
        assert result.schema_id == "person"
        assert result.schema_version == 1

    @patch("tools.schema_registry.JSONSCHEMA_AVAILABLE", True)
    def test_validate_data_invalid(self):
        """Test invalid data validation."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

        self.registry.register_schema("person", schema)
        invalid_data = {"age": 30}  # Missing required name

        result = self.registry.validate_data("person", invalid_data)
        assert not result.valid
        assert len(result.errors) > 0
        assert "name" in str(result.errors[0]).lower()

    def test_negotiate_version(self):
        """Test version negotiation."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Register multiple versions
        self.registry.register_schema("test", schema)
        self.registry.register_schema("test", schema)

        # Client supports version 1
        negotiated = self.registry.negotiate_version("test", [1])
        assert negotiated == 1

        # Client supports version 2
        negotiated = self.registry.negotiate_version("test", [2])
        assert negotiated == 2

        # Client supports both, should get highest
        negotiated = self.registry.negotiate_version("test", [1, 2])
        assert negotiated == 2

        # Client supports unsupported version
        negotiated = self.registry.negotiate_version("test", [99])
        assert negotiated is None

    def test_migration_registration_and_execution(self):
        """Test migration registration and execution."""
        # Register initial schema
        schema_v1 = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        self.registry.register_schema("user", schema_v1)

        # Register migration function
        def migrate_v1_to_v2(data):
            data["version"] = 2
            return data

        self.registry.register_migration("user", 1, 2, migrate_v1_to_v2)

        # Test migration
        old_data = {"name": "John"}
        migrated_data = self.registry.migrate_data("user", old_data, 1, 2)
        assert migrated_data["name"] == "John"
        assert migrated_data["version"] == 2

    def test_list_schemas(self):
        """Test schema listing."""
        # Register some schemas
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        self.registry.register_schema("user", schema)
        self.registry.register_schema("user", schema)  # v2
        self.registry.register_schema("product", schema)

        schemas = self.registry.list_schemas()
        assert "user" in schemas
        assert "product" in schemas
        assert schemas["user"] == [1, 2]
        assert schemas["product"] == [1]


class TestIngestionPolicy:
    """Test cases for IngestionPolicy functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = SchemaRegistry()
        self.policy = IngestionPolicy(self.registry)

    @patch("tools.schema_registry.JSONSCHEMA_AVAILABLE", True)
    def test_policy_validation_success(self):
        """Test successful policy validation."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

        self.registry.register_schema("test", schema)
        self.policy.set_policy("test", {"allow_ingestion": True, "max_size_bytes": 1000, "required_fields": ["name"]})

        valid_data = {"name": "Test"}
        result = self.policy.validate_ingestion("test", valid_data)

        assert result.valid
        assert result.errors == []

    @patch("tools.schema_registry.JSONSCHEMA_AVAILABLE", True)
    def test_policy_validation_size_limit(self):
        """Test policy validation with size limit."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        self.registry.register_schema("test", schema)
        self.policy.set_policy(
            "test",
            {
                "allow_ingestion": True,
                "max_size_bytes": 50,  # Very small limit
            },
        )

        # Create data that exceeds size limit
        large_data = {"name": "This is a very long name that will exceed the size limit"}
        result = self.policy.validate_ingestion("test", large_data)

        assert not result.valid
        assert any("size" in error.lower() for error in result.errors)

    @patch("tools.schema_registry.JSONSCHEMA_AVAILABLE", True)
    def test_policy_validation_required_fields(self):
        """Test policy validation with required fields."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}}

        self.registry.register_schema("test", schema)
        self.policy.set_policy("test", {"allow_ingestion": True, "required_fields": ["name", "age"]})

        # Missing required field
        incomplete_data = {"name": "John"}  # Missing age
        result = self.policy.validate_ingestion("test", incomplete_data)

        assert not result.valid
        assert any("age" in error.lower() for error in result.errors)

    def test_policy_ingestion_disabled(self):
        """Test policy with ingestion disabled."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        self.registry.register_schema("test", schema)
        self.policy.set_policy("test", {"allow_ingestion": False})

        data = {"name": "Test"}
        result = self.policy.validate_ingestion("test", data)

        assert not result.valid
        assert any("not allowed" in error.lower() for error in result.errors)

    def test_version_negotiation_in_policy(self):
        """Test version negotiation in policy validation."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        self.registry.register_schema("test", schema)
        self.policy.set_policy("test", {"allow_ingestion": True})

        data = {"name": "Test"}

        # Client supports version 1 (should work)
        result = self.policy.validate_ingestion("test", data, client_version=1)
        assert result.valid

        # Client supports unsupported version
        result = self.policy.validate_ingestion("test", data, client_version=99)
        assert not result.valid
        assert any("not supported" in error.lower() for error in result.errors)


class TestSchemaEvolution:
    """Test cases for schema evolution scenarios."""

    def setup_method(self):
        """Setup test fixtures."""
        self.registry = SchemaRegistry()

    def test_backward_compatible_addition(self):
        """Test backward compatible schema evolution (adding optional fields)."""
        # Version 1: Basic user
        schema_v1 = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }

        # Version 2: Add optional email field
        schema_v2 = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "email": {"type": "string"},  # Optional field
            },
            "required": ["name"],
        }

        self.registry.register_schema("user", schema_v1)
        self.registry.register_schema("user", schema_v2)

        # Data conforming to v1 should still validate against v2
        v1_data = {"name": "John", "age": 30}
        result = self.registry.validate_data("user", v1_data)
        assert result.valid

        # Data with new field should also validate
        v2_data = {"name": "Jane", "age": 25, "email": "jane@example.com"}
        result = self.registry.validate_data("user", v2_data)
        assert result.valid

    def test_non_backward_compatible_change(self):
        """Test non-backward compatible schema evolution."""
        # Version 1: Age as integer
        schema_v1 = {"type": "object", "properties": {"age": {"type": "integer"}}, "required": ["age"]}

        # Version 2: Age as string (breaking change)
        schema_v2 = {"type": "object", "properties": {"age": {"type": "string"}}, "required": ["age"]}

        self.registry.register_schema("user", schema_v1)
        self.registry.register_schema("user", schema_v2)

        # Old data should fail validation against new schema
        old_data = {"age": 30}
        result = self.registry.validate_data("user", old_data)
        assert not result.valid  # Should fail because 30 is not a string

    def test_migration_with_data_transformation(self):
        """Test migration with actual data transformation."""
        # Register schemas
        schema_v1 = {"type": "object", "properties": {"birth_year": {"type": "integer"}}, "required": ["birth_year"]}

        schema_v2 = {"type": "object", "properties": {"age": {"type": "integer"}}, "required": ["age"]}

        self.registry.register_schema("person", schema_v1)
        self.registry.register_schema("person", schema_v2)

        # Register migration function
        def migrate_birth_year_to_age(data):
            current_year = 2024  # Assume current year
            data["age"] = current_year - data["birth_year"]
            del data["birth_year"]
            return data

        self.registry.register_migration("person", 1, 2, migrate_birth_year_to_age)

        # Test migration
        old_data = {"birth_year": 1990}
        migrated_data = self.registry.migrate_data("person", old_data, 1, 2)

        assert "birth_year" not in migrated_data
        assert migrated_data["age"] == 34  # 2024 - 1990


# class TestSchemaMetrics:
#     """Test cases for schema metrics collection."""

#     def setup_method(self):
#         """Setup test fixtures."""
#         self.metrics = SchemaMetricsCollector()

#     def test_validation_metrics(self):
#         """Test validation metrics recording."""
#         # Record successful validation
#         self.metrics.record_validation("test_schema", 1, True, 0.05)
#         # Record failed validation
#         self.metrics.record_validation("test_schema", 1, False, 0.03)

#         # Note: In a real scenario, we'd check the actual metric values
#         # but with mock prometheus, we just ensure no exceptions

#     def test_rejection_metrics(self):
#         """Test rejection metrics recording."""
#         self.metrics.record_rejection("test_schema", "validation_error", 1)
#         self.metrics.record_rejection("test_schema", "policy_violation", 2)

#     def test_migration_metrics(self):
#         """Test migration metrics recording."""
#         self.metrics.record_migration("test_schema", 1, 2, True, 0.1)
#         self.metrics.record_migration("test_schema", 2, 3, False, 0.05)

#     def test_ingestion_metrics(self):
#         """Test ingestion metrics recording."""
#         self.metrics.record_ingestion("test_schema", True, False, 0.2)
#         self.metrics.record_ingestion("test_schema", False, True, 0.1)

#     def test_version_negotiation_metrics(self):
#         """Test version negotiation metrics recording."""
#         self.metrics.record_version_negotiation("test_schema", True)
#         self.metrics.record_version_negotiation("test_schema", False)


if __name__ == "__main__":
    pytest.main([__file__])
