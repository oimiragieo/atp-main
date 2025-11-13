"""Tool registry for managing available tools.

Central registry for all tools (built-in, custom, and MCP-exposed).
Supports tool discovery, validation, and permission management.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from router_service.tools.core.schema import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}
        self._mcp_tools: dict[str, str] = {}  # tool_name -> server_name
        self._categories: dict[str, list[str]] = {}  # category -> tool_names

    def register(
        self,
        tool: ToolDefinition,
        handler: Callable,
        category: str = "custom",
        mcp_server: str | None = None,
    ) -> None:
        """Register a tool with its execution handler.

        Args:
            tool: Tool definition
            handler: Async callable that executes the tool
            category: Tool category (builtin, custom, mcp, etc.)
            mcp_server: MCP server name if tool is from MCP
        """
        if tool.name in self._tools:
            logger.warning(f"Overwriting existing tool: {tool.name}")

        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

        # Track MCP tools
        if mcp_server:
            self._mcp_tools[tool.name] = mcp_server

        # Categorize
        if category not in self._categories:
            self._categories[category] = []
        if tool.name not in self._categories[category]:
            self._categories[category].append(tool.name)

        logger.info(f"Registered tool: {tool.name} (category: {category}, mcp: {mcp_server or 'N/A'})")

    def unregister(self, tool_name: str) -> None:
        """Unregister a tool."""
        if tool_name in self._tools:
            del self._tools[tool_name]
        if tool_name in self._handlers:
            del self._handlers[tool_name]
        if tool_name in self._mcp_tools:
            del self._mcp_tools[tool_name]

        # Remove from categories
        for category, tools in self._categories.items():
            if tool_name in tools:
                tools.remove(tool_name)

        logger.info(f"Unregistered tool: {tool_name}")

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get tool definition by name."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Callable | None:
        """Get tool handler by name."""
        return self._handlers.get(name)

    def list_tools(
        self,
        category: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ) -> list[ToolDefinition]:
        """List available tools with optional filtering.

        Args:
            category: Filter by category (builtin, custom, mcp, etc.)
            allowed_tools: Whitelist of tool names
            disallowed_tools: Blacklist of tool names

        Returns:
            List of tool definitions
        """
        tools = list(self._tools.values())

        # Filter by category
        if category:
            category_tools = set(self._categories.get(category, []))
            tools = [t for t in tools if t.name in category_tools]

        # Apply whitelist
        if allowed_tools:
            allowed_set = set(allowed_tools)
            tools = [t for t in tools if t.name in allowed_set]

        # Apply blacklist
        if disallowed_tools:
            disallowed_set = set(disallowed_tools)
            tools = [t for t in tools if t.name not in disallowed_set]

        return tools

    def to_anthropic_format(
        self,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get tools in Anthropic API format.

        Args:
            allowed_tools: Whitelist of tool names
            disallowed_tools: Blacklist of tool names

        Returns:
            List of tool definitions in Anthropic format
        """
        tools = self.list_tools(allowed_tools=allowed_tools, disallowed_tools=disallowed_tools)
        return [t.to_anthropic_format() for t in tools]

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if tool is from MCP server."""
        return tool_name in self._mcp_tools

    def get_mcp_server(self, tool_name: str) -> str | None:
        """Get MCP server name for a tool."""
        return self._mcp_tools.get(tool_name)

    def get_categories(self) -> list[str]:
        """Get all tool categories."""
        return list(self._categories.keys())

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_tools": len(self._tools),
            "builtin_tools": len(self._categories.get("builtin", [])),
            "custom_tools": len(self._categories.get("custom", [])),
            "mcp_tools": len(self._mcp_tools),
            "categories": len(self._categories),
        }


# Global registry instance
_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _global_registry
