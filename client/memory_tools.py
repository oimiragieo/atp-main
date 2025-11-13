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

"""Memory/Context Exposure via Tools (GAP-134).

This module implements MCP tools for exposing memory and context operations,
providing AI agents with access to the ATP memory fabric through the tool interface.
"""

import json
import time
from datetime import datetime
from typing import Any

import httpx

from client.tool_schema_versioning import ToolSchemaVersioning


class PermissionChecker:
    """Simple permission checker for memory operations."""

    def __init__(self, allowed_namespaces: list[str]):
        """Initialize permission checker.

        Args:
            allowed_namespaces: List of allowed namespace patterns (supports wildcards)
        """
        self.allowed_namespaces = allowed_namespaces

    def check_namespace_access(self, namespace: str, operation: str) -> bool:
        """Check if access to namespace is allowed.

        Args:
            namespace: Namespace to check
            operation: Operation type (read/write)

        Returns:
            True if access is allowed
        """
        for pattern in self.allowed_namespaces:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if namespace.startswith(prefix):
                    return True
            elif pattern == namespace:
                return True
        return False


class MemoryGatewayClient:
    """Client for interacting with the Memory Gateway service."""

    def __init__(self, base_url: str, tenant_id: str):
        """Initialize memory gateway client.

        Args:
            base_url: Base URL of the memory gateway
            tenant_id: Tenant ID for requests
        """
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def list_keys(
        self, namespace: str, prefix: str | None = None, limit: int = 50, cursor: str | None = None
    ) -> dict[str, Any]:
        """List keys in a namespace.

        Args:
            namespace: Namespace to list
            prefix: Key prefix filter
            limit: Maximum number of keys to return
            cursor: Pagination cursor

        Returns:
            Dictionary with keys, cursor, and total
        """
        # For this prototype, we'll simulate the memory gateway response
        # In a real implementation, this would make HTTP calls to the gateway

        # Simulate some keys
        all_keys = [f"{prefix or 'key'}_{i}" for i in range(1, 101)]

        # Apply prefix filter
        if prefix:
            all_keys = [k for k in all_keys if k.startswith(prefix)]

        # Apply pagination
        start_idx = 0
        if cursor:
            try:
                start_idx = int(cursor)
            except ValueError:
                start_idx = 0

        end_idx = start_idx + limit
        keys_page = all_keys[start_idx:end_idx]

        next_cursor = str(end_idx) if end_idx < len(all_keys) else None

        return {"keys": keys_page, "cursor": next_cursor, "total": len(all_keys)}

    async def get(self, namespace: str, key: str) -> Any | None:
        """Get a value from memory.

        Args:
            namespace: Namespace
            key: Key to retrieve

        Returns:
            Value if found, None otherwise
        """
        # Simulate memory retrieval
        if key.startswith("session_"):
            return {"session_id": key, "start_time": datetime.now().isoformat(), "status": "active"}
        elif key.startswith("agent_"):
            return {
                "agent_id": key,
                "capabilities": ["memory", "tools", "reasoning"],
                "last_active": datetime.now().isoformat(),
            }
        return None

    async def put(self, namespace: str, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        """Store a value in memory.

        Args:
            namespace: Namespace
            key: Key to store
            value: Value to store
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful
        """
        # Simulate successful storage
        print(f"Storing in {namespace}/{key}: {value}")
        return True


class MemoryTools:
    """MCP tools for memory and context operations."""

    def __init__(self, memory_gateway_url: str, tenant_id: str, allowed_namespaces: list[str] | None = None):
        """Initialize memory tools.

        Args:
            memory_gateway_url: URL of the memory gateway service
            tenant_id: Tenant ID for operations
            allowed_namespaces: List of allowed namespace patterns
        """
        self.gateway_url = memory_gateway_url
        self.tenant_id = tenant_id
        self.permissions = PermissionChecker(allowed_namespaces or ["session.*", "agent.*", "public.*"])
        self.schema_versioning = ToolSchemaVersioning()

        # Session context (would come from actual session management)
        self.session_context = {
            "session_id": f"session_{int(time.time())}",
            "agent_id": f"agent_{int(time.time()) % 1000}",
            "task_id": f"task_{int(time.time()) % 100}",
            "start_time": datetime.now().isoformat(),
            "memory_usage": {"tokens_used": 0, "usd_spent": 0.0},
            "tool_history": [],
        }

    def _filter_pii_keys(self, keys: list[str]) -> list[str]:
        """Filter out keys that might contain PII.

        Args:
            keys: List of keys to filter

        Returns:
            Filtered list of keys
        """
        pii_patterns = ["email", "phone", "ssn", "password", "secret", "token"]
        filtered = []

        for key in keys:
            if any(pattern in key.lower() for pattern in pii_patterns):
                # Replace PII-containing keys with redacted version
                filtered.append(f"[REDACTED]_{hash(key) % 1000}")
            else:
                filtered.append(key)

        return filtered

    def _validate_memory_data(self, data: Any) -> None:
        """Validate memory data for storage.

        Args:
            data: Data to validate

        Raises:
            ValueError: If data is invalid
        """
        # Basic validation - check JSON serializability
        try:
            json.dumps(data)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Data is not JSON serializable: {e}") from e

        # Check size (simulate gateway limits)
        data_str = json.dumps(data)
        if len(data_str.encode("utf-8")) > 1024 * 1024:  # 1MB limit
            raise ValueError("Data too large (max 1MB)")

    async def list_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        """List memory objects in a namespace.

        Args:
            args: Tool arguments

        Returns:
            Tool response
        """
        namespace = args["namespace"]
        prefix = args.get("prefix")
        limit = args.get("limit", 50)
        cursor = args.get("cursor")

        # Check permissions
        if not self.permissions.check_namespace_access(namespace, "read"):
            raise PermissionError(f"Access denied to namespace '{namespace}'")

        # Use memory gateway client
        async with MemoryGatewayClient(self.gateway_url, self.tenant_id) as client:
            response = await client.list_keys(namespace=namespace, prefix=prefix, limit=limit, cursor=cursor)

        # Apply PII filtering
        filtered_keys = self._filter_pii_keys(response["keys"])

        return {
            "keys": filtered_keys,
            "cursor": response.get("cursor"),
            "total": response.get("total", len(filtered_keys)),
        }

    async def get_context(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get contextual information for the current session/agent.

        Args:
            args: Tool arguments

        Returns:
            Context information
        """
        context_type = args.get("context_type", "all")
        include_history = args.get("include_history", False)

        context = {}

        if context_type in ["session", "all"]:
            context.update(
                {
                    "session_id": self.session_context["session_id"],
                    "start_time": self.session_context["start_time"],
                    "memory_usage": self.session_context["memory_usage"],
                }
            )

        if context_type in ["agent", "all"]:
            context.update({"agent_id": self.session_context["agent_id"]})

        if context_type in ["task", "all"]:
            context.update({"task_id": self.session_context["task_id"]})

        if include_history:
            context["tool_history"] = self.session_context["tool_history"]

        return context

    async def put_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        """Store data in memory.

        Args:
            args: Tool arguments

        Returns:
            Success confirmation
        """
        namespace = args["namespace"]
        key = args["key"]
        value = args["value"]
        ttl_seconds = args.get("ttl_seconds")

        # Validate data
        self._validate_memory_data(value)

        # Check permissions
        if not self.permissions.check_namespace_access(namespace, "write"):
            raise PermissionError(f"Write access denied to namespace '{namespace}'")

        # Store using memory gateway
        async with MemoryGatewayClient(self.gateway_url, self.tenant_id) as client:
            success = await client.put(namespace=namespace, key=key, value=value, ttl_seconds=ttl_seconds)

        if success:
            # Update tool history
            self.session_context["tool_history"].append(
                {"tool_name": "putMemory", "timestamp": datetime.now().isoformat(), "success": True}
            )

        return {"success": success}

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get MCP tool definitions for memory operations.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "listMemory",
                "description": "List memory objects in a namespace with optional filtering",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string", "description": "Memory namespace to list"},
                        "prefix": {"type": "string", "description": "Key prefix filter (optional)"},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 50,
                            "description": "Maximum number of keys to return",
                        },
                        "cursor": {"type": "string", "description": "Pagination cursor (optional)"},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "getContext",
                "description": "Get contextual information for the current session/agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "context_type": {
                            "type": "string",
                            "enum": ["session", "agent", "task", "all"],
                            "default": "all",
                            "description": "Type of context to retrieve",
                        },
                        "include_history": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include historical context",
                        },
                    },
                },
            },
            {
                "name": "putMemory",
                "description": "Store data in memory with validation and audit",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string", "description": "Memory namespace"},
                        "key": {"type": "string", "description": "Memory key"},
                        "value": {"description": "Value to store (any JSON-serializable data)"},
                        "ttl_seconds": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "Time-to-live in seconds (optional)",
                        },
                    },
                    "required": ["namespace", "key", "value"],
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a memory tool.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        if tool_name == "listMemory":
            return await self.list_memory(args)
        elif tool_name == "getContext":
            return await self.get_context(args)
        elif tool_name == "putMemory":
            return await self.put_memory(args)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")


# Global instance for easy access
memory_tools = MemoryTools(memory_gateway_url="http://localhost:8000", tenant_id="default_tenant")
