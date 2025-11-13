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
ATP LangChain Memory Integration
This module provides LangChain memory integration with ATP's memory gateway.
"""

import asyncio
import logging
import time
from typing import Any

import aiohttp
from pydantic import Field, validator

try:
    from langchain.memory.chat_memory import BaseChatMemory
    from langchain.memory.utils import get_buffer_string
    from langchain.schema import AIMessage, BaseMessage, HumanMessage, SystemMessage
except ImportError:
    raise ImportError("LangChain is required for ATP LangChain integration. Install it with: pip install langchain")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ATPMemoryStore(BaseChatMemory):
    """ATP Memory Store integration with LangChain."""

    # Configuration
    atp_memory_url: str = Field(default="http://localhost:8001")
    atp_api_key: str | None = Field(default=None)
    session_id: str = Field(default="default")
    namespace: str = Field(default="langchain")

    # Memory settings
    max_token_limit: int | None = Field(default=4000)
    return_messages: bool = Field(default=True)

    # ATP-specific settings
    request_timeout: int = Field(default=30)
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)

    # Internal state
    _session: aiohttp.ClientSession | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    @validator("atp_memory_url")
    def validate_memory_url(self, v):
        """Validate memory URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Memory URL must start with http:// or https://")
        return v.rstrip("/")

    @property
    def memory_variables(self) -> list[str]:
        """Return memory variables."""
        return [self.memory_key]

    @property
    def memory_key(self) -> str:
        """Return the memory key."""
        return "history"

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
        headers = {"Content-Type": "application/json", "User-Agent": "ATP-LangChain-Memory/1.0.0"}

        if self.atp_api_key:
            headers["Authorization"] = f"Bearer {self.atp_api_key}"

        return headers

    def _convert_message_to_atp_format(self, message: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message to ATP memory format."""
        if isinstance(message, HumanMessage):
            return {
                "role": "user",
                "content": message.content,
                "timestamp": time.time(),
                "metadata": getattr(message, "additional_kwargs", {}),
            }
        elif isinstance(message, AIMessage):
            return {
                "role": "assistant",
                "content": message.content,
                "timestamp": time.time(),
                "metadata": getattr(message, "additional_kwargs", {}),
            }
        elif isinstance(message, SystemMessage):
            return {
                "role": "system",
                "content": message.content,
                "timestamp": time.time(),
                "metadata": getattr(message, "additional_kwargs", {}),
            }
        else:
            return {"role": "user", "content": str(message.content), "timestamp": time.time(), "metadata": {}}

    def _convert_atp_message_to_langchain(self, atp_message: dict[str, Any]) -> BaseMessage:
        """Convert ATP memory message to LangChain format."""
        role = atp_message.get("role", "user")
        content = atp_message.get("content", "")
        metadata = atp_message.get("metadata", {})

        if role == "user":
            return HumanMessage(content=content, additional_kwargs=metadata)
        elif role == "assistant":
            return AIMessage(content=content, additional_kwargs=metadata)
        elif role == "system":
            return SystemMessage(content=content, additional_kwargs=metadata)
        else:
            return HumanMessage(content=content, additional_kwargs=metadata)

    async def _make_request(self, method: str, endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make request to ATP Memory Gateway with retries."""
        session = self._get_session()
        headers = self._prepare_headers()
        url = f"{self.atp_memory_url}{endpoint}"

        for attempt in range(self.max_retries):
            try:
                async with session.request(method, url, json=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limited
                        if attempt < self.max_retries - 1:
                            retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                    # Handle other errors
                    error_text = await response.text()
                    raise Exception(f"ATP Memory API error {response.status}: {error_text}")

            except asyncio.TimeoutError:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request timeout, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise Exception("Request timeout after all retries")
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed: {e}, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise

        raise Exception("All retry attempts failed")

    async def _aget_messages(self) -> list[BaseMessage]:
        """Async get messages from ATP memory."""
        try:
            endpoint = f"/api/v1/memory/{self.namespace}/{self.session_id}/messages"
            response = await self._make_request("GET", endpoint)

            messages = []
            for atp_message in response.get("messages", []):
                langchain_message = self._convert_atp_message_to_langchain(atp_message)
                messages.append(langchain_message)

            return messages

        except Exception as e:
            logger.error(f"Failed to get messages from ATP memory: {e}")
            return []
        finally:
            await self._close_session()

    async def _astore_message(self, message: BaseMessage):
        """Async store message in ATP memory."""
        try:
            atp_message = self._convert_message_to_atp_format(message)
            endpoint = f"/api/v1/memory/{self.namespace}/{self.session_id}/messages"

            await self._make_request("POST", endpoint, {"message": atp_message})

        except Exception as e:
            logger.error(f"Failed to store message in ATP memory: {e}")
        finally:
            await self._close_session()

    async def _aclear_messages(self):
        """Async clear all messages from ATP memory."""
        try:
            endpoint = f"/api/v1/memory/{self.namespace}/{self.session_id}/messages"
            await self._make_request("DELETE", endpoint)

        except Exception as e:
            logger.error(f"Failed to clear messages from ATP memory: {e}")
        finally:
            await self._close_session()

    def _get_messages(self) -> list[BaseMessage]:
        """Get messages from ATP memory (sync wrapper)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._aget_messages())
        finally:
            loop.close()

    def _store_message(self, message: BaseMessage):
        """Store message in ATP memory (sync wrapper)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._astore_message(message))
        finally:
            loop.close()

    def _clear_messages(self):
        """Clear all messages from ATP memory (sync wrapper)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._aclear_messages())
        finally:
            loop.close()

    @property
    def chat_memory(self) -> list[BaseMessage]:
        """Get chat memory messages."""
        return self._get_messages()

    def add_user_message(self, message: str) -> None:
        """Add a user message to memory."""
        user_message = HumanMessage(content=message)
        self._store_message(user_message)

    def add_ai_message(self, message: str) -> None:
        """Add an AI message to memory."""
        ai_message = AIMessage(content=message)
        self._store_message(ai_message)

    def add_message(self, message: BaseMessage) -> None:
        """Add a message to memory."""
        self._store_message(message)

    def clear(self) -> None:
        """Clear memory contents."""
        self._clear_messages()

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Load memory variables."""
        messages = self._get_messages()

        if self.return_messages:
            return {self.memory_key: messages}
        else:
            # Return as string buffer
            buffer = get_buffer_string(messages)
            return {self.memory_key: buffer}

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, str]) -> None:
        """Save context to memory."""
        # Extract input message
        input_key = list(inputs.keys())[0] if inputs else "input"
        input_text = inputs.get(input_key, "")
        if input_text:
            self.add_user_message(input_text)

        # Extract output message
        output_key = list(outputs.keys())[0] if outputs else "output"
        output_text = outputs.get(output_key, "")
        if output_text:
            self.add_ai_message(output_text)

    async def asave_context(self, inputs: dict[str, Any], outputs: dict[str, str]) -> None:
        """Async save context to memory."""
        # Extract input message
        input_key = list(inputs.keys())[0] if inputs else "input"
        input_text = inputs.get(input_key, "")
        if input_text:
            user_message = HumanMessage(content=input_text)
            await self._astore_message(user_message)

        # Extract output message
        output_key = list(outputs.keys())[0] if outputs else "output"
        output_text = outputs.get(output_key, "")
        if output_text:
            ai_message = AIMessage(content=output_text)
            await self._astore_message(ai_message)

    async def aload_memory_variables(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Async load memory variables."""
        messages = await self._aget_messages()

        if self.return_messages:
            return {self.memory_key: messages}
        else:
            # Return as string buffer
            buffer = get_buffer_string(messages)
            return {self.memory_key: buffer}

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation."""
        messages = self._get_messages()
        if not messages:
            return "No conversation history."

        # Simple summary - in practice you might use the LLM to summarize
        summary_parts = []
        for message in messages[-10:]:  # Last 10 messages
            if isinstance(message, HumanMessage):
                summary_parts.append(f"User: {message.content[:100]}...")
            elif isinstance(message, AIMessage):
                summary_parts.append(f"Assistant: {message.content[:100]}...")

        return "\n".join(summary_parts)

    async def aget_conversation_summary(self) -> str:
        """Async get a summary of the conversation."""
        messages = await self._aget_messages()
        if not messages:
            return "No conversation history."

        # Simple summary - in practice you might use the LLM to summarize
        summary_parts = []
        for message in messages[-10:]:  # Last 10 messages
            if isinstance(message, HumanMessage):
                summary_parts.append(f"User: {message.content[:100]}...")
            elif isinstance(message, AIMessage):
                summary_parts.append(f"Assistant: {message.content[:100]}...")

        return "\n".join(summary_parts)

    def prune_messages(self, max_tokens: int | None = None) -> None:
        """Prune messages to stay within token limit."""
        if max_tokens is None:
            max_tokens = self.max_token_limit

        if max_tokens is None:
            return

        messages = self._get_messages()
        if not messages:
            return

        # Simple token counting (approximate)
        total_tokens = sum(len(msg.content) // 4 for msg in messages)

        # Remove oldest messages until under limit
        while total_tokens > max_tokens and len(messages) > 1:
            removed_message = messages.pop(0)
            total_tokens -= len(removed_message.content) // 4

        # Clear and re-add remaining messages
        self._clear_messages()
        for message in messages:
            self._store_message(message)

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


# Factory function for easy instantiation
def create_atp_memory_store(
    memory_url: str = "http://localhost:8001",
    api_key: str | None = None,
    session_id: str = "default",
    namespace: str = "langchain",
    **kwargs,
) -> ATPMemoryStore:
    """Create ATP Memory Store instance."""
    return ATPMemoryStore(
        atp_memory_url=memory_url, atp_api_key=api_key, session_id=session_id, namespace=namespace, **kwargs
    )
