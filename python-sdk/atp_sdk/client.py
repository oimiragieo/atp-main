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
ATP Client Implementation

Main client classes for synchronous and asynchronous ATP API interactions.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urljoin

import httpx

from .auth import AuthManager
from .config import ATPConfig
from .exceptions import (
    ATPError,
    AuthenticationError,
    InsufficientCreditsError,
    ModelNotFoundError,
    RateLimitError,
)
from .models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CostInfo,
    ModelInfo,
    PolicyInfo,
    ProviderInfo,
    StreamingResponse,
    UsageStats,
)
from .streaming import StreamingClient

logger = logging.getLogger(__name__)


class ATPClient:
    """
    Synchronous ATP client for AI model routing and management.

    This client provides a simple interface for interacting with the ATP platform,
    including chat completions, model management, cost tracking, and more.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        config: ATPConfig | None = None,
    ):
        """
        Initialize the ATP client.

        Args:
            api_key: ATP API key for authentication
            base_url: Base URL for the ATP API
            tenant_id: Tenant ID for multi-tenant environments
            project_id: Project ID for cost attribution
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            config: Optional configuration object
        """
        self.config = config or ATPConfig()

        # Override config with explicit parameters
        if api_key:
            self.config.api_key = api_key
        if base_url:
            self.config.base_url = base_url
        if tenant_id:
            self.config.tenant_id = tenant_id
        if project_id:
            self.config.project_id = project_id
        if timeout:
            self.config.timeout = timeout
        if max_retries:
            self.config.max_retries = max_retries

        # Initialize auth manager
        self.auth = AuthManager(self.config)

        # Initialize HTTP client
        self.client = httpx.Client(
            base_url=self.config.base_url, timeout=self.config.timeout, headers=self._get_default_headers()
        )

        # Initialize streaming client
        self.streaming = StreamingClient(self.config, self.auth)

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "User-Agent": f"ATP-Python-SDK/{self.config.version}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.config.tenant_id:
            headers["X-ATP-Tenant-ID"] = self.config.tenant_id

        if self.config.project_id:
            headers["X-ATP-Project-ID"] = self.config.project_id

        return headers

    def _make_request(self, method: str, endpoint: str, data: dict | None = None, params: dict | None = None) -> dict:
        """Make an authenticated HTTP request."""
        url = urljoin(self.config.base_url, endpoint)
        headers = self._get_default_headers()

        # Add authentication
        auth_header = self.auth.get_auth_header()
        headers.update(auth_header)

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.request(method=method, url=url, json=data, params=params, headers=headers)

                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key or expired token")
                elif response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded")
                elif response.status_code == 404:
                    raise ModelNotFoundError("Requested model not found")
                elif response.status_code == 402:
                    raise InsufficientCreditsError("Insufficient credits")
                elif response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    raise ATPError(f"API error: {response.status_code}", error_data)

                return response.json()

            except httpx.RequestError as e:
                if attempt == self.config.max_retries:
                    raise ATPError(f"Request failed after {self.config.max_retries} retries: {e}")

                # Exponential backoff
                wait_time = 2**attempt
                logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                asyncio.sleep(wait_time)

    def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse | Iterator[StreamingResponse]:
        """
        Create a chat completion.

        Args:
            messages: List of chat messages
            model: Specific model to use (optional, ATP will choose optimal)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional model-specific parameters

        Returns:
            ChatResponse for non-streaming, Iterator for streaming
        """
        request = ChatRequest(
            messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, stream=stream, **kwargs
        )

        if stream:
            return self.streaming.stream_chat_completion(request)

        response_data = self._make_request("POST", "/v1/chat/completions", request.dict())
        return ChatResponse(**response_data)

    def list_models(self) -> list[ModelInfo]:
        """
        List available models.

        Returns:
            List of available models with their capabilities
        """
        response_data = self._make_request("GET", "/v1/models")
        return [ModelInfo(**model) for model in response_data["models"]]

    def get_model_info(self, model_id: str) -> ModelInfo:
        """
        Get detailed information about a specific model.

        Args:
            model_id: The model identifier

        Returns:
            Detailed model information
        """
        response_data = self._make_request("GET", f"/v1/models/{model_id}")
        return ModelInfo(**response_data)

    def list_providers(self) -> list[ProviderInfo]:
        """
        List available providers.

        Returns:
            List of available providers and their status
        """
        response_data = self._make_request("GET", "/v1/providers")
        return [ProviderInfo(**provider) for provider in response_data["providers"]]

    def get_cost_info(self, start_date: str | None = None, end_date: str | None = None) -> CostInfo:
        """
        Get cost information for the current tenant/project.

        Args:
            start_date: Start date for cost query (ISO format)
            end_date: End date for cost query (ISO format)

        Returns:
            Cost information and breakdown
        """
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response_data = self._make_request("GET", "/v1/cost", params=params)
        return CostInfo(**response_data)

    def get_usage_stats(self, start_date: str | None = None, end_date: str | None = None) -> UsageStats:
        """
        Get usage statistics.

        Args:
            start_date: Start date for usage query (ISO format)
            end_date: End date for usage query (ISO format)

        Returns:
            Usage statistics and metrics
        """
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response_data = self._make_request("GET", "/v1/usage", params=params)
        return UsageStats(**response_data)

    def list_policies(self) -> list[PolicyInfo]:
        """
        List active policies for the current tenant.

        Returns:
            List of active policies
        """
        response_data = self._make_request("GET", "/v1/policies")
        return [PolicyInfo(**policy) for policy in response_data["policies"]]

    def create_policy(self, policy_data: dict) -> PolicyInfo:
        """
        Create a new policy.

        Args:
            policy_data: Policy configuration

        Returns:
            Created policy information
        """
        response_data = self._make_request("POST", "/v1/policies", policy_data)
        return PolicyInfo(**response_data)

    def update_policy(self, policy_id: str, policy_data: dict) -> PolicyInfo:
        """
        Update an existing policy.

        Args:
            policy_id: Policy identifier
            policy_data: Updated policy configuration

        Returns:
            Updated policy information
        """
        response_data = self._make_request("PUT", f"/v1/policies/{policy_id}", policy_data)
        return PolicyInfo(**response_data)

    def delete_policy(self, policy_id: str) -> bool:
        """
        Delete a policy.

        Args:
            policy_id: Policy identifier

        Returns:
            True if successful
        """
        self._make_request("DELETE", f"/v1/policies/{policy_id}")
        return True

    def health_check(self) -> dict:
        """
        Check the health of the ATP service.

        Returns:
            Health status information
        """
        return self._make_request("GET", "/health")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()


class AsyncATPClient:
    """
    Asynchronous ATP client for AI model routing and management.

    This client provides async/await support for high-performance applications
    that need to handle many concurrent requests.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        config: ATPConfig | None = None,
    ):
        """
        Initialize the async ATP client.

        Args:
            api_key: ATP API key for authentication
            base_url: Base URL for the ATP API
            tenant_id: Tenant ID for multi-tenant environments
            project_id: Project ID for cost attribution
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            config: Optional configuration object
        """
        self.config = config or ATPConfig()

        # Override config with explicit parameters
        if api_key:
            self.config.api_key = api_key
        if base_url:
            self.config.base_url = base_url
        if tenant_id:
            self.config.tenant_id = tenant_id
        if project_id:
            self.config.project_id = project_id
        if timeout:
            self.config.timeout = timeout
        if max_retries:
            self.config.max_retries = max_retries

        # Initialize auth manager
        self.auth = AuthManager(self.config)

        # Initialize async HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url, timeout=self.config.timeout, headers=self._get_default_headers()
        )

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "User-Agent": f"ATP-Python-SDK/{self.config.version}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.config.tenant_id:
            headers["X-ATP-Tenant-ID"] = self.config.tenant_id

        if self.config.project_id:
            headers["X-ATP-Project-ID"] = self.config.project_id

        return headers

    async def _make_request(
        self, method: str, endpoint: str, data: dict | None = None, params: dict | None = None
    ) -> dict:
        """Make an authenticated HTTP request."""
        url = urljoin(self.config.base_url, endpoint)
        headers = self._get_default_headers()

        # Add authentication
        auth_header = await self.auth.get_auth_header_async()
        headers.update(auth_header)

        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.request(method=method, url=url, json=data, params=params, headers=headers)

                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key or expired token")
                elif response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded")
                elif response.status_code == 404:
                    raise ModelNotFoundError("Requested model not found")
                elif response.status_code == 402:
                    raise InsufficientCreditsError("Insufficient credits")
                elif response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    raise ATPError(f"API error: {response.status_code}", error_data)

                return response.json()

            except httpx.RequestError as e:
                if attempt == self.config.max_retries:
                    raise ATPError(f"Request failed after {self.config.max_retries} retries: {e}")

                # Exponential backoff
                wait_time = 2**attempt
                logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse | AsyncIterator[StreamingResponse]:
        """
        Create a chat completion asynchronously.

        Args:
            messages: List of chat messages
            model: Specific model to use (optional, ATP will choose optimal)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional model-specific parameters

        Returns:
            ChatResponse for non-streaming, AsyncIterator for streaming
        """
        request = ChatRequest(
            messages=messages, model=model, temperature=temperature, max_tokens=max_tokens, stream=stream, **kwargs
        )

        if stream:
            return self._stream_chat_completion(request)

        response_data = await self._make_request("POST", "/v1/chat/completions", request.dict())
        return ChatResponse(**response_data)

    async def _stream_chat_completion(self, request: ChatRequest) -> AsyncIterator[StreamingResponse]:
        """Stream chat completion responses."""
        url = urljoin(self.config.base_url, "/v1/chat/completions")
        headers = self._get_default_headers()

        # Add authentication
        auth_header = await self.auth.get_auth_header_async()
        headers.update(auth_header)

        async with self.client.stream("POST", url, json=request.dict(), headers=headers) as response:
            if response.status_code >= 400:
                error_data = await response.aread()
                raise ATPError(f"Streaming error: {response.status_code}", error_data)

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        yield StreamingResponse(**chunk_data)
                    except json.JSONDecodeError:
                        continue

    async def list_models(self) -> list[ModelInfo]:
        """List available models asynchronously."""
        response_data = await self._make_request("GET", "/v1/models")
        return [ModelInfo(**model) for model in response_data["models"]]

    async def get_model_info(self, model_id: str) -> ModelInfo:
        """Get detailed information about a specific model asynchronously."""
        response_data = await self._make_request("GET", f"/v1/models/{model_id}")
        return ModelInfo(**response_data)

    async def list_providers(self) -> list[ProviderInfo]:
        """List available providers asynchronously."""
        response_data = await self._make_request("GET", "/v1/providers")
        return [ProviderInfo(**provider) for provider in response_data["providers"]]

    async def get_cost_info(self, start_date: str | None = None, end_date: str | None = None) -> CostInfo:
        """Get cost information asynchronously."""
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response_data = await self._make_request("GET", "/v1/cost", params=params)
        return CostInfo(**response_data)

    async def get_usage_stats(self, start_date: str | None = None, end_date: str | None = None) -> UsageStats:
        """Get usage statistics asynchronously."""
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response_data = await self._make_request("GET", "/v1/usage", params=params)
        return UsageStats(**response_data)

    async def health_check(self) -> dict:
        """Check the health of the ATP service asynchronously."""
        return await self._make_request("GET", "/health")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the async HTTP client."""
        await self.client.aclose()
