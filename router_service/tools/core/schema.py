"""Tool schema definitions and validation.

Implements Claude's tool use schema format with JSON Schema validation
and type safety. Supports fine-grained streaming for large parameters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ToolParameterType(str, Enum):
    """Supported parameter types for tool inputs."""

    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """Tool parameter definition following JSON Schema spec."""

    type: ToolParameterType
    description: str = Field(..., min_length=10, description="Detailed description of the parameter")
    enum: list[Any] | None = None
    default: Any | None = None
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    items: dict[str, Any] | None = None  # For array types
    properties: dict[str, ToolParameter] | None = None  # For object types

    class Config:
        use_enum_values = True


class ToolDefinition(BaseModel):
    """Tool definition following Claude's tool use specification.

    Best practices from documentation:
    - Name must match regex: ^[a-zA-Z0-9_-]{1,64}$
    - Description should be 3-4+ sentences explaining:
      * What the tool does
      * When it should be used
      * How it behaves
      * Parameter meanings
      * Limitations
    """

    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=100)
    input_schema: dict[str, Any]
    cache_control: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate tool name matches Claude's requirements."""
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", v):
            msg = f"Tool name must match ^[a-zA-Z0-9_-]{{1,64}}$, got: {v}"
            raise ValueError(msg)
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Ensure description is sufficiently detailed."""
        sentences = v.count(".") + v.count("!") + v.count("?")
        if sentences < 3:
            msg = f"Description should have 3+ sentences, got {sentences}"
            raise ValueError(msg)
        return v

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            **({"cache_control": self.cache_control} if self.cache_control else {}),
        }


@dataclass
class ToolUse:
    """Tool use request from Claude."""

    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class ToolResult:
    """Tool execution result to return to Claude.

    Critical formatting requirement from docs:
    - tool_result blocks must IMMEDIATELY follow tool_use blocks
    - In user message, tool_result must come FIRST in content array
    - All parallel tool results must go in ONE user message
    """

    tool_use_id: str
    content: str | list[dict[str, Any]]
    is_error: bool = False
    type: str = "tool_result"

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic API tool result format."""
        result = {
            "type": self.type,
            "tool_use_id": self.tool_use_id,
        }

        # Handle content
        if isinstance(self.content, str):
            result["content"] = self.content
        else:
            result["content"] = self.content

        if self.is_error:
            result["is_error"] = True

        return result


class ToolChoice(str, Enum):
    """Tool choice options for controlling Claude's behavior."""

    AUTO = "auto"  # Claude decides whether to use tools
    ANY = "any"  # Requires tool use but allows selection
    NONE = "none"  # Prevents tool use entirely


@dataclass
class ToolChoiceConfig:
    """Tool choice configuration."""

    type: ToolChoice
    name: str | None = None  # Specific tool name if type is TOOL
    disable_parallel_use: bool = False


@dataclass
class StreamingToolChunk:
    """Chunk from fine-grained tool streaming.

    With fine-grained streaming, chunks arrive faster and may contain
    partial/invalid JSON. Handle gracefully with fallback wrapping.
    """

    tool_use_id: str
    parameter_name: str
    chunk: str
    is_complete: bool = False
    is_valid_json: bool = True


class ToolValidationError(Exception):
    """Raised when tool input validation fails."""

    pass


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    pass
