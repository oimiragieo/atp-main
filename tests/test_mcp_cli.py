"""Tests for MCP CLI Reference Client (GAP-132)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from client.mcp_cli import MCPClient


class TestMCPClient:
    """Test MCP CLI client functionality."""

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket for testing."""
        ws = MagicMock()
        ws.send = AsyncMock()
        ws.recv = AsyncMock()
        ws.close = AsyncMock()
        return ws

    @pytest.fixture
    def client(self):
        """Test client instance."""
        return MCPClient("localhost", 7443, False)

    @pytest.mark.asyncio
    async def test_connect_success(self, client, mock_websocket):
        """Test successful connection to MCP server."""
        with patch("client.mcp_cli.websockets") as mock_ws_module:
            mock_ws_module.connect = AsyncMock(return_value=mock_websocket)
            await client.connect()

            assert client.websocket == mock_websocket
            assert client.session_id is not None

    @pytest.mark.asyncio
    async def test_connect_failure(self, client):
        """Test connection failure handling."""
        with patch("client.mcp_cli.websockets.connect", side_effect=Exception("Connection refused")):
            with pytest.raises(Exception, match="Connection refused"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, client, mock_websocket):
        """Test disconnecting from MCP server."""
        client.websocket = mock_websocket
        await client.disconnect()

        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message(self, client, mock_websocket):
        """Test sending messages to MCP server."""
        client.websocket = mock_websocket
        message = {"type": "listTools", "id": "test-123"}

        await client.send_message(message)

        mock_websocket.send.assert_called_once_with(json.dumps(message))

    @pytest.mark.asyncio
    async def test_send_message_not_connected(self, client):
        """Test sending message when not connected."""
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.send_message({"type": "test"})

    @pytest.mark.asyncio
    async def test_receive_message(self, client, mock_websocket):
        """Test receiving messages from MCP server."""
        client.websocket = mock_websocket
        expected_message = {"type": "heartbeat"}
        mock_websocket.recv.return_value = json.dumps(expected_message)

        message = await client.receive_message()

        assert message == expected_message
        mock_websocket.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_message_invalid_json(self, client, mock_websocket):
        """Test handling of invalid JSON in received messages."""
        client.websocket = mock_websocket
        mock_websocket.recv.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            await client.receive_message()

    @pytest.mark.asyncio
    async def test_list_tools(self, client, mock_websocket):
        """Test listing available tools."""
        client.websocket = mock_websocket

        # Mock the send/receive sequence
        tools_response = {
            "type": "listTools",
            "tools": [
                {"name": "route.complete", "description": "Complete routing"},
                {"name": "adapter.python", "description": "Python adapter"},
            ],
        }

        # Set up the mock to return the response
        mock_websocket.recv.return_value = json.dumps(tools_response)

        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "route.complete"
        assert tools[1]["name"] == "adapter.python"

    @pytest.mark.asyncio
    async def test_call_tool_streaming(self, client, mock_websocket):
        """Test calling a tool with streaming responses."""
        client.websocket = mock_websocket

        # Mock streaming responses
        responses = [
            {
                "type": "toolOutput",
                "toolCallId": "test-123",
                "content": [{"type": "text", "text": "Hello"}],
                "sequence": 1,
                "cumulative_tokens": 1,
                "is_partial": True,
                "dp_metrics_emitted": True,
            },
            {
                "type": "toolOutput",
                "toolCallId": "test-123",
                "content": [{"type": "text", "text": " world!"}],
                "sequence": 2,
                "cumulative_tokens": 2,
                "final": True,
                "dp_metrics_emitted": True,
                "metadata": {"model_used": "gpt-4", "latency_ms": 150},
            },
        ]

        # Set up the mock to return responses in sequence, then raise ConnectionClosedError
        from websockets import frames
        from websockets.exceptions import ConnectionClosedError

        close_frame = frames.Close(1000, "Connection closed")
        mock_websocket.recv.side_effect = [json.dumps(resp) for resp in responses] + [
            ConnectionClosedError(close_frame, None)
        ]

        await client.call_tool("route.complete", {"prompt": "Hello world"}, stream=True)

        # Verify the call was made
        assert mock_websocket.send.called
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_message["type"] == "callTool"
        assert sent_message["tool"]["name"] == "route.complete"
        assert sent_message["stream"] is True

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self, client, mock_websocket):
        """Test handling error responses from tool calls."""
        client.websocket = mock_websocket

        error_response = {"type": "error", "error": {"code": "INTERNAL_ERROR", "message": "Tool execution failed"}}

        mock_websocket.recv.return_value = json.dumps(error_response)

        await client.call_tool("route.complete", {"prompt": "test"}, stream=False)

        # Should handle the error gracefully without raising exception
        assert mock_websocket.send.called

    @pytest.mark.asyncio
    async def test_call_tool_connection_closed(self, client, mock_websocket):
        """Test handling connection closed during tool call."""
        client.websocket = mock_websocket

        from websockets.exceptions import ConnectionClosedError

        mock_websocket.recv.side_effect = ConnectionClosedError(None, None)

        await client.call_tool("route.complete", {"prompt": "test"}, stream=True)

        # Should handle the connection error gracefully
        assert mock_websocket.send.called


class TestMCPClientIntegration:
    """Integration tests for MCP CLI client (requires running server)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_connect_to_real_server(self):
        """Test connecting to a real MCP server (requires server to be running)."""
        # This test is marked as integration and would require a running server
        # For now, we'll skip it in the basic test suite
        pytest.skip("Integration test requires running MCP server")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_tools_integration(self):
        """Integration test for listing tools from real server."""
        pytest.skip("Integration test requires running MCP server")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_call_tool_integration(self):
        """Integration test for calling tools on real server."""
        pytest.skip("Integration test requires running MCP server")


class TestMCPCLIArguments:
    """Test CLI argument parsing and validation."""

    def test_client_initialization(self):
        """Test MCP client initialization with different parameters."""
        # Default initialization
        client = MCPClient()
        assert client.host == "localhost"
        assert client.port == 7443
        assert client.secure is False
        assert "ws://localhost:7443/mcp" == client.ws_url

        # Custom initialization
        client = MCPClient("example.com", 8080, True)
        assert client.host == "example.com"
        assert client.port == 8080
        assert client.secure is True
        assert "wss://example.com:8080/mcp" == client.ws_url

    def test_session_id_generation(self):
        """Test that session IDs are generated properly."""
        client = MCPClient()
        assert client.session_id is not None
        assert len(client.session_id) == 8  # UUID hex truncated to 8 chars

        # Different clients should have different session IDs
        client2 = MCPClient()
        assert client.session_id != client2.session_id


if __name__ == "__main__":
    # Allow running basic smoke tests
    print("Running MCP CLI smoke tests...")

    async def smoke_test():
        """Basic smoke test for MCP client."""
        client = MCPClient()

        # Test that client can be created and has correct defaults
        assert client.host == "localhost"
        assert client.port == 7443
        assert not client.secure

        print("✅ Smoke test passed")

    asyncio.run(smoke_test())
