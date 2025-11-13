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
ATP SDK Streaming Support

Streaming response handling for real-time AI interactions.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urljoin

import httpx

from .auth import AuthManager
from .config import ATPConfig
from .exceptions import StreamingError
from .models import ChatRequest, StreamingResponse

logger = logging.getLogger(__name__)


class StreamingClient:
    """Client for handling streaming responses from ATP API."""

    def __init__(self, config: ATPConfig, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager

    def stream_chat_completion(self, request: ChatRequest) -> Iterator[StreamingResponse]:
        """Stream chat completion responses synchronously."""
        url = urljoin(self.config.base_url, "/v1/chat/completions")
        headers = self._get_headers()

        # Ensure streaming is enabled
        request_data = request.dict()
        request_data["stream"] = True

        try:
            with httpx.stream(
                "POST", url, json=request_data, headers=headers, timeout=self.config.stream_timeout
            ) as response:
                if response.status_code >= 400:
                    error_data = response.read()
                    raise StreamingError(f"Streaming failed: {response.status_code}", error_data)

                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix

                        if data == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(data)
                            yield StreamingResponse(**chunk_data)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse streaming chunk: {e}")
                            continue
                        except Exception as e:
                            logger.error(f"Error processing streaming chunk: {e}")
                            continue

        except httpx.RequestError as e:
            raise StreamingError(f"Streaming request failed: {e}")
        except Exception as e:
            raise StreamingError(f"Unexpected streaming error: {e}")

    async def stream_chat_completion_async(self, request: ChatRequest) -> AsyncIterator[StreamingResponse]:
        """Stream chat completion responses asynchronously."""
        url = urljoin(self.config.base_url, "/v1/chat/completions")
        headers = await self._get_headers_async()

        # Ensure streaming is enabled
        request_data = request.dict()
        request_data["stream"] = True

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", url, json=request_data, headers=headers, timeout=self.config.stream_timeout
                ) as response:
                    if response.status_code >= 400:
                        error_data = await response.aread()
                        raise StreamingError(f"Streaming failed: {response.status_code}", error_data)

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix

                            if data == "[DONE]":
                                break

                            try:
                                chunk_data = json.loads(data)
                                yield StreamingResponse(**chunk_data)
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse streaming chunk: {e}")
                                continue
                            except Exception as e:
                                logger.error(f"Error processing streaming chunk: {e}")
                                continue

        except httpx.RequestError as e:
            raise StreamingError(f"Streaming request failed: {e}")
        except Exception as e:
            raise StreamingError(f"Unexpected streaming error: {e}")

    def _get_headers(self) -> dict:
        """Get headers for streaming requests."""
        headers = {
            "User-Agent": f"ATP-Python-SDK/{self.config.version}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        # Add authentication
        auth_header = self.auth_manager.get_auth_header()
        headers.update(auth_header)

        # Add tenant and project headers
        if self.config.tenant_id:
            headers["X-ATP-Tenant-ID"] = self.config.tenant_id

        if self.config.project_id:
            headers["X-ATP-Project-ID"] = self.config.project_id

        return headers

    async def _get_headers_async(self) -> dict:
        """Get headers for async streaming requests."""
        headers = {
            "User-Agent": f"ATP-Python-SDK/{self.config.version}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }

        # Add authentication
        auth_header = await self.auth_manager.get_auth_header_async()
        headers.update(auth_header)

        # Add tenant and project headers
        if self.config.tenant_id:
            headers["X-ATP-Tenant-ID"] = self.config.tenant_id

        if self.config.project_id:
            headers["X-ATP-Project-ID"] = self.config.project_id

        return headers


class StreamBuffer:
    """Buffer for accumulating streaming responses."""

    def __init__(self, buffer_size: int = 1000):
        self.buffer_size = buffer_size
        self.chunks = []
        self.accumulated_content = ""
        self.metadata = {}

    def add_chunk(self, chunk: StreamingResponse):
        """Add a streaming chunk to the buffer."""
        self.chunks.append(chunk)

        # Accumulate content from choices
        for choice in chunk.choices:
            if choice.delta.content:
                self.accumulated_content += choice.delta.content

        # Update metadata
        if chunk.provider:
            self.metadata["provider"] = chunk.provider

        # Maintain buffer size
        if len(self.chunks) > self.buffer_size:
            self.chunks = self.chunks[-self.buffer_size :]

    def get_accumulated_content(self) -> str:
        """Get the accumulated content from all chunks."""
        return self.accumulated_content

    def get_latest_chunk(self) -> StreamingResponse | None:
        """Get the latest chunk."""
        return self.chunks[-1] if self.chunks else None

    def is_complete(self) -> bool:
        """Check if the stream is complete."""
        if not self.chunks:
            return False

        latest_chunk = self.chunks[-1]
        for choice in latest_chunk.choices:
            if choice.finish_reason:
                return True

        return False

    def get_finish_reason(self) -> str | None:
        """Get the finish reason if stream is complete."""
        if not self.is_complete():
            return None

        latest_chunk = self.chunks[-1]
        for choice in latest_chunk.choices:
            if choice.finish_reason:
                return choice.finish_reason

        return None

    def clear(self):
        """Clear the buffer."""
        self.chunks.clear()
        self.accumulated_content = ""
        self.metadata.clear()


class StreamProcessor:
    """Advanced stream processing with callbacks and filtering."""

    def __init__(self):
        self.callbacks = []
        self.filters = []

    def add_callback(self, callback):
        """Add a callback function to be called for each chunk."""
        self.callbacks.append(callback)

    def add_filter(self, filter_func):
        """Add a filter function to process chunks."""
        self.filters.append(filter_func)

    def process_stream(self, stream: Iterator[StreamingResponse]) -> Iterator[StreamingResponse]:
        """Process a stream with callbacks and filters."""
        for chunk in stream:
            # Apply filters
            processed_chunk = chunk
            for filter_func in self.filters:
                processed_chunk = filter_func(processed_chunk)
                if processed_chunk is None:
                    break

            if processed_chunk is None:
                continue

            # Call callbacks
            for callback in self.callbacks:
                try:
                    callback(processed_chunk)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            yield processed_chunk

    async def process_stream_async(self, stream: AsyncIterator[StreamingResponse]) -> AsyncIterator[StreamingResponse]:
        """Process an async stream with callbacks and filters."""
        async for chunk in stream:
            # Apply filters
            processed_chunk = chunk
            for filter_func in self.filters:
                processed_chunk = filter_func(processed_chunk)
                if processed_chunk is None:
                    break

            if processed_chunk is None:
                continue

            # Call callbacks
            for callback in self.callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(processed_chunk)
                    else:
                        callback(processed_chunk)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            yield processed_chunk


# Utility functions for common streaming patterns


def collect_stream(stream: Iterator[StreamingResponse]) -> str:
    """Collect all content from a stream into a single string."""
    content = ""
    for chunk in stream:
        for choice in chunk.choices:
            if choice.delta.content:
                content += choice.delta.content
    return content


async def collect_stream_async(stream: AsyncIterator[StreamingResponse]) -> str:
    """Collect all content from an async stream into a single string."""
    content = ""
    async for chunk in stream:
        for choice in chunk.choices:
            if choice.delta.content:
                content += choice.delta.content
    return content


def print_stream(stream: Iterator[StreamingResponse], end: str = "\n"):
    """Print streaming content in real-time."""
    for chunk in stream:
        for choice in chunk.choices:
            if choice.delta.content:
                print(choice.delta.content, end="", flush=True)
    print(end, end="")


async def print_stream_async(stream: AsyncIterator[StreamingResponse], end: str = "\n"):
    """Print async streaming content in real-time."""
    async for chunk in stream:
        for choice in chunk.choices:
            if choice.delta.content:
                print(choice.delta.content, end="", flush=True)
    print(end, end="")
