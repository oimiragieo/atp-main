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
"""
ATP AutoGen Code Execution Integration
This module provides code execution capabilities using ATP's sandboxed environments.
"""

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ATPCodeExecutor:
    """ATP-backed code executor for AutoGen agents."""

    def __init__(
        self,
        atp_base_url: str = "http://localhost:8000",
        atp_api_key: str | None = None,
        work_dir: str = "code_execution",
        timeout: int = 30,
        max_retries: int = 3,
        allowed_languages: list[str] | None = None,
    ):
        """
        Initialize ATP Code Executor.

        Args:
            atp_base_url: ATP API base URL
            atp_api_key: ATP API key
            work_dir: Working directory for code execution
            timeout: Execution timeout in seconds
            max_retries: Maximum retry attempts
            allowed_languages: List of allowed programming languages
        """
        self.atp_base_url = atp_base_url.rstrip("/")
        self.atp_api_key = atp_api_key
        self.work_dir = work_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.allowed_languages = allowed_languages or ["python", "javascript", "bash", "sql", "r"]

        # HTTP session for ATP requests
        self._session: aiohttp.ClientSession | None = None

        # Execution history
        self._execution_history: list[dict[str, Any]] = []

        # Create work directory
        os.makedirs(work_dir, exist_ok=True)

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout + 10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _close_session(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _prepare_headers(self) -> dict[str, str]:
        """Prepare request headers."""
        headers = {"Content-Type": "application/json", "User-Agent": "ATP-AutoGen-CodeExecutor/1.0.0"}

        if self.atp_api_key:
            headers["Authorization"] = f"Bearer {self.atp_api_key}"

        return headers

    def _extract_code_blocks(self, text: str) -> list[dict[str, str]]:
        """Extract code blocks from text."""
        import re

        # Pattern to match code blocks with language specification
        pattern = r"```(\w+)?\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        code_blocks = []
        for language, code in matches:
            # Default to python if no language specified
            if not language:
                language = "python"

            code_blocks.append({"language": language.lower(), "code": code.strip()})

        # If no code blocks found, try to detect inline code
        if not code_blocks:
            # Look for lines that might be code (simple heuristic)
            lines = text.split("\n")
            code_lines = []

            for line in lines:
                line = line.strip()
                # Simple heuristics for code detection
                if (
                    line.startswith(("def ", "class ", "import ", "from "))
                    or "=" in line
                    and ("print(" in line or "return " in line)
                    or line.startswith(("if ", "for ", "while ", "try:"))
                ):
                    code_lines.append(line)

            if code_lines:
                code_blocks.append({"language": "python", "code": "\n".join(code_lines)})

        return code_blocks

    async def _execute_code_via_atp(self, code: str, language: str, execution_id: str | None = None) -> dict[str, Any]:
        """Execute code via ATP sandbox API."""
        session = self._get_session()
        headers = self._prepare_headers()
        url = f"{self.atp_base_url}/api/v1/sandbox/execute"

        # Prepare execution request
        data = {
            "code": code,
            "language": language,
            "timeout": self.timeout,
            "execution_id": execution_id or f"autogen_{int(time.time())}",
        }

        # Make request with retries
        for attempt in range(self.max_retries):
            try:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    elif response.status == 429:  # Rate limited
                        if attempt < self.max_retries - 1:
                            retry_after = int(response.headers.get("Retry-After", 1))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                    # Handle other errors
                    error_text = await response.text()
                    raise Exception(f"ATP Sandbox API error {response.status}: {error_text}")

            except asyncio.TimeoutError:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request timeout, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise Exception("Request timeout after all retries")
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed: {e}, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise

        raise Exception("All retry attempts failed")

    def execute_code_blocks(self, message: str) -> str:
        """Execute code blocks found in a message."""
        # Extract code blocks
        code_blocks = self._extract_code_blocks(message)

        if not code_blocks:
            return "No executable code blocks found in the message."

        results = []

        for i, block in enumerate(code_blocks):
            language = block["language"]
            code = block["code"]

            # Check if language is allowed
            if language not in self.allowed_languages:
                results.append(f"Code block {i + 1} ({language}): Language not allowed")
                continue

            try:
                # Execute code synchronously
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self._execute_code_via_atp(code, language))

                    # Format result
                    execution_result = self._format_execution_result(result, i + 1, language)
                    results.append(execution_result)

                    # Store in history
                    self._execution_history.append(
                        {"timestamp": time.time(), "language": language, "code": code, "result": result}
                    )

                finally:
                    loop.close()

            except Exception as e:
                error_msg = f"Code block {i + 1} ({language}): Execution failed - {str(e)}"
                results.append(error_msg)
                logger.error(error_msg)

        return "\n\n".join(results)

    def _format_execution_result(self, result: dict[str, Any], block_num: int, language: str) -> str:
        """Format execution result for display."""
        output = f"Code block {block_num} ({language}) execution result:\n"

        # Extract result components
        success = result.get("success", False)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        return_value = result.get("return_value")
        execution_time = result.get("execution_time", 0)

        if success:
            output += f"✅ Executed successfully in {execution_time:.3f}s\n"

            if stdout:
                output += f"Output:\n{stdout}\n"

            if return_value is not None:
                output += f"Return value: {return_value}\n"

        else:
            output += "❌ Execution failed\n"

            if stderr:
                output += f"Error:\n{stderr}\n"

            if stdout:
                output += f"Output before error:\n{stdout}\n"

        return output.strip()

    def save_code_to_file(self, code: str, filename: str, language: str = "python") -> str:
        """Save code to a file in the work directory."""
        # Determine file extension
        extensions = {"python": ".py", "javascript": ".js", "bash": ".sh", "sql": ".sql", "r": ".r"}

        ext = extensions.get(language, ".txt")
        if not filename.endswith(ext):
            filename += ext

        filepath = os.path.join(self.work_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            logger.info(f"Saved code to {filepath}")
            return f"Code saved to {filepath}"

        except Exception as e:
            error_msg = f"Failed to save code to {filepath}: {e}"
            logger.error(error_msg)
            return error_msg

    def load_code_from_file(self, filename: str) -> str:
        """Load code from a file in the work directory."""
        filepath = os.path.join(self.work_dir, filename)

        try:
            with open(filepath, encoding="utf-8") as f:
                code = f.read()

            logger.info(f"Loaded code from {filepath}")
            return code

        except Exception as e:
            error_msg = f"Failed to load code from {filepath}: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def list_files(self) -> list[str]:
        """List files in the work directory."""
        try:
            files = os.listdir(self.work_dir)
            return sorted(files)
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []

    def get_execution_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get execution history."""
        history = self._execution_history.copy()
        if limit:
            history = history[-limit:]
        return history

    def clear_execution_history(self):
        """Clear execution history."""
        self._execution_history = []
        logger.info("Cleared execution history")

    def get_execution_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        if not self._execution_history:
            return {"total_executions": 0}

        # Count by language
        language_counts = {}
        success_counts = {}
        total_time = 0

        for execution in self._execution_history:
            language = execution["language"]
            success = execution["result"].get("success", False)
            exec_time = execution["result"].get("execution_time", 0)

            language_counts[language] = language_counts.get(language, 0) + 1
            success_counts[language] = success_counts.get(language, 0) + (1 if success else 0)
            total_time += exec_time

        # Calculate success rates
        success_rates = {}
        for language in language_counts:
            success_rates[language] = success_counts[language] / language_counts[language]

        return {
            "total_executions": len(self._execution_history),
            "language_counts": language_counts,
            "success_rates": success_rates,
            "total_execution_time": total_time,
            "average_execution_time": total_time / len(self._execution_history),
        }

    def create_execution_config(self) -> dict[str, Any]:
        """Create AutoGen-compatible code execution config."""
        return {
            "work_dir": self.work_dir,
            "use_docker": False,  # We use ATP's sandbox instead
            "timeout": self.timeout,
            "last_n_messages": 3,
            "executor": self,  # Custom executor
        }

    def __del__(self):
        """Cleanup on deletion."""
        if self._session and not self._session.closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._close_session())
                else:
                    loop.run_until_complete(self._close_session())
            except Exception:
                pass


# Integration with AutoGen's code execution system
class AutoGenCodeExecutionWrapper:
    """Wrapper to integrate ATP code executor with AutoGen's execution system."""

    def __init__(self, atp_executor: ATPCodeExecutor):
        self.atp_executor = atp_executor

    def execute_code_blocks(self, code_blocks: list[dict[str, str]]) -> str:
        """Execute code blocks in AutoGen format."""
        results = []

        for i, block in enumerate(code_blocks):
            language = block.get("language", "python")
            code = block.get("code", "")

            if not code.strip():
                continue

            try:
                # Use ATP executor
                result_text = self.atp_executor.execute_code_blocks(f"```{language}\n{code}\n```")
                results.append(result_text)

            except Exception as e:
                error_msg = f"Code block {i + 1} execution failed: {e}"
                results.append(error_msg)

        return "\n\n".join(results) if results else "No code executed."


# Factory function
def create_atp_code_executor(
    atp_base_url: str = "http://localhost:8000",
    atp_api_key: str | None = None,
    work_dir: str = "atp_code_execution",
    **kwargs,
) -> ATPCodeExecutor:
    """
    Factory function to create ATP Code Executor.

    Args:
        atp_base_url: ATP API base URL
        atp_api_key: ATP API key
        work_dir: Working directory
        **kwargs: Additional arguments

    Returns:
        ATPCodeExecutor instance
    """
    return ATPCodeExecutor(atp_base_url=atp_base_url, atp_api_key=atp_api_key, work_dir=work_dir, **kwargs)
