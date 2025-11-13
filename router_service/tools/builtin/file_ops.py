"""File operation tools: Read, Write, Edit, Glob, Grep.

Enterprise-grade file manipulation with security controls.
"""

from __future__ import annotations

import glob as glob_module
import logging
import os
import re
from pathlib import Path
from typing import Any

from router_service.tools.core.schema import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Security: Restrict file access to workspace
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/workspace")


def validate_path(path: str) -> Path:
    """Validate and resolve file path within workspace.

    Args:
        path: File path to validate

    Returns:
        Resolved Path object

    Raises:
        ValueError: Path outside workspace
    """
    resolved = Path(path).resolve()
    workspace = Path(WORKSPACE_ROOT).resolve()

    if not str(resolved).startswith(str(workspace)):
        raise ValueError(f"Path outside workspace: {path}")

    return resolved


async def read_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Read file contents.

    Args:
        args: {file_path: str, offset: int, limit: int}
        context: Execution context

    Returns:
        ToolResult with file contents
    """
    file_path = args.get("file_path")
    offset = args.get("offset", 0)
    limit = args.get("limit", 2000)

    try:
        path = validate_path(file_path)

        if not path.exists():
            return ToolResult(
                tool_use_id=context.get("tool_use_id", ""),
                content=f"Error: File not found: {file_path}",
                is_error=True,
            )

        # Read file with offset/limit
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        selected_lines = lines[offset : offset + limit]

        # Format output with line numbers
        output = []
        for i, line in enumerate(selected_lines, start=offset + 1):
            output.append(f"{i:6d}→{line}")

        result = "".join(output)
        if offset + limit < total_lines:
            result += f"\n[Showing lines {offset + 1}-{offset + len(selected_lines)} of {total_lines}]"

        return ToolResult(tool_use_id=context.get("tool_use_id", ""), content=result, is_error=False)

    except Exception as e:
        logger.exception(f"Error reading file: {file_path}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error reading file: {e}",
            is_error=True,
        )


async def write_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Write content to file.

    Args:
        args: {file_path: str, content: str}
        context: Execution context

    Returns:
        ToolResult confirming write
    """
    file_path = args.get("file_path")
    content = args.get("content", "")

    try:
        path = validate_path(file_path)

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with path.open("w", encoding="utf-8") as f:
            f.write(content)

        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Successfully wrote {len(content)} bytes to {file_path}",
            is_error=False,
        )

    except Exception as e:
        logger.exception(f"Error writing file: {file_path}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error writing file: {e}",
            is_error=True,
        )


async def edit_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Edit file by replacing text.

    Args:
        args: {file_path: str, old_string: str, new_string: str, replace_all: bool}
        context: Execution context

    Returns:
        ToolResult confirming edit
    """
    file_path = args.get("file_path")
    old_string = args.get("old_string")
    new_string = args.get("new_string")
    replace_all = args.get("replace_all", False)

    try:
        path = validate_path(file_path)

        if not path.exists():
            return ToolResult(
                tool_use_id=context.get("tool_use_id", ""),
                content=f"Error: File not found: {file_path}",
                is_error=True,
            )

        # Read file
        with path.open("r", encoding="utf-8") as f:
            content = f.read()

        # Replace
        if replace_all:
            count = content.count(old_string)
            new_content = content.replace(old_string, new_string)
        else:
            # Replace first occurrence
            count = 1 if old_string in content else 0
            new_content = content.replace(old_string, new_string, 1)

        if count == 0:
            return ToolResult(
                tool_use_id=context.get("tool_use_id", ""),
                content=f"Error: String not found in file: {old_string}",
                is_error=True,
            )

        # Write back
        with path.open("w", encoding="utf-8") as f:
            f.write(new_content)

        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Successfully replaced {count} occurrence(s) in {file_path}",
            is_error=False,
        )

    except Exception as e:
        logger.exception(f"Error editing file: {file_path}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error editing file: {e}",
            is_error=True,
        )


async def glob_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Find files matching glob pattern.

    Args:
        args: {pattern: str, path: str}
        context: Execution context

    Returns:
        ToolResult with matching file paths
    """
    pattern = args.get("pattern")
    search_path = args.get("path", ".")

    try:
        base_path = validate_path(search_path)

        # Execute glob
        full_pattern = str(base_path / pattern)
        matches = sorted(glob_module.glob(full_pattern, recursive=True))

        # Filter to workspace
        workspace = Path(WORKSPACE_ROOT).resolve()
        filtered = [m for m in matches if Path(m).resolve().is_relative_to(workspace)]

        if not filtered:
            return ToolResult(
                tool_use_id=context.get("tool_use_id", ""),
                content=f"No files found matching: {pattern}",
                is_error=False,
            )

        # Format output
        result = f"Found {len(filtered)} file(s):\n" + "\n".join(filtered)

        return ToolResult(tool_use_id=context.get("tool_use_id", ""), content=result, is_error=False)

    except Exception as e:
        logger.exception(f"Error globbing: {pattern}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error searching files: {e}",
            is_error=True,
        )


