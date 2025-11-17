"""Bash tool with persistent session support.

Implements Claude's bash tool pattern with:
- Persistent subprocess for stateful execution
- Timeout handling (default 30s)
- Output truncation for large results
- Security sandboxing recommendations
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from router_service.tools.core.schema import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Security configuration - restrict dangerous commands
DANGEROUS_COMMANDS = {
    "rm -rf /",
    "dd if=",
    "mkfs",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777",
    "chown root",
    "sudo",
    "su -",
    "passwd",
}

# Dangerous patterns to block (case-insensitive)
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/",  # rm -rf /
    r"\bdd\s+if=",  # dd if=
    r">\s*/dev/sd",  # Write to disk device
    r"chmod\s+777",  # Overly permissive chmod
    r"eval\s+",  # eval (code injection risk)
    r"exec\s+",  # exec (code execution)
    r"\$\(.*curl.*\|.*sh\)",  # curl | sh pattern
    r"wget.*\|.*sh",  # wget | sh pattern
]


def validate_command_safety(command: str) -> tuple[bool, str]:
    """Validate command for basic safety checks.

    This implements defense-in-depth against command injection and destructive operations.
    Not a complete security solution - should be combined with proper sandboxing.

    Args:
        command: The command to validate

    Returns:
        (is_safe, reason) - True if safe, False with reason if blocked

    Security Notes:
        - This is a defense-in-depth measure, NOT a complete solution
        - Commands should still run in a sandboxed environment
        - Allowlist approach is more secure than blocklist
        - See SECURITY.md for production deployment guidelines
    """
    import re

    # Check length to prevent DoS
    if len(command) > 10000:
        return False, "Command too long (max 10000 characters)"

    # Check for null bytes (injection attempt)
    if "\x00" in command:
        return False, "Null bytes not allowed in commands"

    # Check exact matches against dangerous commands
    command_lower = command.lower().strip()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in command_lower:
            return False, f"Dangerous command detected: {dangerous}"

    # Check regex patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Command matches dangerous pattern: {pattern}"

    # Warn about sudo/su usage
    if re.search(r"\b(sudo|su)\b", command, re.IGNORECASE):
        return False, "Privilege escalation commands (sudo/su) are not allowed"

    # Check for attempts to access sensitive files
    sensitive_paths = ["/etc/shadow", "/etc/passwd", "/root/", "/var/run/secrets"]
    for path in sensitive_paths:
        if path in command:
            logger.warning(
                "Command attempts to access sensitive path",
                extra={"path": path, "command": command[:100]},
            )
            # Allow but log - might be legitimate (e.g., checking /etc/passwd for user info)

    return True, "Command validated"


class BashSession:
    """Persistent bash session for stateful command execution."""

    def __init__(self, timeout: float = 30.0, max_output_size: int = 50000):
        """Initialize bash session.

        Args:
            timeout: Command execution timeout in seconds
            max_output_size: Maximum output size before truncation
        """
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.process: asyncio.subprocess.Process | None = None
        self.session_id: str | None = None

    async def start(self) -> None:
        """Start persistent bash process."""
        if self.process:
            return  # Already started

        try:
            self.process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=os.environ.copy(),
            )
            logger.info(f"Started bash session: PID {self.process.pid}")
        except Exception as e:
            logger.exception("Failed to start bash session")
            raise RuntimeError(f"Failed to start bash: {e}") from e

    async def execute(self, command: str) -> tuple[str, int]:
        """Execute command in persistent session.

        Args:
            command: Bash command to execute

        Returns:
            (output, return_code)

        Raises:
            ValueError: If command fails safety validation
        """
        # Validate command safety before execution
        is_safe, reason = validate_command_safety(command)
        if not is_safe:
            logger.warning(
                "Blocked unsafe command",
                extra={"reason": reason, "command": command[:100]},
            )
            raise ValueError(f"Command blocked: {reason}")

        if not self.process:
            await self.start()

        try:
            # Write command with return code capture
            cmd_with_rc = f"{command}\necho $?\n"
            assert self.process.stdin is not None
            self.process.stdin.write(cmd_with_rc.encode())
            await self.process.stdin.drain()

            # Read output with timeout
            output_chunks = []
            total_size = 0

            try:
                async with asyncio.timeout(self.timeout):
                    while True:
                        assert self.process.stdout is not None
                        line = await self.process.stdout.readline()
                        if not line:
                            break

                        output_chunks.append(line)
                        total_size += len(line)

                        # Check size limit
                        if total_size > self.max_output_size:
                            logger.warning(f"Output truncated at {self.max_output_size} bytes")
                            output_chunks.append(b"\n[OUTPUT TRUNCATED - exceeded size limit]\n")
                            break

            except TimeoutError:
                logger.warning(f"Command timeout after {self.timeout}s: {command[:100]}")
                # Kill the process group to stop hung commands
                if self.process:
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                return f"[TIMEOUT after {self.timeout}s]", 124

            # Parse output and return code
            output = b"".join(output_chunks).decode("utf-8", errors="replace")
            lines = output.strip().split("\n")

            # Last line should be return code
            try:
                return_code = int(lines[-1]) if lines else 0
                output_text = "\n".join(lines[:-1]) if len(lines) > 1 else ""
            except ValueError:
                # Couldn't parse return code
                return_code = 0
                output_text = output

            return output_text, return_code

        except Exception as e:
            logger.exception(f"Error executing command: {command[:100]}")
            raise RuntimeError(f"Execution failed: {e}") from e

    async def restart(self) -> None:
        """Restart the bash session."""
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        """Stop the bash session."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                logger.warning(f"Error stopping bash session: {e}")
            finally:
                self.process = None
                logger.info("Stopped bash session")


