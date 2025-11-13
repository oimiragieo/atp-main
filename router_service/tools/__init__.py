"""Enterprise Tool Use Framework for ATP/AGP.

This module implements a comprehensive tool use system based on Claude's
tool use and agent SDK patterns. It provides:

- Tool schema definition and validation
- Fine-grained streaming support
- Built-in tools (bash, code execution, file ops, web)
- MCP (Model Context Protocol) integration
- Subagent system with delegation
- Cost tracking and analytics
- Safety guardrails and permissions

Architecture:
    router_service/tools/
    ├── __init__.py          # Public API
    ├── core/                # Core framework
    │   ├── schema.py        # Tool schemas and validation
    │   ├── executor.py      # Tool execution engine
    │   ├── streaming.py     # Fine-grained streaming
    │   └── registry.py      # Tool registry
    ├── builtin/             # Built-in tools
    │   ├── bash.py          # Bash tool with persistent sessions
    │   ├── code_exec.py     # Sandboxed code execution
    │   ├── file_ops.py      # Read, Write, Edit, Glob, Grep
    │   ├── web.py           # WebFetch, WebSearch
    │   └── memory.py        # Memory tool
    ├── mcp/                 # MCP integration
    │   ├── connector.py     # MCP server connector
    │   ├── transport.py     # stdio/HTTP/SSE transports
    │   └── client.py        # MCP client
    ├── agents/              # Agent system
    │   ├── subagent.py      # Subagent definitions
    │   ├── delegation.py    # Delegation logic
    │   └── context.py       # Context management
    ├── tracking/            # Cost tracking
    │   ├── usage.py         # Usage metrics
    │   └── cost.py          # Cost calculation
    └── guardrails/          # Safety
        ├── permissions.py   # Permission system
        ├── validation.py    # Input validation
        └── sanitization.py  # Output sanitization
"""

from router_service.tools.core.executor import ToolExecutor
from router_service.tools.core.registry import ToolRegistry
from router_service.tools.core.schema import ToolDefinition, ToolParameter, ToolResult

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    "ToolExecutor",
]

__version__ = "1.0.0"
