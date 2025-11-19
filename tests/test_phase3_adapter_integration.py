"""Test Phase 3 adapter integration in service.py.

This test verifies that the adapter integration code paths are correctly
implemented without requiring the full service dependencies.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPhase3AdapterIntegration:
    """Test adapter integration in the main streaming endpoint."""

    @pytest.mark.asyncio
    async def test_adapter_client_basic_functionality(self):
        """Test that AdapterClient can be imported and instantiated."""
        from router_service.adapters.client import AdapterClient, AdapterClientPool

        # Test client creation
        client = AdapterClient("localhost:7073", timeout=30.0)
        assert client.endpoint == "localhost:7073"
        assert client.timeout == 30.0

        # Test pool creation
        pool = AdapterClientPool()
        assert pool is not None

        # Test pool get_client
        client2 = pool.get_client("localhost:7073")
        assert client2.endpoint == "localhost:7073"

        # Test pool reuses clients
        client3 = pool.get_client("localhost:7073")
        assert client2 is client3

    @pytest.mark.asyncio
    async def test_adapter_client_stream_mock(self):
        """Test adapter streaming with mocked gRPC."""
        from router_service.adapters.client import AdapterClient

        client = AdapterClient("localhost:7073")

        # Mock the gRPC stub
        mock_stub = AsyncMock()
        mock_response = [
            MagicMock(
                type="text",
                content_json='{"text": "Hello"}',
                confidence=0.95,
                partial_in_tokens=10,
                partial_out_tokens=1,
                partial_usd_micros=100,
                more=True,
            ),
            MagicMock(
                type="text",
                content_json='{"text": " world"}',
                confidence=0.95,
                partial_in_tokens=10,
                partial_out_tokens=3,
                partial_usd_micros=300,
                more=False,
            ),
        ]

        async def mock_stream(*args, **kwargs):
            for chunk in mock_response:
                yield chunk

        mock_stub.Stream = mock_stream
        client._stub = mock_stub
        client._channel = MagicMock()

        # Test streaming
        chunks = []
        async for chunk in client.stream("Test prompt"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0]["type"] == "text"
        assert chunks[0]["content_json"] == '{"text": "Hello"}'
        assert chunks[0]["partial_out_tokens"] == 1
        assert chunks[0]["more"] is True

        assert chunks[1]["type"] == "text"
        assert chunks[1]["content_json"] == '{"text": " world"}'
        assert chunks[1]["partial_out_tokens"] == 3
        assert chunks[1]["more"] is False

    def test_dynamic_catalog_fallback(self):
        """Test that dynamic catalog gracefully falls back to static catalog."""
        from router_service.routing_constants import CATALOG, STATIC_CATALOG

        # In test environment without adapters, catalog should equal static catalog
        assert len(CATALOG) == len(STATIC_CATALOG)
        assert CATALOG == STATIC_CATALOG

        # Verify static catalog has expected models
        model_names = [c.name for c in STATIC_CATALOG]
        assert "cheap-model" in model_names
        assert "mid-model" in model_names
        assert "premium-model" in model_names

    def test_config_adapter_settings(self):
        """Test that config has adapter integration settings."""
        from router_service.config import Settings

        settings = Settings()

        # Check adapter settings exist
        assert hasattr(settings, "use_real_adapters")
        assert hasattr(settings, "adapter_timeout")
        assert hasattr(settings, "adapter_rollout_percent")

        # Check defaults
        assert settings.use_real_adapters is False  # Default off
        assert settings.adapter_timeout == 30.0
        assert settings.adapter_rollout_percent == 0

    @pytest.mark.asyncio
    async def test_adapter_pool_lifecycle(self):
        """Test adapter pool creation and cleanup."""
        from router_service.adapters.client import AdapterClientPool

        pool = AdapterClientPool()

        # Get some clients
        client1 = pool.get_client("localhost:7073")
        client2 = pool.get_client("localhost:7074")

        # Check they're tracked
        active = pool.get_active_clients()
        assert "localhost:7073" in active
        assert "localhost:7074" in active

        # Mock the channels
        client1._channel = AsyncMock()
        client2._channel = AsyncMock()

        # Test cleanup
        await pool.close_all()

        # Verify close was called on channels
        client1._channel.close.assert_called_once()
        client2._channel.close.assert_called_once()

        # Pool should be empty
        assert len(pool.get_active_clients()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
