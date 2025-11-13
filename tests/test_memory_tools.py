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

"""Tests for memory/context exposure via tools (GAP-134)."""

import pytest

from client.memory_tools import MemoryGatewayClient, MemoryTools, PermissionChecker


class TestPermissionChecker:
    """Test permission checker functionality."""

    def test_check_namespace_access_exact_match(self):
        """Test exact namespace match."""
        checker = PermissionChecker(["session.data", "agent.config"])
        assert checker.check_namespace_access("session.data", "read")
        assert not checker.check_namespace_access("user.data", "read")

    def test_check_namespace_access_wildcard(self):
        """Test wildcard namespace patterns."""
        checker = PermissionChecker(["session.*", "public.*"])
        assert checker.check_namespace_access("session.data", "read")
        assert checker.check_namespace_access("session.config", "read")
        assert checker.check_namespace_access("public.info", "read")
        assert not checker.check_namespace_access("private.data", "read")

    def test_check_namespace_access_operation_types(self):
        """Test that operation type doesn't affect namespace checking."""
        checker = PermissionChecker(["session.*"])
        assert checker.check_namespace_access("session.data", "read")
        assert checker.check_namespace_access("session.data", "write")


class TestMemoryGatewayClient:
    """Test memory gateway client functionality."""

    @pytest.mark.asyncio
    async def test_list_keys_basic(self):
        """Test basic key listing."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            response = await client.list_keys("test_namespace", limit=10)

        assert "keys" in response
        assert "cursor" in response
        assert "total" in response
        assert len(response["keys"]) <= 10

    @pytest.mark.asyncio
    async def test_list_keys_with_prefix(self):
        """Test key listing with prefix filter."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            response = await client.list_keys("test_namespace", prefix="key_1", limit=5)

        assert all(key.startswith("key_1") for key in response["keys"])

    @pytest.mark.asyncio
    async def test_list_keys_pagination(self):
        """Test key listing pagination."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            # First page
            response1 = await client.list_keys("test_namespace", limit=5)
            assert len(response1["keys"]) == 5
            assert response1["cursor"] == "5"

            # Second page
            response2 = await client.list_keys("test_namespace", limit=5, cursor="5")
            assert len(response2["keys"]) == 5
            assert response2["cursor"] == "10"

    @pytest.mark.asyncio
    async def test_get_existing_key(self):
        """Test getting an existing key."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            value = await client.get("session", "session_123")

        assert value is not None
        assert value["session_id"] == "session_123"
        assert "start_time" in value

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Test getting a nonexistent key."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            value = await client.get("session", "nonexistent_key")

        assert value is None

    @pytest.mark.asyncio
    async def test_put_data(self):
        """Test storing data."""
        client = MemoryGatewayClient("http://localhost:8000", "test_tenant")

        async with client:
            success = await client.put("session", "test_key", {"data": "value"})

        assert success is True


