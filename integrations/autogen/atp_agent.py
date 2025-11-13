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
ATP AutoGen Agent Integration
This module provides AutoGen ConversableAgent integration with ATP platform.
"""

import asyncio
import logging
from typing import Any, Optional

import aiohttp

try:
    from autogen import ConversableAgent
    from autogen.agentchat.conversable_agent import ConversableAgent as BaseConversableAgent
except ImportError:
    raise ImportError("AutoGen is required for ATP AutoGen integration. Install it with: pip install pyautogen")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ATPAutoGenAgent(ConversableAgent):
    """ATP-backed AutoGen ConversableAgent."""

    def __init__(
        self,
        name: str,
        atp_base_url: str = "http://localhost:8000",
        atp_api_key: str | None = None,
        model: str = "gpt-4",
        system_message: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        request_timeout: int = 60,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        Initialize ATP AutoGen Agent.

        Args:
            name: Agent name
            atp_base_url: ATP API base URL
            atp_api_key: ATP API key
            model: Model to use
            system_message: System message for the agent
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            request_timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            **kwargs: Additional arguments for ConversableAgent
        """
        # ATP configuration
        self.atp_base_url = atp_base_url.rstrip("/")
        self.atp_api_key = atp_api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        # HTTP session for ATP requests
        self._session: aiohttp.ClientSession | None = None

        # Configure LLM config for AutoGen
        llm_config = {
            "config_list": [
                {
                    "model": model,
                    "api_key": atp_api_key or "dummy",  # AutoGen requires this field
                    "base_url": atp_base_url,
                    "api_type": "atp",
                }
            ],
            "temperature": temperature,
            "timeout": request_timeout,
        }

        if max_tokens:
            llm_config["max_tokens"] = max_tokens

        # Initialize parent ConversableAgent
        super().__init__(name=name, system_message=system_message, llm_config=llm_config, **kwargs)

        # Override the generate_reply method to use ATP
        self._original_generate_reply = self.generate_reply
        self.generate_reply = self._atp_generate_reply

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _close_session(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _prepare_headers(self) -> dict[str, str]:
        """Prepare request headers."""
        headers = {"Content-Type": "application/json", "User-Agent": "ATP-AutoGen/1.0.0"}

        if self.atp_api_key:
            headers["Authorization"] = f"Bearer {self.atp_api_key}"

        return headers

    def _convert_messages_to_atp_format(self, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Convert AutoGen messages to ATP format."""
        atp_messages = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            # Map AutoGen roles to ATP roles
            if role == "assistant":
                atp_role = "assistant"
            elif role == "system":
                atp_role = "system"
            else:
                atp_role = "user"

            atp_messages.append({"role": atp_role, "content": str(content)})

        return atp_messages

    async def _make_atp_request(self, messages: list[dict[str, Any]]) -> str:
        """Make request to ATP API."""
        session = self._get_session()
        headers = self._prepare_headers()
        url = f"{self.atp_base_url}/api/v1/chat/completions"

        # Convert messages to ATP format
        atp_messages = self._convert_messages_to_atp_format(messages)

        # Prepare request data
        data = {"messages": atp_messages, "model": self.model, "temperature": self.temperature, "stream": False}

        if self.max_tokens:
            data["max_tokens"] = self.max_tokens

        # Make request with retries
        for attempt in range(self.max_retries):
            try:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        # Extract response content
                        choices = result.get("choices", [])
                        if choices:
                            message = choices[0].get("message", {})
                            return message.get("content", "")
                        return ""
                    elif response.status == 429:  # Rate limited
                        if attempt < self.max_retries - 1:
                            retry_after = int(response.headers.get("Retry-After", 1))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                    # Handle other errors
                    error_text = await response.text()
                    raise Exception(f"ATP API error {response.status}: {error_text}")

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

    def _atp_generate_reply(
        self, messages: list[dict] | None = None, sender: Optional["ConversableAgent"] = None, **kwargs
    ) -> str | dict | None:
        """Generate reply using ATP backend."""
        try:
            # Get messages from conversation history if not provided
            if messages is None:
                messages = self._oai_messages[sender] if sender else []

            # Add system message if configured
            if self.system_message and (not messages or messages[0].get("role") != "system"):
                system_msg = {"role": "system", "content": self.system_message}
                messages = [system_msg] + messages

            # Make async request in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(self._make_atp_request(messages))
                return response
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"ATP generate reply failed: {e}")
            return f"Error generating response: {e}"

    def update_system_message(self, system_message: str):
        """Update the agent's system message."""
        self.system_message = system_message
        logger.info(f"Updated system message for agent {self.name}")

    def get_conversation_history(self, sender: Optional["ConversableAgent"] = None) -> list[dict[str, Any]]:
        """Get conversation history with a specific sender."""
        if sender and sender in self._oai_messages:
            return self._oai_messages[sender].copy()
        return []

    def clear_conversation_history(self, sender: Optional["ConversableAgent"] = None):
        """Clear conversation history."""
        if sender:
            if sender in self._oai_messages:
                self._oai_messages[sender] = []
        else:
            self._oai_messages = {}
        logger.info(f"Cleared conversation history for agent {self.name}")

    def get_agent_info(self) -> dict[str, Any]:
        """Get agent information."""
        return {
            "name": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_message": self.system_message,
            "atp_base_url": self.atp_base_url,
            "human_input_mode": self.human_input_mode,
            "max_consecutive_auto_reply": self.max_consecutive_auto_reply,
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


# Specialized agent types
class ATPUserProxyAgent(ATPAutoGenAgent):
    """ATP-backed UserProxyAgent for human interaction."""

    def __init__(self, name: str = "UserProxy", atp_base_url: str = "http://localhost:8000", **kwargs):
        # Set human input mode for user proxy
        kwargs.setdefault("human_input_mode", "ALWAYS")
        kwargs.setdefault("max_consecutive_auto_reply", 0)
        kwargs.setdefault("code_execution_config", {"work_dir": "coding"})

        super().__init__(name=name, atp_base_url=atp_base_url, **kwargs)


class ATPAssistantAgent(ATPAutoGenAgent):
    """ATP-backed AssistantAgent for automated responses."""

    def __init__(
        self,
        name: str = "Assistant",
        atp_base_url: str = "http://localhost:8000",
        system_message: str | None = None,
        **kwargs,
    ):
        if system_message is None:
            system_message = (
                "You are a helpful AI assistant. You can help with various tasks including "
                "answering questions, writing code, analyzing data, and solving problems. "
                "When you need to write code, make sure to explain your approach and provide "
                "clear, well-commented code."
            )

        # Set automatic reply mode
        kwargs.setdefault("human_input_mode", "NEVER")
        kwargs.setdefault("max_consecutive_auto_reply", 10)

        super().__init__(name=name, atp_base_url=atp_base_url, system_message=system_message, **kwargs)


class ATPCodeReviewerAgent(ATPAutoGenAgent):
    """ATP-backed agent specialized for code review."""

    def __init__(self, name: str = "CodeReviewer", atp_base_url: str = "http://localhost:8000", **kwargs):
        system_message = (
            "You are an expert code reviewer. Your role is to:\n"
            "1. Review code for bugs, security issues, and performance problems\n"
            "2. Suggest improvements for code quality and maintainability\n"
            "3. Ensure code follows best practices and coding standards\n"
            "4. Provide constructive feedback with specific examples\n"
            "5. Highlight both positive aspects and areas for improvement\n\n"
            "Always be thorough but constructive in your reviews."
        )

        kwargs.setdefault("human_input_mode", "NEVER")
        kwargs.setdefault("max_consecutive_auto_reply", 5)

        super().__init__(name=name, atp_base_url=atp_base_url, system_message=system_message, **kwargs)


class ATPDataAnalystAgent(ATPAutoGenAgent):
    """ATP-backed agent specialized for data analysis."""

    def __init__(self, name: str = "DataAnalyst", atp_base_url: str = "http://localhost:8000", **kwargs):
        system_message = (
            "You are a data analyst expert. Your role is to:\n"
            "1. Analyze datasets and identify patterns, trends, and insights\n"
            "2. Create visualizations and statistical summaries\n"
            "3. Suggest appropriate analytical methods and techniques\n"
            "4. Interpret results and provide actionable recommendations\n"
            "5. Write Python code for data analysis using pandas, numpy, matplotlib, etc.\n\n"
            "Always explain your analytical approach and reasoning."
        )

        kwargs.setdefault("human_input_mode", "NEVER")
        kwargs.setdefault("max_consecutive_auto_reply", 8)
        kwargs.setdefault("code_execution_config", {"work_dir": "data_analysis", "use_docker": False})

        super().__init__(name=name, atp_base_url=atp_base_url, system_message=system_message, **kwargs)


# Factory functions
def create_atp_agent(
    name: str,
    agent_type: str = "assistant",
    atp_base_url: str = "http://localhost:8000",
    atp_api_key: str | None = None,
    **kwargs,
) -> ATPAutoGenAgent:
    """
    Factory function to create ATP AutoGen agents.

    Args:
        name: Agent name
        agent_type: Type of agent ("assistant", "user_proxy", "code_reviewer", "data_analyst")
        atp_base_url: ATP API base URL
        atp_api_key: ATP API key
        **kwargs: Additional arguments

    Returns:
        ATPAutoGenAgent instance
    """
    agent_classes = {
        "assistant": ATPAssistantAgent,
        "user_proxy": ATPUserProxyAgent,
        "code_reviewer": ATPCodeReviewerAgent,
        "data_analyst": ATPDataAnalystAgent,
    }

    agent_class = agent_classes.get(agent_type, ATPAssistantAgent)

    return agent_class(name=name, atp_base_url=atp_base_url, atp_api_key=atp_api_key, **kwargs)
