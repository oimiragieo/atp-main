"""Tests for MCP JSON Schema validation (GAP-131)."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest


class SchemaValidator:
    """Helper class for validating messages against MCP schemas."""

    def __init__(self, schema_dir: Path):
        self.schema_dir = schema_dir
        self.schemas: dict[str, dict[str, Any]] = {}

        # Load all schemas
        for schema_file in schema_dir.glob("*.json"):
            if schema_file.name != "index.json":
                with open(schema_file) as f:
                    schema = json.load(f)
                    schema_name = schema_file.stem
                    self.schemas[schema_name] = schema

    def validate_message(self, message: dict[str, Any], schema_name: str) -> None:
        """Validate a message against a specific schema."""
        if schema_name not in self.schemas:
            raise ValueError(f"Schema '{schema_name}' not found")

        try:
            jsonschema.validate(message, self.schemas[schema_name])
        except jsonschema.ValidationError as e:
            pytest.fail(f"Message validation failed for schema '{schema_name}': {e.message}")
        except jsonschema.SchemaError as e:
            pytest.fail(f"Schema error in '{schema_name}': {e.message}")


@pytest.fixture
def validator():
    """Fixture to provide a schema validator."""
    schema_dir = Path(__file__).parent.parent / "schemas" / "mcp" / "v1.0"
    return SchemaValidator(schema_dir)


class TestMCPMessageValidation:
    """Test MCP message validation against JSON schemas."""

    def test_tool_output_partial_message(self, validator):
        """Test validation of partial toolOutput message."""
        message = {
            "type": "toolOutput",
            "toolCallId": "test-call-123",
            "content": [{"type": "text", "text": "test content"}],
            "sequence": 1,
            "cumulative_tokens": 5,
            "is_partial": True,
            "dp_metrics_emitted": True,
        }
        validator.validate_message(message, "toolOutput")

    def test_tool_output_final_message(self, validator):
        """Test validation of final toolOutput message."""
        message = {
            "type": "toolOutput",
            "toolCallId": "test-call-123",
            "content": [{"type": "text", "text": "complete response"}],
            "sequence": 3,
            "cumulative_tokens": 12,
            "final": True,
            "dp_metrics_emitted": True,
            "metadata": {"model_used": "gpt-4", "latency_ms": 150, "tokens_used": 12, "cost_usd": 0.0024},
        }
        validator.validate_message(message, "toolOutput")

    def test_tool_output_with_experiment_metadata(self, validator):
        """Test validation of toolOutput message with experiment metadata."""
        message = {
            "type": "toolOutput",
            "toolCallId": "test-call-123",
            "content": [{"type": "text", "text": "response"}],
            "sequence": 1,
            "cumulative_tokens": 5,
            "is_partial": True,
            "dp_metrics_emitted": True,
            "metadata": {"model_used": "claude-3", "latency_ms": 200, "tokens_used": 5, "cost_usd": 0.001},
        }
        validator.validate_message(message, "toolOutput")

    def test_error_message_internal_error(self, validator):
        """Test validation of internal error message."""
        message = {
            "type": "error",
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"traceback": "..."},
            },
            "toolCallId": "test-call-123",
        }
        validator.validate_message(message, "error")

    def test_error_message_idle_timeout(self, validator):
        """Test validation of idle timeout error message."""
        message = {"type": "error", "error": {"code": "IDLE_TIMEOUT", "message": "MCP session idle timeout"}}
        validator.validate_message(message, "error")

    def test_event_message_challenger_selected(self, validator):
        """Test validation of challenger selected event."""
        message = {
            "type": "event",
            "event": "challenger_selected",
            "model": "claude-3-haiku",
            "timestamp": "2025-09-07T20:42:00Z",
            "data": {"confidence": 0.85, "reason": "cost_optimization"},
        }
        validator.validate_message(message, "event")

    def test_event_message_escalate(self, validator):
        """Test validation of escalate event."""
        message = {"type": "event", "event": "escalate", "model": "gpt-4-turbo", "timestamp": "2025-09-07T20:42:00Z"}
        validator.validate_message(message, "event")

    def test_plan_message_with_roles(self, validator):
        """Test validation of plan message with experiment roles."""
        message = {
            "type": "plan",
            "toolCallId": "test-call-123",
            "plan": {
                "description": "Execute user query with A/B testing",
                "steps": [
                    {
                        "step_id": "1",
                        "description": "Analyze user intent",
                        "tool": "intent_analyzer",
                        "estimated_tokens": 50,
                    }
                ],
                "estimated_total_tokens": 150,
                "model_selected": "gpt-4",
            },
            "roles": [
                {"role": "champion", "model": "gpt-4", "confidence": 0.9},
                {"role": "challenger", "model": "claude-3", "confidence": 0.85},
            ],
        }
        validator.validate_message(message, "plan")

    def test_final_message_success(self, validator):
        """Test validation of successful final message."""
        message = {
            "type": "final",
            "toolCallId": "test-call-123",
            "final": True,
            "model_used": "gpt-4",
            "total_tokens": 150,
            "latency_ms": 1200,
            "cost_usd": 0.003,
            "metadata": {"experiment_id": "exp-2025-09-07-001", "winner_model": "gpt-4", "quality_score": 0.92},
        }
        validator.validate_message(message, "final")

    def test_final_message_aborted(self, validator):
        """Test validation of aborted final message."""
        message = {"type": "final", "final": True, "aborted": True, "error": "CANCELLED", "model_used": "gpt-4"}
        validator.validate_message(message, "final")

    def test_heartbeat_message(self, validator):
        """Test validation of heartbeat message."""
        message = {
            "type": "heartbeat",
            "timestamp": "2025-09-07T20:42:00Z",
            "session_id": "session-123",
            "uptime_seconds": 3600,
            "active_connections": 5,
            "memory_usage_mb": 256,
        }
        validator.validate_message(message, "heartbeat")

    def test_list_tools_message(self, validator):
        """Test validation of listTools message."""
        message = {
            "type": "listTools",
            "request_id": "req-123",
            "filter": {"category": "analysis", "tags": ["nlp", "classification"]},
        }
        validator.validate_message(message, "listTools")

    def test_call_tool_message(self, validator):
        """Test validation of callTool message."""
        message = {
            "type": "callTool",
            "toolCallId": "call-123",
            "tool": "text_analyzer",
            "parameters": {"text": "Hello world", "analysis_type": "sentiment"},
            "stream": True,
            "timeout_seconds": 60,
            "priority": "high",
        }
        validator.validate_message(message, "callTool")

    def test_invalid_message_type(self, validator):
        """Test that invalid message types are rejected."""
        message = {"type": "invalid_type", "data": "test"}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(message, validator.schemas["base"])

    def test_missing_required_fields(self, validator):
        """Test that messages missing required fields are rejected."""
        message = {
            "type": "toolOutput",
            "content": [{"type": "text", "text": "test"}],
            # Missing required toolCallId
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(message, validator.schemas["toolOutput"])

    def test_invalid_enum_value(self, validator):
        """Test that invalid enum values are rejected."""
        message = {"type": "error", "error": {"code": "INVALID_CODE", "message": "Test error"}}

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(message, validator.schemas["error"])


class TestSchemaConsistency:
    """Test schema consistency and versioning."""

    def test_all_schemas_loadable(self):
        """Test that all schemas can be loaded without errors."""
        schema_dir = Path(__file__).parent.parent / "schemas" / "mcp" / "v1.0"

        for schema_file in schema_dir.glob("*.json"):
            with open(schema_file) as f:
                schema = json.load(f)
                assert "$schema" in schema
                assert "title" in schema
                assert "description" in schema

    def test_index_schema_references(self):
        """Test that index schema properly references all individual schemas."""
        schema_dir = Path(__file__).parent.parent / "schemas" / "mcp" / "v1.0"
        index_file = schema_dir / "index.json"

        with open(index_file) as f:
            index_schema = json.load(f)

        # Check that all expected schemas are referenced
        expected_schemas = [
            "base",
            "toolOutput",
            "error",
            "event",
            "plan",
            "final",
            "heartbeat",
            "listTools",
            "callTool",
        ]

        for schema_name in expected_schemas:
            assert schema_name in index_schema["properties"]["schemas"]["properties"]
            assert "$ref" in index_schema["properties"]["schemas"]["properties"][schema_name]

    def test_schema_version_consistency(self):
        """Test that all schemas have consistent versioning."""
        schema_dir = Path(__file__).parent.parent / "schemas" / "mcp" / "v1.0"

        for schema_file in schema_dir.glob("*.json"):
            with open(schema_file) as f:
                schema = json.load(f)

            # Check that schema ID contains version
            assert "v1.0" in schema["$id"]

            # Check that index schema declares version 1.0
            if schema_file.name == "index.json":
                assert schema["properties"]["version"]["const"] == "1.0"
