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

"""ATP API Client for CLI interactions"""

import os
from collections.abc import Iterator
from typing import Any

import httpx
import typer


class ATPAPIClient:
    """Client for interacting with ATP Router Service API"""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0):
        """Initialize API client.

        Args:
            base_url: Base URL of ATP Router Service
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.headers = {}

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    @classmethod
    def from_context(cls, ctx: typer.Context) -> "ATPAPIClient":
        """Create API client from Typer context.

        Args:
            ctx: Typer context containing configuration

        Returns:
            ATPAPIClient instance
        """
        # Get configuration from context or environment
        config_file = ctx.obj.get("config_file") if ctx.obj else None

        # For now, use environment variables or defaults
        base_url = os.getenv("ATP_API_URL", "http://localhost:8000")
        api_key = os.getenv("ATP_API_KEY")

        return cls(base_url=base_url, api_key=api_key)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make GET request.

        Args:
            path: API endpoint path
            params: Query parameters

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def post(
        self, path: str, json: dict[str, Any] | None = None, files: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make POST request.

        Args:
            path: API endpoint path
            json: JSON request body
            files: Files to upload

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=json, files=files, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def put(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make PUT request.

        Args:
            path: API endpoint path
            json: JSON request body

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.put(url, json=json, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def delete(self, path: str) -> dict[str, Any]:
        """Make DELETE request.

        Args:
            path: API endpoint path

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.delete(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def stream_get(self, path: str, params: dict[str, Any] | None = None) -> Iterator[str]:
        """Make streaming GET request.

        Args:
            path: API endpoint path
            params: Query parameters

        Yields:
            Response lines
        """
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", url, params=params, headers=self.headers) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    yield line
