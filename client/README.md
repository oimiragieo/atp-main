# MCP CLI Reference Client

A command-line interface for interacting with MCP (Model Context Protocol) servers.

## Installation

The MCP CLI is part of the ATP Router project. Make sure you have the required dependencies:

```bash
pip install websockets
```

## Usage

### Basic Usage

```bash
# List available tools
python client/mcp_cli.py --list-tools

# Call a tool with basic parameters
python client/mcp_cli.py --call-tool route.complete --prompt "Hello world"

# Call a tool with advanced parameters
python client/mcp_cli.py --call-tool route.complete \
  --prompt "Analyze this text" \
  --quality quality \
  --max-cost 0.10 \
  --latency-slo 3000

# Use a specific model
python client/mcp_cli.py --call-tool adapter.python \
  --prompt "print('hello')" \
  --model gpt-4
```

### Command Line Options

- `--host HOST`: MCP server hostname (default: localhost)
- `--port PORT`: MCP server port (default: 7443)
- `--secure`: Use secure WebSocket connection (wss://)
- `--list-tools`: List available tools and exit
- `--call-tool TOOL`: Name of tool to call
- `--prompt TEXT`: Prompt text for tool calls
- `--model MODEL`: Model to use for tool calls
- `--quality {fast,balanced,quality}`: Quality target (default: balanced)
- `--max-cost USD`: Maximum cost in USD (default: 0.05)
- `--latency-slo MS`: Latency SLO in milliseconds (default: 2000)
- `--no-stream`: Disable streaming responses

### Examples

#### 1. List Available Tools

```bash
$ python client/mcp_cli.py --list-tools
✅ Connected (session: abc123)
📋 Available tools (2):
  • route.complete: Complete routing with streaming support
  • adapter.python: Execute Python code
```

#### 2. Simple Tool Call

```bash
$ python client/mcp_cli.py --call-tool route.complete --prompt "Hello world"
✅ Connected (session: def456)
🔧 Calling tool: route.complete
📝 Arguments: {"prompt": "Hello world", "quality_target": "balanced", "max_cost_usd": 0.05, "latency_slo_ms": 2000}
📄 Partial [1]: Hello
📄 Partial [2]: world
🏁 Final [3]: response!
📊 Metadata: {
  "model_used": "gpt-4",
  "latency_ms": 150,
  "cost_estimate": 0.002
}
```

#### 3. Error Handling

```bash
$ python client/mcp_cli.py --call-tool nonexistent.tool --prompt "test"
✅ Connected (session: ghi789)
🔧 Calling tool: nonexistent.tool
❌ Error [TOOL_NOT_FOUND]: Tool not found
```

#### 4. Custom Server

```bash
$ python client/mcp_cli.py --host my-server.com --port 8080 --secure --list-tools
✅ Connected (session: jkl012)
📋 Available tools (3):
  • route.complete: Complete routing
  • adapter.python: Python execution
  • adapter.javascript: JavaScript execution
```

## Architecture

The MCP CLI consists of:

1. **MCPClient Class**: Core WebSocket client handling connection, messaging, and protocol logic
2. **CLI Interface**: Command-line argument parsing and user interaction
3. **Streaming Support**: Real-time handling of partial and final responses
4. **Error Handling**: Comprehensive error reporting and recovery

### Message Flow

```
CLI Command → Argument Parsing → MCPClient.connect() → WebSocket Handshake
    ↓
Tool Call/List → Message Formatting → WebSocket Send
    ↓
Server Response → Message Parsing → Streaming Display
    ↓
Final Result → Metadata Display → Cleanup
```

## Protocol Support

The CLI supports the complete MCP protocol including:

- **Connection Management**: Automatic connection handling with error recovery
- **Tool Discovery**: Dynamic tool listing and capability inspection
- **Tool Invocation**: Parameter passing and result handling
- **Streaming Responses**: Real-time partial result display
- **Error Handling**: Structured error codes and messages
- **Metadata**: Model usage, latency, and cost information

## Testing

Run the test suite:

```bash
# Unit tests
pytest tests/test_mcp_cli.py -v

# Integration tests (requires running MCP server)
pytest tests/test_mcp_cli.py::TestMCPClientIntegration -v
```

## Troubleshooting

### Connection Issues

- **Connection refused**: Ensure MCP server is running on the specified host/port
- **SSL errors**: Use `--secure` flag for wss:// connections
- **Timeout**: Check network connectivity and server status

### Tool Issues

- **Tool not found**: Verify tool name spelling and server configuration
- **Invalid parameters**: Check tool documentation for required parameters
- **Rate limiting**: Wait before retrying or reduce request frequency

### Streaming Issues

- **No streaming output**: Use `--no-stream` flag to disable streaming
- **Incomplete responses**: Check server logs for streaming errors
- **Connection drops**: Network issues during long-running requests

## Development

### Adding New Features

1. Extend `MCPClient` class for new protocol features
2. Add CLI arguments in the `main()` function
3. Update tests in `test_mcp_cli.py`
4. Update this documentation

### Code Structure

```
client/
├── mcp_cli.py          # Main CLI application
└── ...

tests/
└── test_mcp_cli.py     # CLI tests
```

## Related Documentation

- [MCP Protocol Specification](../docs/14_MCP_Integration.md)
- [JSON Schema Definitions](../schemas/mcp/)
- [Router Service](../router_service/)
