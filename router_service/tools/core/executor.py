"""Tool execution engine with streaming support.

Handles tool invocation, result formatting, error handling, and
fine-grained streaming for large parameters.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from router_service.tools.core.registry import get_registry
from router_service.tools.core.schema import (
    StreamingToolChunk,
    ToolExecutionError,
    ToolResult,
    ToolUse,
    ToolValidationError,
)

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tools with validation, error handling, and streaming."""

    def __init__(
        self,
        max_concurrent_tools: int = 10,
        timeout_seconds: float = 300.0,
        enable_streaming: bool = True,
    ):
        """Initialize tool executor.

        Args:
            max_concurrent_tools: Maximum parallel tool executions
            timeout_seconds: Per-tool execution timeout
            enable_streaming: Enable fine-grained streaming
        """
        self.max_concurrent_tools = max_concurrent_tools
        self.timeout_seconds = timeout_seconds
        self.enable_streaming = enable_streaming
        self._semaphore = asyncio.Semaphore(max_concurrent_tools)
        self._registry = get_registry()

    async def execute(self, tool_use: ToolUse, context: dict[str, Any] | None = None) -> ToolResult:
        """Execute a single tool.

        Args:
            tool_use: Tool use request from Claude
            context: Optional execution context (permissions, user_id, etc.)

        Returns:
            Tool result for Claude

        Raises:
            ToolValidationError: Invalid tool or parameters
            ToolExecutionError: Tool execution failed
        """
        start_time = time.time()
        context = context or {}

        # Validate tool exists
        tool_def = self._registry.get_tool(tool_use.name)
        if not tool_def:
            logger.error(f"Unknown tool: {tool_use.name}")
            return ToolResult(
                tool_use_id=tool_use.id,
                content=f"Error: Unknown tool '{tool_use.name}'",
                is_error=True,
            )

        # Get handler
        handler = self._registry.get_handler(tool_use.name)
        if not handler:
            logger.error(f"No handler for tool: {tool_use.name}")
            return ToolResult(
                tool_use_id=tool_use.id,
                content=f"Error: No handler for tool '{tool_use.name}'",
                is_error=True,
            )

        # Execute with semaphore for concurrency control
        async with self._semaphore:
            try:
                # Execute with timeout
                result = await asyncio.wait_for(handler(tool_use.input, context), timeout=self.timeout_seconds)

                # Format result
                if isinstance(result, ToolResult):
                    tool_result = result
                elif isinstance(result, str):
                    tool_result = ToolResult(tool_use_id=tool_use.id, content=result, is_error=False)
                elif isinstance(result, dict):
                    tool_result = ToolResult(
                        tool_use_id=tool_use.id,
                        content=json.dumps(result, indent=2),
                        is_error=False,
                    )
                else:
                    tool_result = ToolResult(tool_use_id=tool_use.id, content=str(result), is_error=False)

                elapsed = time.time() - start_time
                logger.info(f"Tool executed: {tool_use.name} in {elapsed:.2f}s (error: {tool_result.is_error})")

                return tool_result

            except asyncio.TimeoutError:
                logger.error(f"Tool timeout: {tool_use.name} after {self.timeout_seconds}s")
                return ToolResult(
                    tool_use_id=tool_use.id,
                    content=f"Error: Tool execution timed out after {self.timeout_seconds}s",
                    is_error=True,
                )

            except ToolValidationError as e:
                logger.error(f"Tool validation error: {tool_use.name} - {e}")
                return ToolResult(tool_use_id=tool_use.id, content=f"Validation error: {e}", is_error=True)

            except ToolExecutionError as e:
                logger.error(f"Tool execution error: {tool_use.name} - {e}")
                return ToolResult(tool_use_id=tool_use.id, content=f"Execution error: {e}", is_error=True)

            except Exception as e:
                logger.exception(f"Unexpected error executing tool: {tool_use.name}")
                return ToolResult(
                    tool_use_id=tool_use.id,
                    content=f"Unexpected error: {type(e).__name__}: {e}",
                    is_error=True,
                )

    async def execute_parallel(
        self, tool_uses: list[ToolUse], context: dict[str, Any] | None = None
    ) -> list[ToolResult]:
        """Execute multiple tools in parallel.

        Critical formatting requirement from docs:
        - All parallel tool results must go in ONE user message
        - Results must come FIRST in content array

        Args:
            tool_uses: List of tool use requests
            context: Shared execution context

        Returns:
            List of tool results in same order as inputs
        """
        if not tool_uses:
            return []

        logger.info(f"Executing {len(tool_uses)} tools in parallel")

        # Execute all in parallel
        tasks = [self.execute(tool_use, context) for tool_use in tool_uses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        formatted_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Tool {i} failed: {result}")
                formatted_results.append(
                    ToolResult(
                        tool_use_id=tool_uses[i].id,
                        content=f"Error: {type(result).__name__}: {result}",
                        is_error=True,
                    )
                )
            else:
                formatted_results.append(result)

        return formatted_results

    async def execute_streaming(
        self, tool_use: ToolUse, context: dict[str, Any] | None = None
    ) -> AsyncIterator[StreamingToolChunk]:
        """Execute tool with fine-grained streaming.

        Yields parameter values as they're generated without buffering.
        May yield partial/invalid JSON - handle gracefully.

        Args:
            tool_use: Tool use request
            context: Execution context

        Yields:
            StreamingToolChunk objects
        """
        if not self.enable_streaming:
            # Fall back to regular execution
            result = await self.execute(tool_use, context)
            yield StreamingToolChunk(
                tool_use_id=tool_use.id,
                parameter_name="result",
                chunk=result.content if isinstance(result.content, str) else json.dumps(result.content),
                is_complete=True,
                is_valid_json=True,
            )
            return

        # Get handler
        handler = self._registry.get_handler(tool_use.name)
        if not handler or not hasattr(handler, "__streaming__"):
            # Handler doesn't support streaming, fall back
            result = await self.execute(tool_use, context)
            yield StreamingToolChunk(
                tool_use_id=tool_use.id,
                parameter_name="result",
                chunk=result.content if isinstance(result.content, str) else json.dumps(result.content),
                is_complete=True,
                is_valid_json=True,
            )
            return

        # Execute streaming handler
        try:
            async for chunk in handler(tool_use.input, context, streaming=True):
                yield chunk
        except Exception as e:
            logger.exception(f"Streaming error: {tool_use.name}")
            yield StreamingToolChunk(
                tool_use_id=tool_use.id,
                parameter_name="error",
                chunk=f"Error: {type(e).__name__}: {e}",
                is_complete=True,
                is_valid_json=False,
            )

    def validate_tool_chain(self, tool_uses: list[ToolUse]) -> tuple[bool, str | None]:
        """Validate a chain of tool executions.

        Checks for dependencies, permissions, and resource constraints.

        Args:
            tool_uses: List of tool use requests

        Returns:
            (is_valid, error_message)
        """
        # Check concurrency limit
        if len(tool_uses) > self.max_concurrent_tools:
            return (
                False,
                f"Too many parallel tools: {len(tool_uses)} > {self.max_concurrent_tools}",
            )

        # Check all tools exist
        for tool_use in tool_uses:
            if not self._registry.get_tool(tool_use.name):
                return False, f"Unknown tool: {tool_use.name}"

        return True, None
