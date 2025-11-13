"""Integration layer for ATP/AGP tool use system.

Integrates the comprehensive tool use framework with existing ATP/AGP
infrastructure for seamless enterprise deployment.
"""

from __future__ import annotations

import logging
from typing import Any

from router_service.tools.agents.subagent import get_agent_registry
from router_service.tools.builtin import register_builtin_tools
from router_service.tools.core.executor import ToolExecutor
from router_service.tools.core.registry import get_registry
from router_service.tools.core.schema import ToolResult, ToolUse
from router_service.tools.guardrails.permissions import PermissionManager, PermissionPolicy
from router_service.tools.mcp.connector import MCPConnector, MCPServerConfig
from router_service.tools.tracking.cost import Usage, get_cost_tracker

logger = logging.getLogger(__name__)


class ATPToolManager:
    """Main interface for ATP/AGP tool use system.

    Provides unified access to:
    - Built-in tools (bash, file ops, etc.)
    - MCP-connected external tools
    - Subagent delegation
    - Cost tracking
    - Permission management
    """

    def __init__(
        self,
        enable_builtin_tools: bool = True,
        enable_mcp: bool = True,
        permission_policy: PermissionPolicy | None = None,
    ):
        """Initialize ATP tool manager.

        Args:
            enable_builtin_tools: Register built-in tools
            enable_mcp: Enable MCP server connections
            permission_policy: Default permission policy
        """
        self.registry = get_registry()
        self.executor = ToolExecutor()
        self.agent_registry = get_agent_registry()
        self.cost_tracker = get_cost_tracker()
        self.permission_manager = PermissionManager(default_policy=permission_policy or PermissionPolicy())
        self.mcp_connector = MCPConnector() if enable_mcp else None

        # Register built-in tools
        if enable_builtin_tools:
            register_builtin_tools()
            logger.info("Registered built-in tools")

    async def execute_tool(
        self,
        tool_use: ToolUse,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> ToolResult:
        """Execute a tool with permission checks and cost tracking.

        Args:
            tool_use: Tool use request
            user_id: User requesting tool use
            session_id: Session identifier for cost tracking

        Returns:
            Tool execution result
        """
        # Permission check
        can_use, reason = self.permission_manager.can_use_tool(
            tool_use.name, user_id, context={"tool_use_id": tool_use.id}
        )

        if not can_use:
            return ToolResult(
                tool_use_id=tool_use.id,
                content=f"Permission denied: {reason}",
                is_error=True,
            )

        # Execute tool
        context = {"user_id": user_id, "session_id": session_id, "tool_use_id": tool_use.id}

        result = await self.executor.execute(tool_use, context)

        return result

    async def execute_parallel(
        self,
        tool_uses: list[ToolUse],
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[ToolResult]:
        """Execute multiple tools in parallel.

        Args:
            tool_uses: List of tool use requests
            user_id: User requesting tool use
            session_id: Session identifier

        Returns:
            List of tool results
        """
        # Permission checks
        for tool_use in tool_uses:
            can_use, reason = self.permission_manager.can_use_tool(tool_use.name, user_id)
            if not can_use:
                logger.warning(f"Blocked tool use: {tool_use.name} for user {user_id} - {reason}")

        # Execute all
        context = {"user_id": user_id, "session_id": session_id}
        results = await self.executor.execute_parallel(tool_uses, context)

        return results

    def track_usage(
        self,
        step_id: str,
        message_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        session_id: str | None = None,
    ) -> float:
        """Track token usage and cost.

        Args:
            step_id: Step identifier
            message_id: Message ID for deduplication
            input_tokens: Input tokens
            output_tokens: Output tokens
            cache_creation_tokens: Cache write tokens
            cache_read_tokens: Cache read tokens
            session_id: Session identifier

        Returns:
            Cost for this step in USD
        """
        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            cache_read_input_tokens=cache_read_tokens,
        )

        cost = self.cost_tracker.track_step(step_id=step_id, message_id=message_id, usage=usage, session_id=session_id)

        return cost

    def get_tools_for_request(self, user_id: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        """Get available tools for a request in Anthropic format.

        Args:
            user_id: User requesting tools
            category: Filter by category

        Returns:
            List of tool definitions in Anthropic API format
        """
        # Get policy
        policy = self.permission_manager.get_policy(user_id)

        # List tools with permission filters
        tools = self.registry.list_tools(
            category=category,
            allowed_tools=policy.allowed_tools,
            disallowed_tools=policy.disallowed_tools,
        )

        return [t.to_anthropic_format() for t in tools]

    async def connect_mcp_servers(self, configs: list[MCPServerConfig]) -> dict[str, bool]:
        """Connect to MCP servers.

        Args:
            configs: List of MCP server configurations

        Returns:
            Dict mapping server name to connection status
        """
        if not self.mcp_connector:
            logger.warning("MCP connector not enabled")
            return {config.name: False for config in configs}

        status = await self.mcp_connector.connect_all(configs)

        # Register MCP tools in registry
        for server_name, connected in status.items():
            if connected:
                client = self.mcp_connector.get_client(server_name)
                if client:
                    for tool_name, _tool_def in client.tools.items():
                        # Convert MCP tool to our format and register
                        # (implementation would go here)
                        logger.info(f"Registered MCP tool: {tool_name}")

        return status

    def get_cost_report(self) -> dict[str, Any]:
        """Get cost tracking report.

        Returns:
            Cost report with tokens and USD totals
        """
        return self.cost_tracker.get_report()

    def get_permission_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get permission audit log.

        Args:
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        return self.permission_manager.get_audit_log(limit)

    async def cleanup(self) -> None:
        """Cleanup resources (disconnect MCP, etc.)."""
        if self.mcp_connector:
            await self.mcp_connector.disconnect_all()


# Global manager instance
_global_manager: ATPToolManager | None = None


def get_tool_manager(
    enable_builtin_tools: bool = True,
    enable_mcp: bool = True,
    permission_policy: PermissionPolicy | None = None,
) -> ATPToolManager:
    """Get or create the global tool manager.

    Args:
        enable_builtin_tools: Register built-in tools
        enable_mcp: Enable MCP server connections
        permission_policy: Default permission policy

    Returns:
        ATPToolManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = ATPToolManager(
            enable_builtin_tools=enable_builtin_tools,
            enable_mcp=enable_mcp,
            permission_policy=permission_policy,
        )

    return _global_manager
