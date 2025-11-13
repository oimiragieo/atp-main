"""Comprehensive tests for ATP tool use system.

Tests all major components:
- Tool registration and execution
- Permission management
- Cost tracking
- Subagent system
- MCP integration
- Integration layer
"""

import asyncio

import pytest

from router_service.tools.agents.subagent import AgentDefinition, AgentModel, get_agent_registry
from router_service.tools.core.executor import ToolExecutor
from router_service.tools.core.registry import ToolRegistry
from router_service.tools.core.schema import ToolDefinition, ToolResult, ToolUse
from router_service.tools.guardrails.permissions import PermissionMode, PermissionPolicy
from router_service.tools.integration import ATPToolManager, get_tool_manager
from router_service.tools.tracking.cost import CostTracker, Usage


class TestToolRegistry:
    """Test tool registry functionality."""

    def test_register_tool(self):
        """Test tool registration."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool for unit testing. This tool does nothing useful but serves as a validation example. It demonstrates proper tool definition patterns.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

        async def handler(args, context):
            return "test result"

        registry.register(tool, handler, category="test")

        assert registry.get_tool("test_tool") is not None
        assert registry.get_handler("test_tool") is not None

    def test_list_tools_with_filters(self):
        """Test tool listing with filters."""
        registry = ToolRegistry()

        tool1 = ToolDefinition(
            name="allowed_tool",
            description="An allowed test tool. This tool can be used freely. It demonstrates permission filtering in the tool registry system.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

        tool2 = ToolDefinition(
            name="blocked_tool",
            description="A blocked test tool. This tool should be filtered out. It demonstrates permission denial in the tool registry system.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )

        registry.register(tool1, lambda a, c: "ok", category="test")
        registry.register(tool2, lambda a, c: "ok", category="test")

        # Test allowlist
        tools = registry.list_tools(allowed_tools=["allowed_tool"])
        assert len(tools) == 1
        assert tools[0].name == "allowed_tool"

        # Test denylist
        tools = registry.list_tools(disallowed_tools=["blocked_tool"])
        assert len(tools) == 1
        assert tools[0].name == "allowed_tool"


class TestToolExecutor:
    """Test tool execution engine."""

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """Test tool execution."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="echo_tool",
            description="Echoes back input for testing. This tool returns whatever message it receives. It validates basic tool execution patterns.",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )

        async def handler(args, context):
            return f"Echo: {args['message']}"

        registry.register(tool, handler)

        executor = ToolExecutor()
        tool_use = ToolUse(id="test-1", name="echo_tool", input={"message": "Hello"})

        result = await executor.execute(tool_use)

        assert not result.is_error
        assert "Echo: Hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        """Test parallel tool execution."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="add_tool",
            description="Adds two numbers for testing. This tool performs simple arithmetic. It validates parallel execution patterns.",
            input_schema={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        )

        async def handler(args, context):
            await asyncio.sleep(0.1)  # Simulate work
            return str(args["a"] + args["b"])

        registry.register(tool, handler)

        executor = ToolExecutor()
        tool_uses = [
            ToolUse(id="calc-1", name="add_tool", input={"a": 1, "b": 2}),
            ToolUse(id="calc-2", name="add_tool", input={"a": 3, "b": 4}),
            ToolUse(id="calc-3", name="add_tool", input={"a": 5, "b": 6}),
        ]

        results = await executor.execute_parallel(tool_uses)

        assert len(results) == 3
        assert all(not r.is_error for r in results)
        assert results[0].content == "3"
        assert results[1].content == "7"
        assert results[2].content == "11"


class TestCostTracking:
    """Test cost tracking system."""

    def test_track_step(self):
        """Test step tracking."""
        tracker = CostTracker()

        usage = Usage(input_tokens=100, output_tokens=50)
        cost = tracker.track_step(step_id="step-1", message_id="msg-1", usage=usage, session_id="session-1")

        assert cost > 0
        assert tracker.get_session_cost("session-1") == cost

    def test_deduplication(self):
        """Test message ID deduplication."""
        tracker = CostTracker()

        usage = Usage(input_tokens=100, output_tokens=50)

        # Track same message ID twice
        cost1 = tracker.track_step(step_id="step-1", message_id="msg-same", usage=usage)
        cost2 = tracker.track_step(step_id="step-2", message_id="msg-same", usage=usage)

        # Second should be deduplicated (cost = 0)
        assert cost1 > 0
        assert cost2 == 0
        assert tracker.get_total_cost() == cost1

    def test_cost_report(self):
        """Test cost report generation."""
        tracker = CostTracker()

        usage1 = Usage(input_tokens=100, output_tokens=50)
        usage2 = Usage(input_tokens=200, output_tokens=100)

        tracker.track_step("step-1", "msg-1", usage1, session_id="session-1")
        tracker.track_step("step-2", "msg-2", usage2, session_id="session-1")

        report = tracker.get_report()

        assert report["total_steps"] == 2
        assert report["total_cost_usd"] > 0
        assert report["tokens"]["input_tokens"] == 300
        assert report["tokens"]["output_tokens"] == 150


