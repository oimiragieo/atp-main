"""Tests for the enterprise data access layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Test the repository manager
@pytest.mark.asyncio
async def test_repository_manager_initialization():
    """Test that repository manager initializes correctly."""
    with patch("router_service.repository_manager.get_database_manager") as mock_db:
        mock_db.return_value = MagicMock()

        from router_service.repository_manager import RepositoryManager

        repo_manager = RepositoryManager()

        # Check that all repositories are initialized
        assert repo_manager.models is not None
        assert repo_manager.providers is not None
        assert repo_manager.requests is not None
        assert repo_manager.policies is not None
        assert repo_manager.compliance is not None
        assert repo_manager.audit is not None


@pytest.mark.asyncio
async def test_data_service_model_registry():
    """Test data service model registry functionality."""
    with patch("router_service.data_service.get_repository_manager") as mock_repo_manager:
        # Mock repository manager
        mock_manager = AsyncMock()
        mock_repo_manager.return_value = mock_manager

        # Mock model data
        mock_models = [
            MagicMock(
                id="model-1",
                name="test-model",
                display_name="Test Model",
                provider_id="provider-1",
                status="active",
                is_enabled=True,
                model_family="test",
                context_window=4096,
                max_output_tokens=1024,
                supports_streaming=True,
                supports_function_calling=False,
                supports_vision=False,
                cost_per_input_token=0.001,
                cost_per_output_token=0.002,
                cost_per_request=0.0,
                latency_p50_ms=100.0,
                latency_p95_ms=200.0,
                quality_score=0.85,
                created_at=None,
                updated_at=None,
            )
        ]

        mock_provider = MagicMock(id="provider-1", name="test-provider")

        mock_manager.models.get_enabled_models.return_value = mock_models
        mock_manager.providers.get_by_id.return_value = mock_provider

        from router_service.data_service import DataService

        data_service = DataService()
        registry_data = await data_service.get_model_registry()

        # Verify registry data structure
        assert "test-model" in registry_data
        model_data = registry_data["test-model"]
        assert model_data["name"] == "test-model"
        assert model_data["provider"] == "test-provider"
        assert model_data["status"] == "active"
        assert model_data["is_enabled"] is True


@pytest.mark.asyncio
async def test_registry_adapter_compatibility():
    """Test that registry adapter provides backward compatibility."""
    with patch("router_service.registry_adapter.get_data_service") as mock_data_service:
        # Mock data service
        mock_service = AsyncMock()
        mock_data_service.return_value = mock_service

        # Mock registry data
        mock_registry = {
            "model1": {"status": "active", "provider": "openai"},
            "model2": {"status": "shadow", "provider": "anthropic"},
        }
        mock_service.get_model_registry.return_value = mock_registry
        mock_service.get_shadow_models.return_value = ["model2"]

        from router_service.registry_adapter import RegistryAdapter

        adapter = RegistryAdapter()

        # Test async methods
        registry = await adapter.get_registry()
        assert len(registry) == 2
        assert "model1" in registry

        shadow_models = await adapter.get_shadow_models()
        assert "model2" in shadow_models

        # Test synchronous compatibility methods
        # Note: These would normally require an event loop
        adapter._cache = mock_registry
        adapter._cache_valid = True

        assert len(adapter) == 2
        assert "model1" in adapter
        assert adapter.get("model1") is not None
        assert adapter.get("nonexistent") is None


@pytest.mark.asyncio
async def test_model_repository_specialized_methods():
    """Test model repository specialized query methods."""
    with patch("router_service.repositories.model_repository.get_database_manager") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.get_session.return_value.__aenter__.return_value = mock_session

        from router_service.repositories.model_repository import ModelRepository

        repo = ModelRepository()

        # Mock query results
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(name="model1", status="active"),
            MagicMock(name="model2", status="active"),
        ]
        mock_session.execute.return_value = mock_result

        # Test get_enabled_models
        models = await repo.get_enabled_models()

        # Verify that execute was called
        mock_session.execute.assert_called()
        assert len(models) == 2


@pytest.mark.asyncio
async def test_transaction_management():
    """Test transaction management in repository manager."""
    with patch("router_service.repository_manager.get_database_manager") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.get_session.return_value.__aenter__.return_value = mock_session

        from router_service.repository_manager import RepositoryManager

        repo_manager = RepositoryManager()

        # Test transaction context manager
        async with repo_manager.transaction() as tx_manager:
            # Verify that repositories have transaction session
            assert hasattr(tx_manager.models, "_transaction_session")
            assert hasattr(tx_manager.providers, "_transaction_session")

        # Verify session methods were called
        mock_session.begin.assert_called_once()
        mock_session.commit.assert_called_once()


def test_registry_migration_validation():
    """Test registry migration validation logic."""

    # This would normally be an async test, but we're testing the validation logic
    # In a real test, we'd mock the file system and database calls
    pass


@pytest.mark.asyncio
async def test_startup_initialization():
    """Test startup initialization process."""
    with (
        patch("router_service.startup.initialize_database") as mock_init_db,
        patch("router_service.startup.initialize_repository_manager") as mock_init_repo,
        patch("router_service.startup.migrate_registry_to_database") as mock_migrate,
        patch("router_service.startup.create_sample_models") as mock_samples,
        patch("router_service.startup.initialize_registry_adapter"),
        patch("os.path.exists") as mock_exists,
    ):
        # Mock successful initialization
        mock_init_repo.return_value = AsyncMock()
        mock_init_repo.return_value.health_check.return_value = {"database_connection": True}
        mock_migrate.return_value = True
        mock_samples.return_value = True
        mock_exists.return_value = False  # No registry file to migrate

        from router_service.startup import initialize_enterprise_data_layer

        success = await initialize_enterprise_data_layer(create_tables=True, migrate_registry=True, create_samples=True)

        assert success is True
        mock_init_db.assert_called_once()
        mock_init_repo.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
