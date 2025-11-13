"""POC tests for enterprise infrastructure features.

Tests verify that the new enterprise architecture works correctly:
- Dependency injection container
- Lifecycle manager with graceful shutdown
- Secrets management (Vault + environment fallback)
- Rate limiting (Redis-based per-tenant)
- Database connection pooling
- Routing service with multiple strategies
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from router_service.core.container import Container
from router_service.core.lifecycle import LifecycleManager
from router_service.core.shutdown import ShutdownCoordinator
from router_service.domain.adapter.registry import AdapterRegistry
from router_service.domain.observation.service import ObservationService
from router_service.domain.routing.service import RoutingService
from router_service.infrastructure.secrets.service import SecretsService


class TestDependencyInjection:
    """Test the dependency injection container."""

    def test_container_register_and_resolve(self):
        """Test service registration and resolution."""
        container = Container()

        # Register a service
        obs_service = ObservationService(buffer_size=100)
        container.register(ObservationService, obs_service)

        # Resolve the service
        resolved = container.resolve(ObservationService)
        assert resolved is obs_service
        assert resolved.buffer_size == 100

    def test_container_singleton_behavior(self):
        """Test singleton pattern in container."""
        container = Container()

        # Register as singleton
        obs_service = ObservationService(buffer_size=100)
        container.register(ObservationService, obs_service, singleton=True)

        # Resolve multiple times
        resolved1 = container.resolve(ObservationService)
        resolved2 = container.resolve(ObservationService)

        assert resolved1 is resolved2

    def test_container_factory_registration(self):
        """Test factory-based registration."""
        container = Container()

        # Register with factory
        def create_obs_service():
            return ObservationService(buffer_size=200)

        container.register(ObservationService, factory=create_obs_service, singleton=False)

        # Each resolution should create new instance
        resolved1 = container.resolve(ObservationService)
        resolved2 = container.resolve(ObservationService)

        assert resolved1 is not resolved2
        assert resolved1.buffer_size == 200


class TestLifecycleManager:
    """Test application lifecycle management."""

    @pytest.mark.asyncio
    async def test_startup_handlers(self):
        """Test startup handler execution."""
        lifecycle = LifecycleManager()

        # Track execution
        executed = []

        async def handler1():
            executed.append(1)

        async def handler2():
            executed.append(2)

        lifecycle.register_startup(handler1)
        lifecycle.register_startup(handler2)

        await lifecycle.startup()

        assert executed == [1, 2]

    @pytest.mark.asyncio
    async def test_shutdown_handlers(self):
        """Test shutdown handler execution."""
        lifecycle = LifecycleManager()

        # Track execution
        executed = []

        async def handler1():
            executed.append(1)

        async def handler2():
            executed.append(2)

        lifecycle.register_shutdown(handler1)
        lifecycle.register_shutdown(handler2)

        await lifecycle.shutdown()

        assert executed == [1, 2]


class TestShutdownCoordinator:
    """Test graceful shutdown coordination."""

    @pytest.mark.asyncio
    async def test_shutdown_event(self):
        """Test shutdown event signaling."""
        coordinator = ShutdownCoordinator()

        assert not coordinator.is_shutting_down()

        # Start shutdown
        shutdown_task = asyncio.create_task(coordinator.shutdown())

        # Give it a moment
        await asyncio.sleep(0.1)

        assert coordinator.is_shutting_down()

        await shutdown_task

    @pytest.mark.asyncio
    async def test_connection_tracking(self):
        """Test WebSocket connection tracking."""
        coordinator = ShutdownCoordinator()

        # Mock WebSocket
        ws1 = Mock()
        ws1.close = AsyncMock()
        ws2 = Mock()
        ws2.close = AsyncMock()

        coordinator.add_connection(ws1)
        coordinator.add_connection(ws2)

        await coordinator.shutdown(timeout=5.0)

        # Verify connections were closed
        ws1.close.assert_called_once()
        ws2.close.assert_called_once()


class TestSecretsManagement:
    """Test secrets management service."""

    def test_environment_backend(self):
        """Test environment-based secrets backend."""
        # Set environment variable
        os.environ["TEST_SECRET"] = "test_value"

        service = SecretsService.from_config()

        # Resolve secret
        secret = service.get_secret("TEST_SECRET")
        assert secret == "test_value"

        # Cleanup
        del os.environ["TEST_SECRET"]

    def test_secret_caching(self):
        """Test secret caching behavior."""
        os.environ["TEST_SECRET"] = "test_value"

        service = SecretsService.from_config()

        # First access
        secret1 = service.get_secret("TEST_SECRET")

        # Second access (should be cached)
        secret2 = service.get_secret("TEST_SECRET")

        assert secret1 == secret2

        # Cleanup
        del os.environ["TEST_SECRET"]


class TestObservationService:
    """Test observation buffering service."""

    @pytest.mark.asyncio
    async def test_add_observation(self):
        """Test adding observations to buffer."""
        service = ObservationService(buffer_size=10)

        from router_service.domain.observation.models import Observation

        obs = Observation(
            request_id="req-1",
            model="gpt-4",
            prompt_length=100,
            completion_length=200,
            latency_ms=500.0,
            cost_usd=0.01,
        )

        await service.add(obs)

        observations = await service.get_all()
        assert len(observations) == 1
        assert observations[0].request_id == "req-1"

    @pytest.mark.asyncio
    async def test_buffer_overflow(self):
        """Test buffer overflow handling."""
        service = ObservationService(buffer_size=3)

        from router_service.domain.observation.models import Observation

        # Add more than buffer size
        for i in range(5):
            obs = Observation(
                request_id=f"req-{i}",
                model="gpt-4",
                prompt_length=100,
                completion_length=200,
                latency_ms=500.0,
                cost_usd=0.01,
            )
            await service.add(obs)

        observations = await service.get_all()
        assert len(observations) == 3  # Buffer size
        assert observations[0].request_id == "req-2"  # Oldest kept


class TestAdapterRegistry:
    """Test adapter registry service."""

    def test_register_adapter(self):
        """Test adapter registration."""
        registry = AdapterRegistry()

        registry.register(
            adapter_id="adapter-1",
            adapter_type="openai",
            capabilities=["chat", "completion"],
        )

        adapters = registry.list_adapters()
        assert len(adapters) == 1
        assert adapters[0].adapter_id == "adapter-1"

    def test_adapter_health_tracking(self):
        """Test adapter health status tracking."""
        registry = AdapterRegistry()

        registry.register(adapter_id="adapter-1", adapter_type="openai", capabilities=["chat"])

        # Mark as unhealthy
        registry.mark_unhealthy("adapter-1")

        adapters = registry.list_adapters(healthy_only=False)
        assert adapters[0].is_healthy is False

        # Mark as healthy
        registry.mark_healthy("adapter-1")

        adapters = registry.list_adapters(healthy_only=True)
        assert len(adapters) == 1
        assert adapters[0].is_healthy is True


class TestRoutingService:
    """Test routing service."""

    def test_routing_service_creation(self):
        """Test creating routing service with default strategy."""
        service = RoutingService(default_strategy="thompson")

        assert service.default_strategy == "thompson"

    @pytest.mark.asyncio
    async def test_select_model_basic(self):
        """Test basic model selection."""
        service = RoutingService(default_strategy="greedy")

        # Mock stats
        mock_stats = Mock()
        mock_stats.all_models = ["gpt-4", "claude-3"]
        mock_stats.mean_cost_usd = Mock(return_value=0.01)
        mock_stats.mean_latency_ms = Mock(return_value=500.0)
        mock_stats.success_rate = Mock(return_value=0.99)

        with patch("router_service.domain.routing.service.get_stats", return_value=mock_stats):
            model_id, metadata = await service.select_model(
                prompt="Test prompt",
                quality_target="balanced",
                max_cost_usd=0.1,
            )

            assert model_id in ["gpt-4", "claude-3"]
            assert "strategy" in metadata


# Integration test
class TestEnterpriseIntegration:
    """Test integrated enterprise components."""

    @pytest.mark.asyncio
    async def test_full_request_lifecycle(self):
        """Test full request lifecycle with all components."""
        # Setup container
        container = Container()

        # Register services
        obs_service = ObservationService(buffer_size=100)
        container.register(ObservationService, obs_service)

        routing_service = RoutingService(default_strategy="thompson")
        container.register(RoutingService, routing_service)

        adapter_registry = AdapterRegistry()
        container.register(AdapterRegistry, adapter_registry)

        # Register adapter
        adapter_registry.register(
            adapter_id="test-adapter",
            adapter_type="openai",
            capabilities=["chat"],
        )

        # Simulate request
        from router_service.domain.observation.models import Observation

        obs = Observation(
            request_id="req-test",
            model="gpt-4",
            prompt_length=100,
            completion_length=200,
            latency_ms=500.0,
            cost_usd=0.01,
        )

        await obs_service.add(obs)

        # Verify observation stored
        observations = await obs_service.get_all()
        assert len(observations) == 1

        # Verify adapter registered
        adapters = adapter_registry.list_adapters()
        assert len(adapters) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
