"""Built-in tools for ATP/AGP."""

from router_service.tools.builtin.bash import BASH_TOOL, bash_tool_handler
from router_service.tools.builtin.file_ops import (
    FILE_OPERATION_TOOLS,
    edit_tool_handler,
    glob_tool_handler,
    grep_tool_handler,
    read_tool_handler,
    write_tool_handler,
)
from router_service.tools.core.registry import get_registry


# Register all built-in tools
def register_builtin_tools():
    """Register all built-in tools with the global registry."""
    registry = get_registry()

    # Bash tool
    registry.register(BASH_TOOL, bash_tool_handler, category="builtin")

    # File operation tools
    handlers = {
        "read": read_tool_handler,
        "write": write_tool_handler,
        "edit": edit_tool_handler,
        "glob": glob_tool_handler,
        "grep": grep_tool_handler,
    }

    for tool in FILE_OPERATION_TOOLS:
        registry.register(tool, handlers[tool.name], category="builtin")


__all__ = ["register_builtin_tools"]