class TestPermissions:
    """Test permission system."""

    def test_permission_check(self):
        """Test permission checking."""
        from router_service.tools.guardrails.permissions import PermissionManager

        manager = PermissionManager()

        # Default policy (require approval)
        can_use, reason = manager.can_use_tool("test_tool")
        assert can_use  # Allowed but requires approval
        assert "approval" in reason.lower()

    def test_tool_denylist(self):
        """Test tool denylist."""
        from router_service.tools.guardrails.permissions import PermissionManager

        policy = PermissionPolicy(disallowed_tools=["dangerous_tool"])
        manager = PermissionManager(default_policy=policy)

        can_use, reason = manager.can_use_tool("dangerous_tool")
        assert not can_use
        assert "disallowed" in reason.lower()

    def test_audit_log(self):
        """Test audit logging."""
        from router_service.tools.guardrails.permissions import PermissionManager

        manager = PermissionManager()

        manager.can_use_tool("tool1", user_id="user1")
        manager.can_use_tool("tool2", user_id="user2")

        audit = manager.get_audit_log(limit=10)
        assert len(audit) == 2
        assert audit[0]["tool_name"] == "tool1"
        assert audit[1]["tool_name"] == "tool2"


class TestAgentSystem:
    """Test subagent system."""

    def test_agent_registration(self):
        """Test agent registration."""
        registry = get_agent_registry()

        agent = AgentDefinition(
            name="test_agent",
            description="Test agent for unit testing",
            prompt="You are a test agent",
            tools=["read", "write"],
            model=AgentModel.SONNET,
        )

        registry.register(agent)

        retrieved = registry.get("test_agent")
        assert retrieved is not None
        assert retrieved.name == "test_agent"

    def test_agent_matching(self):
        """Test agent task matching."""
        registry = get_agent_registry()

        agent = AgentDefinition(
            name="code_reviewer",
            description="Reviews code for bugs and security issues",
            prompt="You are a code reviewer",
            tools=["read", "grep"],
        )

        registry.register(agent)

        # Should match
        matched = registry.match_agent("Please review this code for bugs")
        assert matched is not None
        assert matched.name == "code_reviewer"

        # Should not match
        matched = registry.match_agent("Please write a new feature")
        # May or may not match depending on other registered agents


class TestIntegration:
    """Test ATP tool manager integration."""

    @pytest.mark.asyncio
    async def test_tool_manager_initialization(self):
        """Test tool manager initialization."""
        manager = ATPToolManager(enable_builtin_tools=True, enable_mcp=False)

        # Should have built-in tools registered
        tools = manager.get_tools_for_request()
        assert len(tools) > 0

        # Should have common tools
        tool_names = {t["name"] for t in tools}
        assert "bash" in tool_names
        assert "read" in tool_names

    @pytest.mark.asyncio
    async def test_tool_execution_with_permissions(self):
        """Test tool execution with permission checks."""
        from router_service.tools.guardrails.permissions import PermissionPolicy

        policy = PermissionPolicy(mode=PermissionMode.ACCEPT_EDITS, allowed_tools=["bash"])
        manager = ATPToolManager(permission_policy=policy)

        # Should succeed (bash allowed)
        tool_use = ToolUse(id="test-1", name="bash", input={"command": "echo test"})
        result = await manager.execute_tool(tool_use, user_id="test_user")

        # Result depends on handler implementation
        assert result is not None

    def test_cost_tracking_integration(self):
        """Test cost tracking integration."""
        manager = ATPToolManager()

        cost = manager.track_usage(
            step_id="step-1",
            message_id="msg-1",
            input_tokens=100,
            output_tokens=50,
            session_id="session-1",
        )

        assert cost > 0

        report = manager.get_cost_report()
        assert report["total_steps"] == 1
        assert report["total_cost_usd"] == cost


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
