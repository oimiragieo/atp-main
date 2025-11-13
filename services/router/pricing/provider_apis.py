"""Provider API integrations for real-time pricing data."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class PricingAPIError(Exception):
    """Base exception for pricing API errors."""

    pass


class PricingAPIRateLimitError(PricingAPIError):
    """Exception for rate limit errors."""

    pass


class PricingAPITimeoutError(PricingAPIError):
    """Exception for timeout errors."""

    pass


class BasePricingAPI(ABC):
    """Base class for provider pricing APIs."""

    def __init__(
        self, api_key: str | None = None, timeout: float = 30.0, retry_attempts: int = 3, retry_delay: float = 1.0
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        # Rate limiting
        self._last_request_time = 0.0
        self._min_request_interval = 1.0  # Minimum seconds between requests

    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - time_since_last)

        self._last_request_time = time.time()

    async def _make_request(
        self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic."""
        await self._rate_limit()

        for attempt in range(self.retry_attempts):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 429:  # Rate limited
                            retry_after = int(response.headers.get("Retry-After", 60))
                            raise PricingAPIRateLimitError(f"Rate limited, retry after {retry_after}s")

                        response.raise_for_status()
                        return await response.json()

            except asyncio.TimeoutError:
                if attempt == self.retry_attempts - 1:
                    raise PricingAPITimeoutError(f"Request timed out after {self.timeout}s")
                await asyncio.sleep(self.retry_delay * (2**attempt))

            except aiohttp.ClientError as e:
                if attempt == self.retry_attempts - 1:
                    raise PricingAPIError(f"Request failed: {e}")
                await asyncio.sleep(self.retry_delay * (2**attempt))

        raise PricingAPIError("Max retry attempts exceeded")

    @abstractmethod
    async def get_model_pricing(self, model_name: str) -> dict[str, float]:
        """Get pricing for a specific model."""
        pass

    @abstractmethod
    async def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """Get pricing for all supported models."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider name."""
        pass


class OpenAIPricingAPI(BasePricingAPI):
    """OpenAI pricing API integration."""

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://api.openai.com/v1"

    def get_provider_name(self) -> str:
        return "openai"

    async def get_model_pricing(self, model_name: str) -> dict[str, float]:
        """Get pricing for a specific OpenAI model."""
        # OpenAI doesn't have a direct pricing API, so we use static data
        # In a real implementation, this might scrape their pricing page or use internal APIs

        pricing_data = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
            "gpt-4-vision-preview": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
            "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
            "text-embedding-ada-002": {"input": 0.0001, "output": 0.0},
            "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
            "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
        }

        if model_name not in pricing_data:
            logger.warning(f"No pricing data for OpenAI model: {model_name}")
            return {"input": 0.01, "output": 0.03}  # Default fallback

        return pricing_data[model_name]

    async def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """Get pricing for all OpenAI models."""
        # In a real implementation, this would fetch from OpenAI's pricing API or scrape their website
        models = [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4-vision-preview",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
        ]

        pricing = {}
        for model in models:
            try:
                pricing[model] = await self.get_model_pricing(model)
            except Exception as e:
                logger.error(f"Failed to get pricing for {model}: {e}")
                pricing[model] = {"input": 0.01, "output": 0.03}

        return pricing

    async def get_usage_pricing(self) -> dict[str, Any]:
        """Get current usage and billing information (if API key provided)."""
        if not self.api_key:
            return {}

        try:
            # Get usage data (this endpoint may not exist in public API)
            # This is a placeholder for potential future OpenAI billing API

            # For now, return empty dict as OpenAI doesn't expose this publicly
            return {}

        except Exception as e:
            logger.error(f"Failed to get OpenAI usage data: {e}")
            return {}