async def grep_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Search file contents using regex.

    Args:
        args: {pattern: str, path: str, output_mode: str, head_limit: int, case_insensitive: bool}
        context: Execution context

    Returns:
        ToolResult with search results
    """
    pattern = args.get("pattern")
    search_path = args.get("path", ".")
    output_mode = args.get("output_mode", "files_with_matches")
    head_limit = args.get("head_limit", 100)
    case_insensitive = args.get("case_insensitive", False)

    try:
        base_path = validate_path(search_path)

        # Compile regex
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)

        # Search files
        results = []
        for root, _, files in os.walk(base_path):
            for filename in files:
                filepath = Path(root) / filename

                try:
                    with filepath.open("r", encoding="utf-8") as f:
                        content = f.read()

                    matches = regex.findall(content)
                    if matches:
                        if output_mode == "files_with_matches":
                            results.append(str(filepath))
                        elif output_mode == "count":
                            results.append(f"{filepath}: {len(matches)}")
                        else:  # content
                            lines = content.split("\n")
                            for i, line in enumerate(lines, 1):
                                if regex.search(line):
                                    results.append(f"{filepath}:{i}:{line}")

                except (UnicodeDecodeError, PermissionError):
                    continue

        # Apply limit
        limited_results = results[:head_limit]

        if not limited_results:
            return ToolResult(
                tool_use_id=context.get("tool_use_id", ""),
                content=f"No matches found for pattern: {pattern}",
                is_error=False,
            )

        result = "\n".join(limited_results)
        if len(results) > head_limit:
            result += f"\n\n[Showing {head_limit} of {len(results)} results]"

        return ToolResult(tool_use_id=context.get("tool_use_id", ""), content=result, is_error=False)

    except Exception as e:
        logger.exception(f"Error grepping: {pattern}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error searching: {e}",
            is_error=True,
        )


# Tool definitions
FILE_OPERATION_TOOLS = [
    ToolDefinition(
        name="read",
        description="""Read file contents from the filesystem. Returns file contents with line numbers for easy reference. Supports reading specific line ranges for large files. Use this tool when you need to examine file contents, inspect configuration, review code, or read data files.""",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute or relative path to the file"},
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed)",
                    "default": 0,
                },
                "limit": {"type": "integer", "description": "Maximum number of lines to read", "default": 2000},
            },
            "required": ["file_path"],
        },
    ),
    ToolDefinition(
        name="write",
        description="""Write content to a file. Creates the file if it doesn't exist, including parent directories. Overwrites existing files completely. Use this tool to create new files, save generated content, write configuration files, or update existing files with completely new content.""",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path where file should be written"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["file_path", "content"],
        },
    ),
    ToolDefinition(
        name="edit",
        description="""Edit an existing file by replacing text. Finds exact string matches and replaces them with new content. Can replace first occurrence or all occurrences. Use this tool for targeted edits to existing files when you want to modify specific content without rewriting the entire file.""",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to file to edit"},
                "old_string": {"type": "string", "description": "Exact string to find and replace"},
                "new_string": {"type": "string", "description": "Replacement string"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: first only)",
                    "default": False,
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    ),
    ToolDefinition(
        name="glob",
        description="""Find files matching a glob pattern. Supports wildcards (* for any characters, ** for recursive directory matching, ? for single character). Returns sorted list of matching file paths. Use this tool to discover files by name pattern, find all files of a type, or locate files in directory structures.""",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py', 'src/*.ts')"},
                "path": {"type": "string", "description": "Base directory to search from", "default": "."},
            },
            "required": ["pattern"],
        },
    ),
    ToolDefinition(
        name="grep",
        description="""Search file contents using regular expressions. Supports case-insensitive search and multiple output modes (file paths, match counts, or matching lines with context). Use this tool to find code patterns, search for specific content across files, or locate usage of functions/variables.""",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search", "default": "."},
                "output_mode": {
                    "type": "string",
                    "enum": ["files_with_matches", "count", "content"],
                    "default": "files_with_matches",
                },
                "head_limit": {"type": "integer", "description": "Maximum results to return", "default": 100},
                "case_insensitive": {"type": "boolean", "description": "Case-insensitive search", "default": False},
            },
            "required": ["pattern"],
        },
    ),
]