# Global session manager (one session per request context)
_sessions: dict[str, BashSession] = {}


async def bash_tool_handler(args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
    """Execute bash commands in persistent session.

    Args:
        args: Tool arguments (command, restart)
        context: Execution context (session_id, user_id, etc.)

    Returns:
        ToolResult with command output

    Security Notes:
        - Commands are validated against dangerous patterns before execution
        - Output is truncated to prevent memory exhaustion
        - Timeouts prevent hung processes
        - This is defense-in-depth - deploy in sandboxed environment for production
    """
    command = args.get("command")
    restart = args.get("restart", False)

    # Check if bash tool is enabled (default: disabled in production)
    bash_enabled = os.getenv("ROUTER_ENABLE_BASH_TOOL", "0") == "1"
    if not bash_enabled and not context.get("allow_bash", False):
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content="Error: Bash tool is disabled. Set ROUTER_ENABLE_BASH_TOOL=1 to enable (NOT recommended in production without sandboxing)",
            is_error=True,
        )

    # Get or create session
    session_id = context.get("session_id", "default")
    if session_id not in _sessions:
        _sessions[session_id] = BashSession()

    session = _sessions[session_id]

    # Handle restart
    if restart:
        await session.restart()
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content="Bash session restarted",
            is_error=False,
        )

    # Execute command
    if not command:
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content="Error: No command provided",
            is_error=True,
        )

    try:
        output, return_code = await session.execute(command)

        # Format output
        result = output
        if return_code != 0:
            result += f"\n\n[Exit code: {return_code}]"

        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=result,
            is_error=return_code != 0,
        )

    except ValueError as e:
        # Command validation failure
        logger.warning(f"Command validation failed: {e}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Command blocked for security reasons: {e}",
            is_error=True,
        )
    except Exception as e:
        logger.exception(f"Bash execution error: {command[:100]}")
        return ToolResult(
            tool_use_id=context.get("tool_use_id", ""),
            content=f"Error executing command: {e}",
            is_error=True,
        )


# Tool definition
BASH_TOOL = ToolDefinition(
    name="bash",
    description="""Execute bash commands in a persistent shell session.

The bash tool maintains state between commands, allowing you to:
- Navigate directories with cd (persists across commands)
- Set environment variables (available in subsequent commands)
- Create files and reference them in later commands
- Run multi-step workflows

Use this tool when you need to:
- Execute shell commands to inspect the system
- Run build scripts, tests, or deployment commands
- Manipulate files and directories
- Query system information

Important limitations:
- Interactive commands (vim, nano, password prompts) are not supported
- Commands timeout after 30 seconds by default
- Output is truncated if it exceeds 50KB

Security considerations:
- Disabled by default (set ROUTER_ENABLE_BASH_TOOL=1 to enable)
- Commands are validated against dangerous patterns before execution
- All commands run in the context of the API service
- Deploy in sandboxed environment (Docker/Kubernetes) for production
- Dangerous commands (rm -rf /, dd, sudo, etc.) are blocked
- See SECURITY.md and AUDIT_REPORT.md for deployment guidelines

⚠️ WARNING: This tool allows arbitrary command execution.
   Only enable in trusted, sandboxed environments.""",
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute",
            },
            "restart": {
                "type": "boolean",
                "description": "Set to true to restart the bash session (clears state)",
                "default": False,
            },
        },
        "required": [],  # command not required if restarting
    },
)
