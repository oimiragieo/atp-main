"""Registry adapter that provides backward compatibility while transitioning to database."""

import asyncio
import logging
from typing import Any

from .data_service import get_data_service

logger = logging.getLogger(__name__)


class RegistryAdapter:
    """Adapter that provides the same interface as the old in-memory registry."""

    def __init__(self):
        self.data_service = get_data_service()
        self._cache: dict[str, dict[str, Any]] | None = None
        self._cache_valid = False

    async def _ensure_cache(self) -> None:
        """Ensure the cache is loaded and valid."""
        if not self._cache_valid or self._cache is None:
            self._cache = await self.data_service.get_model_registry()
            self._cache_valid = True

    def invalidate_cache(self) -> None:
        """Invalidate the cache to force reload on next access."""
        self._cache_valid = False

    async def get_registry(self) -> dict[str, dict[str, Any]]:
        """Get the full model registry."""
        await self._ensure_cache()
        return self._cache or {}

    async def get_model(self, model_name: str) -> dict[str, Any] | None:
        """Get a specific model from the registry."""
        registry = await self.get_registry()
        return registry.get(model_name)

    async def get_shadow_models(self) -> list[str]:
        """Get list of shadow model names."""
        return await self.data_service.get_shadow_models()

    async def update_model_performance(
        self,
        model_name: str,
        latency_p50_ms: float | None = None,
        latency_p95_ms: float | None = None,
        quality_score: float | None = None,
    ) -> bool:
        """Update model performance metrics."""
        success = await self.data_service.update_model_performance(
            model_name, latency_p50_ms, latency_p95_ms, quality_score
        )
        if success:
            self.invalidate_cache()
        return success

    async def promote_shadow_model(self, model_name: str) -> bool:
        """Promote a shadow model to active status."""
        success = await self.data_service.promote_shadow_model(model_name)
        if success:
            self.invalidate_cache()
        return success

    async def demote_to_shadow(self, model_name: str) -> bool:
        """Demote an active model to shadow status."""
        success = await self.data_service.demote_to_shadow(model_name)
        if success:
            self.invalidate_cache()
        return success

    async def save_registry(self) -> bool:
        """Save registry (no-op for database backend)."""
        return await self.data_service.save_registry_data({})

    async def reload_from_config(self, config_data: dict[str, Any]) -> bool:
        """Reload registry from configuration."""
        success = await self.data_service.reload_registry_from_config(config_data)
        if success:
            self.invalidate_cache()
        return success

    def __len__(self) -> int:
        """Get the size of the registry (synchronous for compatibility)."""
        # This is a bit of a hack for synchronous compatibility
        # In practice, we should avoid this and use async methods
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we can't use run_until_complete
                # Return cached size or 0
                return len(self._cache) if self._cache else 0
            else:
                registry = loop.run_until_complete(self.get_registry())
                return len(registry)
        except Exception as e:
            logger.error(f"Failed to get registry size: {e}")
            return 0

    def __contains__(self, model_name: str) -> bool:
        """Check if a model exists in the registry (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, check cache
                return model_name in (self._cache or {})
            else:
                registry = loop.run_until_complete(self.get_registry())
                return model_name in registry
        except Exception as e:
            logger.error(f"Failed to check model existence: {e}")
            return False

    def __getitem__(self, model_name: str) -> dict[str, Any]:
        """Get a model from the registry (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, use cache
                if self._cache and model_name in self._cache:
                    return self._cache[model_name]
                else:
                    raise KeyError(f"Model {model_name} not found")
            else:
                registry = loop.run_until_complete(self.get_registry())
                return registry[model_name]
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Failed to get model {model_name}: {e}")
            raise KeyError(f"Model {model_name} not found") from e

    def __iter__(self):
        """Iterate over model names (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, use cache
                return iter(self._cache or {})
            else:
                registry = loop.run_until_complete(self.get_registry())
                return iter(registry)
        except Exception as e:
            logger.error(f"Failed to iterate registry: {e}")
            return iter({})

    def items(self):
        """Get registry items (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, use cache
                return (self._cache or {}).items()
            else:
                registry = loop.run_until_complete(self.get_registry())
                return registry.items()
        except Exception as e:
            logger.error(f"Failed to get registry items: {e}")
            return {}.items()

    def keys(self):
        """Get registry keys (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, use cache
                return (self._cache or {}).keys()
            else:
                registry = loop.run_until_complete(self.get_registry())
                return registry.keys()
        except Exception as e:
            logger.error(f"Failed to get registry keys: {e}")
            return {}.keys()

    def values(self):
        """Get registry values (synchronous for compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, use cache
                return (self._cache or {}).values()
            else:
                registry = loop.run_until_complete(self.get_registry())
                return registry.values()
        except Exception as e:
            logger.error(f"Failed to get registry values: {e}")
            return {}.values()

    def get(self, model_name: str, default=None):
        """Get a model with default value (synchronous for compatibility)."""
        try:
            return self[model_name]
        except KeyError:
            return default

    def clear(self) -> None:
        """Clear the registry (invalidate cache)."""
        self.invalidate_cache()

    def update(self, other: dict[str, Any]) -> None:
        """Update registry with new data (triggers reload)."""
        # For compatibility, we'll trigger a cache invalidation
        # In practice, updates should go through the proper data service methods
        self.invalidate_cache()
        logger.warning("Registry.update() called - this should use proper data service methods")


# Global registry adapter instance
_registry_adapter: RegistryAdapter | None = None


def get_registry_adapter() -> RegistryAdapter:
    """Get the global registry adapter instance."""
    global _registry_adapter
    if _registry_adapter is None:
        _registry_adapter = RegistryAdapter()
    return _registry_adapter


async def initialize_registry_adapter() -> RegistryAdapter:
    """Initialize the registry adapter and preload cache."""
    adapter = get_registry_adapter()
    await adapter._ensure_cache()
    logger.info("Registry adapter initialized and cache preloaded")
    return adapter
