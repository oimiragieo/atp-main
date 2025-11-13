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

#!/usr/bin/env python3
"""MCP CLI Reference Client (GAP-132).

A command-line interface for interacting with MCP (Model Context Protocol) servers.
Provides tools for connecting, listing available tools, and invoking tools with streaming support.
"""

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosedError

from .tool_schema_versioning import ToolSchemaVersioning


class MCPClient:
    """MCP WebSocket client for interacting with MCP servers."""

    def __init__(self, host: str = "localhost", port: int = 7443, secure: bool = False,
                 schema_version: Optional[str] = None):
        """Initialize MCP client.

        Args:
            host: Server hostname
            port: Server port
            secure: Whether to use wss:// instead of ws://
            schema_version: MCP schema version to request (optional)
        """
        self.host = host
        self.port = port
        self.secure = secure
        self.ws_url = f"{'wss' if secure else 'ws'}://{host}:{port}/mcp"
        self.websocket = None
        self.session_id = str(uuid.uuid4())[:8]
        self.schema_versioning = ToolSchemaVersioning()
        self.negotiated_version: Optional[str] = None
        self.requested_version = schema_version

    async def connect(self) -> None:
        """Connect to MCP server and negotiate schema version."""
        try:
            print(f"Connecting to {self.ws_url}...")
            self.websocket = await websockets.connect(self.ws_url)
            print("✅ Connected successfully")

            # Negotiate schema version
            await self._negotiate_schema_version()

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            raise

    async def _negotiate_schema_version(self) -> None:
        """Negotiate MCP schema version with server."""
        try:
            # Request schema version negotiation
            requested = self.requested_version or self.schema_versioning.get_latest_version("index")
            if requested:
                negotiate_msg = {
                    "type": "negotiateSchema",
                    "id": f"{self.session_id}-negotiate",
                    "requestedVersion": requested
                }
                await self.send_message(negotiate_msg)

                # Wait for negotiation response
                response = await self.receive_message()
                if response.get("type") == "schemaNegotiated":
                    self.negotiated_version = response.get("negotiatedVersion")
                    print(f"📋 Schema version negotiated: {self.negotiated_version}")
                else:
                    # Fallback to latest available
                    self.negotiated_version = self.schema_versioning.get_latest_version("index")
                    print(f"📋 Using fallback schema version: {self.negotiated_version}")
            else:
                print("⚠️  No schema versions available, proceeding without negotiation")

        except Exception as e:
            print(f"⚠️  Schema negotiation failed: {e}, proceeding without validation")
            self.negotiated_version = None

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self.websocket:
            await self.websocket.close()
            print("✅ Disconnected")

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send a message to the MCP server with schema validation."""
        if not self.websocket:
            raise ConnectionError("Not connected to MCP server")

        # Validate outgoing message
        if not self.validate_outgoing_message(message):
            raise ValueError("Message failed schema validation")

        await self.websocket.send(json.dumps(message))
        print(f"📤 Sent: {message['type']}")

    async def receive_message(self) -> dict[str, Any]:
        """Receive a message from the MCP server with schema validation."""
        if not self.websocket:
            raise ConnectionError("Not connected to MCP server")

        try:
            message_raw = await self.websocket.recv()
            message = json.loads(message_raw)

            # Validate message against schema if version negotiated
            if self.negotiated_version:
                await self._validate_message_schema(message)

            return message
        except ConnectionClosedError:
            print("❌ Connection closed by server")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON received: {e}")
            raise

    async def _validate_message_schema(self, message: dict[str, Any]) -> None:
        """Validate message against negotiated schema version."""
        msg_type = message.get("type")
        if not msg_type:
            return  # Skip validation for messages without type

        try:
            is_valid, error = self.schema_versioning.validate_message(
                message, msg_type, self.negotiated_version
            )
            if not is_valid:
                print(f"⚠️  Schema validation warning for {msg_type}: {error}")
        except Exception as e:
            print(f"⚠️  Schema validation error: {e}")

    def validate_outgoing_message(self, message: dict[str, Any]) -> bool:
        """Validate outgoing message against schema.

        Args:
            message: Message to validate

        Returns:
            True if valid or no schema available, False otherwise
        """
        if not self.negotiated_version:
            return True  # Skip validation if no negotiated version

        msg_type = message.get("type")
        if not msg_type:
            return True

        try:
            is_valid, error = self.schema_versioning.validate_message(
                message, msg_type, self.negotiated_version
            )
            if not is_valid:
                print(f"❌ Outgoing message validation failed: {error}")
                return False
            return True
        except Exception as e:
            print(f"❌ Message validation error: {e}")
            return False

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        await self.send_message({"type": "listTools", "id": self.session_id})

        response = await self.receive_message()
        if response.get("type") == "listTools":
            tools = response.get("tools", [])
            print(f"📋 Available tools ({len(tools)}):")
            for tool in tools:
                print(f"  • {tool.get('name', 'unknown')}: {tool.get('description', 'no description')}")
            return tools
        else:
            print(f"❌ Unexpected response: {response}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], stream: bool = True) -> None:
        """Call a tool on the MCP server."""
        tool_call_id = f"{self.session_id}-{uuid.uuid4().hex[:8]}"

        message = {
            "type": "callTool",
            "id": tool_call_id,
            "tool": {
                "name": tool_name,
                "arguments": arguments
            },
            "stream": stream
        }

        await self.send_message(message)

        if stream:
            await self._handle_streaming_response(tool_call_id)
        else:
            response = await self.receive_message()
            self._handle_tool_response(response)

    async def _handle_streaming_response(self, tool_call_id: str) -> None:
        """Handle streaming response from tool call."""
        try:
            while True:
                response = await self.receive_message()

                if response.get("type") == "toolOutput":
                    if response.get("toolCallId") == tool_call_id:
                        self._handle_tool_output(response)
                        if response.get("final", False):
                            break
                elif response.get("type") == "error":
                    self._handle_error(response)
                    break
                else:
                    print(f"📨 Other message: {response.get('type', 'unknown')}")
        except ConnectionClosedError:
            print("❌ Connection lost")
            return

    def _handle_tool_response(self, response: dict[str, Any]) -> None:
        """Handle non-streaming tool response."""
        if response.get("type") == "toolOutput":
            self._handle_tool_output(response)
        elif response.get("type") == "error":
            self._handle_error(response)
        else:
            print(f"📨 Unexpected response: {response}")

    def _handle_tool_output(self, response: dict[str, Any]) -> None:
        """Handle tool output messages."""
        content = response.get("content", [])
        sequence = response.get("sequence", 0)
        is_partial = response.get("is_partial", False)
        is_final = response.get("final", False)

        if is_partial:
            print(f"📄 Partial [{sequence}]: ", end="")
        elif is_final:
            print(f"🏁 Final [{sequence}]: ", end="")
        else:
            print("📄 Output: ", end="")

        for item in content:
            if item.get("type") == "text":
                print(item.get("text", ""), end="")
            elif item.get("type") == "image":
                print(f"[Image: {item.get('mimeType', 'unknown')}]", end="")
            elif item.get("type") == "json":
                print(f"[JSON: {item.get('data', '{}')}]", end="")

        if is_final:
            metadata = response.get("metadata", {})
            if metadata:
                print(f"\n📊 Metadata: {json.dumps(metadata, indent=2)}")
        else:
            print()

    def _handle_error(self, response: dict[str, Any]) -> None:
        """Handle error messages."""
        error = response.get("error", {})
        code = error.get("code", "UNKNOWN")
        message = error.get("message", "Unknown error")
        print(f"❌ Error [{code}]: {message}")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MCP CLI Reference Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list-tools
  %(prog)s --call-tool route.complete --args '{"prompt": "Hello world"}'
  %(prog)s --call-tool adapter.python --args '{"code": "print(\\"hello\\")"}' --model gpt-4
        """
    )

    parser.add_argument("--host", default="localhost", help="MCP server hostname")
    parser.add_argument("--port", type=int, default=7443, help="MCP server port")
    parser.add_argument("--secure", action="store_true", help="Use secure WebSocket (wss://)")
    parser.add_argument("--schema-version", help="MCP schema version to request (e.g., v1.0, v1.1)")
    parser.add_argument("--list-tools", action="store_true", help="List available tools")
    parser.add_argument("--call-tool", help="Tool name to call")
    parser.add_argument("--args", help="JSON arguments for tool call")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming for tool calls")

    args = parser.parse_args()

    # Validate arguments
    if not any([args.list_tools, args.call_tool]):
        parser.error("Must specify either --list-tools or --call-tool")

    if args.call_tool and not args.args:
        parser.error("--call-tool requires --args with JSON arguments")

    # Parse tool arguments
    tool_args = {}
    if args.args:
        try:
            tool_args = json.loads(args.args)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in --args: {e}")
            sys.exit(1)

    # Create client and connect
    client = MCPClient(host=args.host, port=args.port, secure=args.secure,
                      schema_version=args.schema_version)

    try:
        await client.connect()

        if args.list_tools:
            await client.list_tools()
        elif args.call_tool:
            await client.call_tool(args.call_tool, tool_args, stream=not args.no_stream)

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