class TestMemoryTools:
    """Test memory tools functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tools = MemoryTools(
            memory_gateway_url="http://localhost:8000",
            tenant_id="test_tenant",
            allowed_namespaces=["session.*", "agent.*", "public.*"]
        )

    def test_filter_pii_keys_no_pii(self):
        """Test PII filtering with no PII keys."""
        keys = ["session_data", "agent_config", "public_info"]
        filtered = self.tools._filter_pii_keys(keys)
        assert filtered == keys

    def test_filter_pii_keys_with_pii(self):
        """Test PII filtering with PII-containing keys."""
        keys = ["session_data", "user_email", "agent_phone", "public_token"]
        filtered = self.tools._filter_pii_keys(keys)

        assert len(filtered) == 4
        assert "session_data" in filtered
        assert "[REDACTED]_" in filtered[1]  # user_email redacted
        assert "[REDACTED]_" in filtered[2]  # agent_phone redacted
        assert "[REDACTED]_" in filtered[3]  # public_token redacted

    def test_validate_memory_data_valid(self):
        """Test validation of valid memory data."""
        valid_data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        # Should not raise exception
        self.tools._validate_memory_data(valid_data)

    def test_validate_memory_data_invalid_json(self):
        """Test validation of non-JSON-serializable data."""
        invalid_data = {"function": lambda x: x}  # Functions aren't JSON serializable

        with pytest.raises(ValueError, match="not JSON serializable"):
            self.tools._validate_memory_data(invalid_data)

    def test_validate_memory_data_too_large(self):
        """Test validation of oversized data."""
        large_data = {"data": "x" * (1024 * 1024 + 1)}  # Over 1MB

        with pytest.raises(ValueError, match="Data too large"):
            self.tools._validate_memory_data(large_data)

    @pytest.mark.asyncio
    async def test_list_memory_allowed_namespace(self):
        """Test listing memory in allowed namespace."""
        result = await self.tools.list_memory({"namespace": "session.data"})

        assert "keys" in result
        assert "cursor" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_list_memory_denied_namespace(self):
        """Test listing memory in denied namespace."""
        with pytest.raises(PermissionError, match="Access denied"):
            await self.tools.list_memory({"namespace": "private.data"})

    @pytest.mark.asyncio
    async def test_get_context_all_types(self):
        """Test getting all context types."""
        result = await self.tools.get_context({"context_type": "all"})

        assert "session_id" in result
        assert "agent_id" in result
        assert "task_id" in result
        assert "start_time" in result
        assert "memory_usage" in result

    @pytest.mark.asyncio
    async def test_get_context_session_only(self):
        """Test getting session context only."""
        result = await self.tools.get_context({"context_type": "session"})

        assert "session_id" in result
        assert "start_time" in result
        assert "memory_usage" in result
        assert "agent_id" not in result
        assert "task_id" not in result

    @pytest.mark.asyncio
    async def test_get_context_with_history(self):
        """Test getting context with history."""
        result = await self.tools.get_context({
            "context_type": "all",
            "include_history": True
        })

        assert "tool_history" in result
        assert isinstance(result["tool_history"], list)

    @pytest.mark.asyncio
    async def test_put_memory_allowed_namespace(self):
        """Test putting memory in allowed namespace."""
        result = await self.tools.put_memory({
            "namespace": "session.data",
            "key": "test_key",
            "value": {"test": "data"}
        })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_put_memory_denied_namespace(self):
        """Test putting memory in denied namespace."""
        with pytest.raises(PermissionError, match="Write access denied"):
            await self.tools.put_memory({
                "namespace": "private.data",
                "key": "test_key",
                "value": {"test": "data"}
            })

    @pytest.mark.asyncio
    async def test_put_memory_invalid_data(self):
        """Test putting invalid memory data."""
        with pytest.raises(ValueError, match="not JSON serializable"):
            await self.tools.put_memory({
                "namespace": "session.data",
                "key": "test_key",
                "value": {"function": lambda x: x}
            })

    def test_get_tool_definitions(self):
        """Test getting tool definitions."""
        definitions = self.tools.get_tool_definitions()

        assert len(definitions) == 3

        # Check listMemory tool
        list_tool = next(d for d in definitions if d["name"] == "listMemory")
        assert "namespace" in list_tool["inputSchema"]["required"]
        assert "properties" in list_tool["inputSchema"]

        # Check getContext tool
        context_tool = next(d for d in definitions if d["name"] == "getContext")
        assert "context_type" in context_tool["inputSchema"]["properties"]

        # Check putMemory tool
        put_tool = next(d for d in definitions if d["name"] == "putMemory")
        required = put_tool["inputSchema"]["required"]
        assert "namespace" in required
        assert "key" in required
        assert "value" in required

    @pytest.mark.asyncio
    async def test_execute_tool_list_memory(self):
        """Test executing listMemory tool."""
        result = await self.tools.execute_tool("listMemory", {"namespace": "session.data"})
        assert "keys" in result

    @pytest.mark.asyncio
    async def test_execute_tool_get_context(self):
        """Test executing getContext tool."""
        result = await self.tools.execute_tool("getContext", {})
        assert "session_id" in result

    @pytest.mark.asyncio
    async def test_execute_tool_put_memory(self):
        """Test executing putMemory tool."""
        result = await self.tools.execute_tool("putMemory", {
            "namespace": "session.data",
            "key": "test_key",
            "value": {"test": "data"}
        })
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self):
        """Test executing unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await self.tools.execute_tool("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_put_memory_updates_history(self):
        """Test that putMemory updates tool history."""
        initial_history_length = len(self.tools.session_context["tool_history"])

        await self.tools.put_memory({
            "namespace": "session.data",
            "key": "test_key",
            "value": {"test": "data"}
        })

        final_history_length = len(self.tools.session_context["tool_history"])
        assert final_history_length == initial_history_length + 1

        last_entry = self.tools.session_context["tool_history"][-1]
        assert last_entry["tool_name"] == "putMemory"
        assert last_entry["success"] is True
        assert "timestamp" in last_entry
