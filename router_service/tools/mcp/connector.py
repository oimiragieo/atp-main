"""MCP (Model Context Protocol) connector.

Implements MCP integration for external tool servers:
- stdio transport (subprocess)
- HTTP/SSE transport (remote servers)
- In-process SDK servers
- Tool exposure and resource management
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """MCP server transport types."""

    STDIO = "stdio"
    HTTP_SSE = "http_sse"
    SDK = "sdk"


@dataclass
class MCPServerConfig:
    """MCP server configuration."""

    name: str
    transport: MCPTransportType
    command: str | None = None  # For stdio
    args: list[str] | None = None  # For stdio
    env: dict[str, str] | None = None  # For stdio
    url: str | None = None  # For HTTP/SSE
    headers: dict[str, str] | None = None  # For HTTP/SSE


class MCPClient:
    """MCP protocol client for communicating with servers."""

    def __init__(self, config: MCPServerConfig):
        """Initialize MCP client.

        Args:
            config: Server configuration
        """
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.connected = False
        self.tools: dict[str, dict[str, Any]] = {}
        self.resources: dict[str, dict[str, Any]] = {}

    async def connect(self) -> bool:
        """Connect to MCP server.

        Returns:
            True if connected successfully
        """
        try:
            if self.config.transport == MCPTransportType.STDIO:
                await self._connect_stdio()
            elif self.config.transport == MCPTransportType.HTTP_SSE:
                await self._connect_http()
            else:
                logger.error(f"Unsupported transport: {self.config.transport}")
                return False

            # Initialize connection
            await self._send_initialize()
            await self._list_tools()
            await self._list_resources()

            self.connected = True
            logger.info(
                f"Connected to MCP server: {self.config.name} "
                f"({len(self.tools)} tools, {len(self.resources)} resources)"
            )
            return True

        except Exception:
            logger.exception(f"Failed to connect to MCP server: {self.config.name}")
            self.connected = False
            return False

    async def _connect_stdio(self) -> None:
        """Connect via stdio transport."""
        # Prepare environment
        env = os.environ.copy()
        if self.config.env:
            # Support variable substitution: ${VAR_NAME:-default}
            for key, value in self.config.env.items():
                expanded = self._expand_env_var(value)
                env[key] = expanded

        # Start subprocess
        self.process = await asyncio.create_subprocess_exec(
            self.config.command,
            *(self.config.args or []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        logger.info(f"Started MCP server process: PID {self.process.pid}")

    async def _connect_http(self) -> None:
        """Connect via HTTP/SSE transport."""
        # HTTP/SSE implementation would go here
        # For now, placeholder
        logger.warning("HTTP/SSE transport not yet implemented")

    def _expand_env_var(self, value: str) -> str:
        """Expand environment variable with default support.

        Supports syntax: ${VAR_NAME:-default_value}

        Args:
            value: Value to expand

        Returns:
            Expanded value
        """
        import re

        pattern = r"\$\{([^}:]+)(?::-(.*?))?\}"

        def replace(match):
            var_name = match.group(1)
            default = match.group(2) or ""
            return os.getenv(var_name, default)

        return re.sub(pattern, replace, value)

    async def _send_initialize(self) -> None:
        """Send initialize request to MCP server."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "clientInfo": {"name": "ATP-Router", "version": "1.0.0"},
            },
        }

        await self._send_request(request)
        response = await self._receive_response()

        if "error" in response:
            raise RuntimeError(f"Initialize failed: {response['error']}")

    async def _list_tools(self) -> None:
        """List available tools from MCP server."""
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

        await self._send_request(request)
        response = await self._receive_response()

        if "result" in response and "tools" in response["result"]:
            for tool in response["result"]["tools"]:
                tool_name = f"mcp__{self.config.name}__{tool['name']}"
                self.tools[tool_name] = tool

    async def _list_resources(self) -> None:
        """List available resources from MCP server."""
        request = {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}

        await self._send_request(request)
        response = await self._receive_response()

        if "result" in response and "resources" in response["result"]:
            for resource in response["result"]["resources"]:
                self.resources[resource["uri"]] = resource

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server.

        Args:
            tool_name: Tool name (without mcp__ prefix)
            arguments: Tool arguments

        Returns:
            Tool result
        """
        request = {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        await self._send_request(request)
        response = await self._receive_response()

        if "error" in response:
            raise RuntimeError(f"Tool call failed: {response['error']}")

        return response.get("result", {})

    async def _send_request(self, request: dict[str, Any]) -> None:
        """Send JSON-RPC request to server."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("Not connected to MCP server")

        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

    async def _receive_response(self) -> dict[str, Any]:
        """Receive JSON-RPC response from server."""
        if not self.process or not self.process.stdout:
            raise RuntimeError("Not connected to MCP server")

        line = await self.process.stdout.readline()
        if not line:
            raise RuntimeError("Connection closed by MCP server")

        return json.loads(line.decode())

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                logger.warning(f"Error disconnecting from MCP server: {e}")
            finally:
                self.process = None
                self.connected = False
                logger.info(f"Disconnected from MCP server: {self.config.name}")


class MCPConnector:
    """Manages connections to multiple MCP servers."""

    def __init__(self):
        """Initialize MCP connector."""
        self.clients: dict[str, MCPClient] = {}

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """Connect to an MCP server.

        Args:
            config: Server configuration

        Returns:
            True if connected successfully
        """
        client = MCPClient(config)
        success = await client.connect()

        if success:
            self.clients[config.name] = client

        return success

    async def connect_all(self, configs: list[MCPServerConfig]) -> dict[str, bool]:
        """Connect to multiple MCP servers in parallel.

        Args:
            configs: List of server configurations

        Returns:
            Dict mapping server name to connection status
        """
        tasks = [self.connect_server(config) for config in configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        status = {}
        for config, result in zip(configs, results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Failed to connect to {config.name}: {result}")
                status[config.name] = False
            else:
                status[config.name] = result

        return status

    def get_client(self, server_name: str) -> MCPClient | None:
        """Get MCP client for a server.

        Args:
            server_name: Server name

        Returns:
            MCPClient or None if not connected
        """
        return self.clients.get(server_name)

    def get_all_tools(self) -> dict[str, dict[str, Any]]:
        """Get all tools from all connected servers.

        Returns:
            Dict mapping tool names to definitions
        """
        all_tools = {}
        for client in self.clients.values():
            all_tools.update(client.tools)
        return all_tools

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        tasks = [client.disconnect() for client in self.clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.clients.clear()