class AnthropicPricingAPI(BasePricingAPI):
    """Anthropic pricing API integration."""

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://api.anthropic.com/v1"

    def get_provider_name(self) -> str:
        return "anthropic"

    async def get_model_pricing(self, model_name: str) -> dict[str, float]:
        """Get pricing for a specific Anthropic model."""
        pricing_data = {
            "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
            "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
            "claude-2.1": {"input": 0.008, "output": 0.024},
            "claude-2.0": {"input": 0.008, "output": 0.024},
            "claude-instant-1.2": {"input": 0.0008, "output": 0.0024},
        }

        if model_name not in pricing_data:
            logger.warning(f"No pricing data for Anthropic model: {model_name}")
            return {"input": 0.008, "output": 0.024}  # Default fallback

        return pricing_data[model_name]

    async def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """Get pricing for all Anthropic models."""
        models = [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]

        pricing = {}
        for model in models:
            try:
                pricing[model] = await self.get_model_pricing(model)
            except Exception as e:
                logger.error(f"Failed to get pricing for {model}: {e}")
                pricing[model] = {"input": 0.008, "output": 0.024}

        return pricing


class GooglePricingAPI(BasePricingAPI):
    """Google AI pricing API integration."""

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://generativelanguage.googleapis.com/v1"

    def get_provider_name(self) -> str:
        return "google"

    async def get_model_pricing(self, model_name: str) -> dict[str, float]:
        """Get pricing for a specific Google model."""
        pricing_data = {
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "gemini-pro-vision": {"input": 0.0025, "output": 0.01},
            "gemini-ultra": {"input": 0.0125, "output": 0.0375},  # Estimated
            "text-bison-001": {"input": 0.001, "output": 0.001},
            "chat-bison-001": {"input": 0.001, "output": 0.001},
            "code-bison-001": {"input": 0.001, "output": 0.001},
        }

        if model_name not in pricing_data:
            logger.warning(f"No pricing data for Google model: {model_name}")
            return {"input": 0.001, "output": 0.001}  # Default fallback

        return pricing_data[model_name]

    async def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """Get pricing for all Google models."""
        models = [
            "gemini-pro",
            "gemini-pro-vision",
            "gemini-ultra",
            "text-bison-001",
            "chat-bison-001",
            "code-bison-001",
        ]

        pricing = {}
        for model in models:
            try:
                pricing[model] = await self.get_model_pricing(model)
            except Exception as e:
                logger.error(f"Failed to get pricing for {model}: {e}")
                pricing[model] = {"input": 0.001, "output": 0.001}

        return pricing


class MockPricingAPI(BasePricingAPI):
    """Mock pricing API for testing and development."""

    def __init__(self, provider_name: str, **kwargs):
        super().__init__(**kwargs)
        self.provider_name = provider_name
        self._pricing_data = {}
        self._price_volatility = 0.05  # 5% random price changes

    def get_provider_name(self) -> str:
        return self.provider_name

    def set_pricing_data(self, pricing_data: dict[str, dict[str, float]]) -> None:
        """Set mock pricing data."""
        self._pricing_data = pricing_data

    async def get_model_pricing(self, model_name: str) -> dict[str, float]:
        """Get mock pricing for a model with optional volatility."""
        if model_name not in self._pricing_data:
            return {"input": 0.01, "output": 0.03}

        base_pricing = self._pricing_data[model_name]

        # Add some random volatility for testing
        import random

        volatility_factor = 1 + random.uniform(-self._price_volatility, self._price_volatility)

        return {
            "input": base_pricing["input"] * volatility_factor,
            "output": base_pricing["output"] * volatility_factor,
        }

    async def get_all_pricing(self) -> dict[str, dict[str, float]]:
        """Get all mock pricing data."""
        pricing = {}
        for model_name in self._pricing_data:
            pricing[model_name] = await self.get_model_pricing(model_name)

        return pricing


def create_pricing_api(provider: str, api_key: str | None = None, **kwargs) -> BasePricingAPI:
    """Factory function to create pricing API instances."""
    if provider.lower() == "openai":
        return OpenAIPricingAPI(api_key, **kwargs)
    elif provider.lower() == "anthropic":
        return AnthropicPricingAPI(api_key, **kwargs)
    elif provider.lower() == "google":
        return GooglePricingAPI(api_key, **kwargs)
    elif provider.lower() == "mock":
        return MockPricingAPI(kwargs.get("provider_name", "mock"), **kwargs)
    else:
        raise ValueError(f"Unsupported pricing provider: {provider}")
