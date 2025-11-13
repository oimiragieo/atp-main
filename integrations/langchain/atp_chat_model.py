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
ATP LangChain Chat Model Integration
This module provides LangChain ChatModel interface for ATP platform.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

import aiohttp
from pydantic import Field, validator

try:
    from langchain.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
    from langchain.chat_models.base import BaseChatModel
    from langchain.schema import (
        AIMessage,
        BaseMessage,
        ChatGeneration,
        ChatMessage,
        ChatResult,
        HumanMessage,
        SystemMessage,
    )
    from langchain.schema.output import ChatGenerationChunk
except ImportError:
    raise ImportError("LangChain is required for ATP LangChain integration. Install it with: pip install langchain") from None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ATPChatModel(BaseChatModel):
    """ATP LangChain Chat Model implementation."""

    # Configuration
    atp_base_url: str = Field(default="http://localhost:8000")
    atp_api_key: str | None = Field(default=None)
    model: str = Field(default="gpt-4")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    stop: list[str] | None = Field(default=None)

    # ATP-specific settings
    request_timeout: int = Field(default=60)
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)
    streaming: bool = Field(default=False)

    # Internal state
    _session: aiohttp.ClientSession | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    @validator("atp_base_url")
    def validate_base_url(self, v):
        """Validate base URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return v.rstrip("/")

    @property
    def _llm_type(self) -> str:
        """Return identifier of llm type."""
        return "atp-chat"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "atp_base_url": self.atp_base_url,
        }

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

    def _convert_messages_to_atp_format(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        """Convert LangChain messages to ATP format."""
        atp_messages = []

        for message in messages:
            if isinstance(message, HumanMessage):
                atp_messages.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                atp_messages.append({"role": "assistant", "content": message.content})
            elif isinstance(message, SystemMessage):
                atp_messages.append({"role": "system", "content": message.content})
            elif isinstance(message, ChatMessage):
                # Generic chat message with custom role
                atp_messages.append({"role": message.role, "content": message.content})
            else:
                # Fallback to user message
                atp_messages.append({"role": "user", "content": str(message.content)})

        return atp_messages

    def _prepare_request_data(self, messages: list[BaseMessage], **kwargs) -> dict[str, Any]:
        """Prepare request data for ATP API."""
        atp_messages = self._convert_messages_to_atp_format(messages)

        data = {
            "messages": atp_messages,
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": self.streaming,
        }

        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens

        if self.stop is not None:
            data["stop"] = self.stop

        # Override with any kwargs
        data.update(kwargs)

        return data

    def _prepare_headers(self) -> dict[str, str]:
        """Prepare request headers."""
        headers = {"Content-Type": "application/json", "User-Agent": "ATP-LangChain-Chat/1.0.0"}

        if self.atp_api_key:
            headers["Authorization"] = f"Bearer {self.atp_api_key}"

        return headers

    async def _make_request(
        self, data: dict[str, Any], stream: bool = False
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Make request to ATP API with retries."""
        session = self._get_session()
        headers = self._prepare_headers()
        url = f"{self.atp_base_url}/api/v1/chat/completions"

        for attempt in range(self.max_retries):
            try:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        if stream:
                            return self._handle_streaming_response(response)
                        else:
                            return await response.json()
                    elif response.status == 429:  # Rate limited
                        if attempt < self.max_retries - 1:
                            retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                            logger.warning(f"Rate limited, retrying after {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                    # Handle other errors
                    error_text = await response.text()
                    raise Exception(f"ATP API error {response.status}: {error_text}")

            except asyncio.TimeoutError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request timeout, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise Exception("Request timeout after all retries") from e
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed: {e}, retrying (attempt {attempt + 1})")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise

        raise Exception("All retry attempts failed")

    async def _handle_streaming_response(self, response: aiohttp.ClientResponse) -> AsyncIterator[dict[str, Any]]:
        """Handle streaming response from ATP API."""
        async for line in response.content:
            line = line.decode("utf-8").strip()
            if line.startswith("data: "):
                data_str = line[6:]  # Remove 'data: ' prefix
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    yield data
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse streaming data: {data_str}")
                    continue

    def _extract_message_from_response(self, response: dict[str, Any]) -> AIMessage:
        """Extract AI message from ATP API response."""
        try:
            choices = response.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                return AIMessage(content=content)
            return AIMessage(content="")
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to extract message from response: {e}")
            return AIMessage(content="")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat completion."""
        # Run async method in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))
        finally:
            loop.close()

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate chat completion."""
        try:
            # Prepare request
            request_data = self._prepare_request_data(messages, **kwargs)
            if stop is not None:
                request_data["stop"] = stop

            # Make request
            if self.streaming:
                # Handle streaming response
                full_content = ""
                async for chunk in await self._make_request(request_data, stream=True):
                    chunk_message = self._extract_message_from_response(chunk)
                    chunk_text = chunk_message.content
                    if chunk_text:
                        full_content += chunk_text
                        if run_manager:
                            await run_manager.on_llm_new_token(chunk_text)

                ai_message = AIMessage(content=full_content)
                generation = ChatGeneration(message=ai_message)

            else:
                # Handle non-streaming response
                response = await self._make_request(request_data, stream=False)
                ai_message = self._extract_message_from_response(response)
                generation = ChatGeneration(message=ai_message)

            # Extract usage information if available
            llm_output = {}
            if isinstance(response, dict) and "usage" in response:
                llm_output = {
                    "token_usage": response["usage"],
                    "model_name": self.model,
                }

            return ChatResult(generations=[generation], llm_output=llm_output)

        except Exception as e:
            logger.error(f"ATP Chat Model generation failed: {e}")
            # Return empty result on error
            empty_message = AIMessage(content="")
            generation = ChatGeneration(message=empty_message)
            return ChatResult(generations=[generation])
        finally:
            await self._close_session()

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream the chat model on the given messages."""
        # Run async streaming in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = self._astream(messages, stop=stop, run_manager=run_manager, **kwargs)
            while True:
                try:
                    chunk = loop.run_until_complete(async_gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Async stream the chat model on the given messages."""
        try:
            # Prepare request
            request_data = self._prepare_request_data(messages, **kwargs)
            request_data["stream"] = True  # Force streaming
            if stop is not None:
                request_data["stop"] = stop

            # Stream response
            async for chunk in await self._make_request(request_data, stream=True):
                chunk_message = self._extract_message_from_response(chunk)
                chunk_text = chunk_message.content
                if chunk_text:
                    ai_message_chunk = AIMessage(content=chunk_text)
                    generation_chunk = ChatGenerationChunk(message=ai_message_chunk)
                    if run_manager:
                        await run_manager.on_llm_new_token(chunk_text, chunk=generation_chunk)
                    yield generation_chunk

        except Exception as e:
            logger.error(f"ATP Chat Model streaming failed: {e}")
            raise
        finally:
            await self._close_session()

    def get_num_tokens(self, text: str) -> int:
        """Get the number of tokens in a text string."""
        # Simple approximation - in practice you'd use a proper tokenizer
        # This is a rough estimate: ~4 characters per token for English
        return len(text) // 4

    def get_token_ids(self, text: str) -> list[int]:
        """Get token IDs for text."""
        # This would require access to the model's tokenizer
        # For now, return a simple approximation
        return list(range(self.get_num_tokens(text)))

    @property
    def lc_secrets(self) -> dict[str, str]:
        """Return secrets to be hidden in tracing."""
        return {"atp_api_key": "ATP_API_KEY"}

    @property
    def lc_serializable(self) -> bool:
        """Return whether this model can be serialized by Langchain."""
        return True

    def __del__(self):
        """Cleanup on deletion."""
        if self._session and not self._session.closed:
            # Can't await in __del__, so we'll just close synchronously
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, schedule cleanup
                    loop.create_task(self._close_session())
                else:
                    # If no loop, run cleanup
                    loop.run_until_complete(self._close_session())
            except Exception as e:
                # Cleanup errors are expected during interpreter shutdown
                logger.debug(f"Session cleanup failed during chat model deletion: {e}")


# Factory function for easy instantiation
def create_atp_chat_model(
    base_url: str = "http://localhost:8000", api_key: str | None = None, model: str = "gpt-4", **kwargs
) -> ATPChatModel:
    """Create ATP LangChain Chat Model instance."""
    return ATPChatModel(atp_base_url=base_url, atp_api_key=api_key, model=model, **kwargs)
