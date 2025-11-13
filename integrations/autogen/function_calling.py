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
ATP AutoGen Function Calling Integration
This module provides function calling capabilities for ATP AutoGen agents.
"""

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FunctionSchema:
    """Schema for a function that can be called by agents."""

    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str]
    function: Callable
    async_function: bool = False


class ATPFunctionRegistry:
    """Registry for functions that can be called by ATP AutoGen agents."""

    def __init__(self):
        self._functions: dict[str, FunctionSchema] = {}
        self._execution_history: list[dict[str, Any]] = []

    def register_function(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        parameter_descriptions: dict[str, str] | None = None,
    ) -> FunctionSchema:
        """
        Register a function for agent use.

        Args:
            func: Function to register
            name: Function name (defaults to func.__name__)
            description: Function description
            parameter_descriptions: Descriptions for parameters

        Returns:
            FunctionSchema for the registered function
        """
        func_name = name or func.__name__
        func_description = description or func.__doc__ or f"Function {func_name}"

        # Extract function signature
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        # Build parameter schema
        parameters = {"type": "object", "properties": {}, "required": []}

        for param_name, param in sig.parameters.items():
            param_type = self._python_type_to_json_schema(
                type_hints.get(param_name, type(param.default) if param.default != param.empty else str)
            )

            param_schema = {"type": param_type}

            # Add description if provided
            if parameter_descriptions and param_name in parameter_descriptions:
                param_schema["description"] = parameter_descriptions[param_name]

            # Add default value if present
            if param.default != param.empty:
                param_schema["default"] = param.default
            else:
                parameters["required"].append(param_name)

            parameters["properties"][param_name] = param_schema

        # Check if function is async
        is_async = asyncio.iscoroutinefunction(func)

        # Create schema
        schema = FunctionSchema(
            name=func_name,
            description=func_description,
            parameters=parameters,
            required=parameters["required"],
            function=func,
            async_function=is_async,
        )

        self._functions[func_name] = schema
        logger.info(f"Registered function: {func_name}")

        return schema

    def _python_type_to_json_schema(self, python_type: type) -> str:
        """Convert Python type to JSON schema type."""
        type_mapping = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}

        return type_mapping.get(python_type, "string")

    def unregister_function(self, name: str):
        """Unregister a function."""
        if name in self._functions:
            del self._functions[name]
            logger.info(f"Unregistered function: {name}")

    def get_function_schema(self, name: str) -> FunctionSchema | None:
        """Get schema for a specific function."""
        return self._functions.get(name)

    def list_functions(self) -> list[str]:
        """List all registered function names."""
        return list(self._functions.keys())

    def get_all_schemas(self) -> dict[str, dict[str, Any]]:
        """Get all function schemas in OpenAI format."""
        schemas = {}
        for name, schema in self._functions.items():
            schemas[name] = {"name": schema.name, "description": schema.description, "parameters": schema.parameters}
        return schemas

    async def call_function(
        self, name: str, arguments: dict[str, Any], execution_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Call a registered function.

        Args:
            name: Function name
            arguments: Function arguments
            execution_context: Additional context for execution

        Returns:
            Function execution result
        """
        if name not in self._functions:
            raise ValueError(f"Function '{name}' not found in registry")

        schema = self._functions[name]
        func = schema.function

        try:
            # Validate arguments against schema
            self._validate_arguments(schema, arguments)

            # Execute function
            if schema.async_function:
                result = await func(**arguments)
            else:
                result = func(**arguments)

            # Record execution
            execution_record = {
                "function_name": name,
                "arguments": arguments,
                "result": result,
                "success": True,
                "error": None,
                "context": execution_context,
            }

            self._execution_history.append(execution_record)

            return {"success": True, "result": result, "function_name": name}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Function {name} execution failed: {error_msg}")

            # Record failed execution
            execution_record = {
                "function_name": name,
                "arguments": arguments,
                "result": None,
                "success": False,
                "error": error_msg,
                "context": execution_context,
            }

            self._execution_history.append(execution_record)

            return {"success": False, "error": error_msg, "function_name": name}

    def _validate_arguments(self, schema: FunctionSchema, arguments: dict[str, Any]):
        """Validate function arguments against schema."""
        # Check required parameters
        for required_param in schema.required:
            if required_param not in arguments:
                raise ValueError(f"Missing required parameter: {required_param}")

        # Basic type validation (simplified)
        properties = schema.parameters.get("properties", {})
        for arg_name, arg_value in arguments.items():
            if arg_name in properties:
                expected_type = properties[arg_name].get("type")
                if expected_type == "string" and not isinstance(arg_value, str):
                    raise ValueError(f"Parameter {arg_name} must be a string")
                elif expected_type == "integer" and not isinstance(arg_value, int):
                    raise ValueError(f"Parameter {arg_name} must be an integer")
                elif expected_type == "number" and not isinstance(arg_value, (int, float)):
                    raise ValueError(f"Parameter {arg_name} must be a number")
                elif expected_type == "boolean" and not isinstance(arg_value, bool):
                    raise ValueError(f"Parameter {arg_name} must be a boolean")

    def get_execution_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get function execution history."""
        history = self._execution_history.copy()
        if limit:
            history = history[-limit:]
        return history

    def clear_execution_history(self):
        """Clear execution history."""
        self._execution_history = []
        logger.info("Cleared function execution history")

    def get_execution_stats(self) -> dict[str, Any]:
        """Get function execution statistics."""
        if not self._execution_history:
            return {"total_executions": 0}

        # Count executions by function
        function_counts = {}
        success_counts = {}

        for execution in self._execution_history:
            func_name = execution["function_name"]
            success = execution["success"]

            function_counts[func_name] = function_counts.get(func_name, 0) + 1
            success_counts[func_name] = success_counts.get(func_name, 0) + (1 if success else 0)

        # Calculate success rates
        success_rates = {}
        for func_name in function_counts:
            success_rates[func_name] = success_counts[func_name] / function_counts[func_name]

        return {
            "total_executions": len(self._execution_history),
            "function_counts": function_counts,
            "success_rates": success_rates,
            "registered_functions": len(self._functions),
        }


# Decorator for easy function registration
def atp_function(
    registry: ATPFunctionRegistry,
    name: str | None = None,
    description: str | None = None,
    parameter_descriptions: dict[str, str] | None = None,
):
    """
    Decorator to register a function with ATP function registry.

    Args:
        registry: ATPFunctionRegistry instance
        name: Function name
        description: Function description
        parameter_descriptions: Parameter descriptions
    """

    def decorator(func: Callable) -> Callable:
        registry.register_function(
            func=func, name=name, description=description, parameter_descriptions=parameter_descriptions
        )
        return func

    return decorator


# Built-in utility functions
class BuiltinFunctions:
    """Built-in utility functions for ATP AutoGen agents."""

    @staticmethod
    def create_registry_with_builtins() -> ATPFunctionRegistry:
        """Create a function registry with built-in utility functions."""
        registry = ATPFunctionRegistry()

        # Math functions
        @atp_function(
            registry,
            description="Calculate the sum of a list of numbers",
            parameter_descriptions={"numbers": "List of numbers to sum"},
        )
        def calculate_sum(numbers: list[float]) -> float:
            """Calculate the sum of numbers."""
            return sum(numbers)

        @atp_function(
            registry,
            description="Calculate the average of a list of numbers",
            parameter_descriptions={"numbers": "List of numbers to average"},
        )
        def calculate_average(numbers: list[float]) -> float:
            """Calculate the average of numbers."""
            return sum(numbers) / len(numbers) if numbers else 0

        # String functions
        @atp_function(
            registry,
            description="Count the number of words in a text",
            parameter_descriptions={"text": "Text to count words in"},
        )
        def count_words(text: str) -> int:
            """Count words in text."""
            return len(text.split())

        @atp_function(
            registry, description="Convert text to uppercase", parameter_descriptions={"text": "Text to convert"}
        )
        def to_uppercase(text: str) -> str:
            """Convert text to uppercase."""
            return text.upper()

        @atp_function(
            registry, description="Convert text to lowercase", parameter_descriptions={"text": "Text to convert"}
        )
        def to_lowercase(text: str) -> str:
            """Convert text to lowercase."""
            return text.lower()

        # File functions
        @atp_function(
            registry,
            description="Read content from a file",
            parameter_descriptions={"filename": "Name of the file to read"},
        )
        def read_file(filename: str) -> str:
            """Read file content."""
            try:
                with open(filename, encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {e}"

        @atp_function(
            registry,
            description="Write content to a file",
            parameter_descriptions={"filename": "Name of the file to write", "content": "Content to write to the file"},
        )
        def write_file(filename: str, content: str) -> str:
            """Write content to file."""
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to {filename}"
            except Exception as e:
                return f"Error writing file: {e}"

        # Time functions
        @atp_function(
            registry,
            description="Get current timestamp",
        )
        def get_current_timestamp() -> float:
            """Get current timestamp."""
            import time

            return time.time()

        @atp_function(
            registry,
            description="Format timestamp as human-readable date",
            parameter_descriptions={"timestamp": "Unix timestamp to format"},
        )
        def format_timestamp(timestamp: float) -> str:
            """Format timestamp as readable date."""
            import datetime

            return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        return registry


# Integration with AutoGen agents
class FunctionCallingMixin:
    """Mixin to add function calling capabilities to AutoGen agents."""

    def __init__(self, function_registry: ATPFunctionRegistry | None = None, **kwargs):
        super().__init__(**kwargs)
        self.function_registry = function_registry or ATPFunctionRegistry()

    def register_function(self, func: Callable, **kwargs) -> FunctionSchema:
        """Register a function for this agent."""
        return self.function_registry.register_function(func, **kwargs)

    async def call_function(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a registered function."""
        return await self.function_registry.call_function(name, arguments)

    def get_available_functions(self) -> list[str]:
        """Get list of available functions."""
        return self.function_registry.list_functions()

    def get_function_schemas(self) -> dict[str, dict[str, Any]]:
        """Get all function schemas."""
        return self.function_registry.get_all_schemas()


# Factory functions
def create_function_registry() -> ATPFunctionRegistry:
    """Create a new function registry."""
    return ATPFunctionRegistry()


def create_builtin_function_registry() -> ATPFunctionRegistry:
    """Create a function registry with built-in functions."""
    return BuiltinFunctions.create_registry_with_builtins()
