"""Data service layer that integrates repositories with the router service."""

from __future__ import annotations

import logging
from typing import Any

from .repository_manager import get_repository_manager

logger = logging.getLogger(__name__)


class DataService:
    """Service layer that provides data access methods for the router service."""

    def __init__(self):
        self.repo_manager = get_repository_manager()

    async def get_model_registry(self) -> dict[str, dict[str, Any]]:
        """Get model registry data compatible with existing router service format."""
        try:
            return await self.repo_manager.get_model_registry_data()
        except Exception as e:
            logger.error(f"Failed to get model registry: {e}")
            return {}

    async def get_shadow_models(self) -> list[str]:
        """Get list of shadow model names."""
        try:
            shadow_models = await self.repo_manager.get_shadow_models()
            return list(shadow_models.keys())
        except Exception as e:
            logger.error(f"Failed to get shadow models: {e}")
            return []

    async def update_model_performance(
        self,
        model_name: str,
        latency_p50_ms: float | None = None,
        latency_p95_ms: float | None = None,
        quality_score: float | None = None,
    ) -> bool:
        """Update model performance metrics."""
        try:
            return await self.repo_manager.update_model_performance(
                model_name, latency_p50_ms, latency_p95_ms, quality_score
            )
        except Exception as e:
            logger.error(f"Failed to update model performance for {model_name}: {e}")
            return False

    async def promote_shadow_model(self, model_name: str) -> bool:
        """Promote a shadow model to active status."""
        try:
            success = await self.repo_manager.promote_shadow_model(model_name)
            if success:
                # Log audit event
                await self.repo_manager.log_audit_event(
                    event_type="model_lifecycle",
                    action="promote_model",
                    outcome="success",
                    resource_type="model",
                    resource_id=model_name,
                    event_data={"model_name": model_name, "action": "promote_to_active"},
                )
            return success
        except Exception as e:
            logger.error(f"Failed to promote model {model_name}: {e}")
            # Log audit event for failure
            await self.repo_manager.log_audit_event(
                event_type="model_lifecycle",
                action="promote_model",
                outcome="failure",
                resource_type="model",
                resource_id=model_name,
                event_data={"model_name": model_name, "error": str(e)},
            )
            return False

    async def demote_to_shadow(self, model_name: str) -> bool:
        """Demote an active model to shadow status."""
        try:
            success = await self.repo_manager.demote_to_shadow(model_name)
            if success:
                # Log audit event
                await self.repo_manager.log_audit_event(
                    event_type="model_lifecycle",
                    action="demote_model",
                    outcome="success",
                    resource_type="model",
                    resource_id=model_name,
                    event_data={"model_name": model_name, "action": "demote_to_shadow"},
                )
            return success
        except Exception as e:
            logger.error(f"Failed to demote model {model_name}: {e}")
            # Log audit event for failure
            await self.repo_manager.log_audit_event(
                event_type="model_lifecycle",
                action="demote_model",
                outcome="failure",
                resource_type="model",
                resource_id=model_name,
                event_data={"model_name": model_name, "error": str(e)},
            )
            return False

    async def log_request(
        self,
        correlation_id: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
        prompt: str | None = None,
        model_used: str | None = None,
        provider_used: str | None = None,
        response_text: str | None = None,
        status_code: int = 200,
        response_time_ms: float | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        cost_usd: float | None = None,
        quality_score: float | None = None,
        confidence_score: float | None = None,
        request_metadata: dict[str, Any] | None = None,
    ):
        """Log a request to the database."""
        try:
            return await self.repo_manager.log_request(
                correlation_id=correlation_id,
                user_id=user_id,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt=prompt,
                model_used=model_used,
                provider_used=provider_used,
                response_text=response_text,
                status_code=status_code,
                response_time_ms=response_time_ms,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_usd=cost_usd,
                quality_score=quality_score,
                confidence_score=confidence_score,
                request_metadata=request_metadata,
            )
        except Exception as e:
            logger.error(f"Failed to log request {correlation_id}: {e}")
            return None

    async def get_model_status_summary(self) -> list[dict[str, Any]]:
        """Get model status summary for admin endpoints."""
        try:
            registry_data = await self.get_model_registry()
            shadow_models = await self.get_shadow_models()

            summary = []
            for model_name, model_data in registry_data.items():
                summary.append(
                    {
                        "name": model_name,
                        "display_name": model_data.get("display_name", model_name),
                        "provider": model_data.get("provider", "unknown"),
                        "status": model_data.get("status", "unknown"),
                        "is_enabled": model_data.get("is_enabled", False),
                        "quality_score": model_data.get("quality_score", 0.0),
                        "latency_p95_ms": model_data.get("latency_p95_ms", 0.0),
                        "cost_per_input_token": model_data.get("cost_per_input_token", 0.0),
                        "cost_per_output_token": model_data.get("cost_per_output_token", 0.0),
                    }
                )

            # Add shadow models that might not be in the main registry
            for shadow_model in shadow_models:
                if not any(m["name"] == shadow_model for m in summary):
                    summary.append(
                        {
                            "name": shadow_model,
                            "display_name": shadow_model,
                            "provider": "unknown",
                            "status": "shadow",
                            "is_enabled": False,
                            "quality_score": 0.0,
                            "latency_p95_ms": 0.0,
                            "cost_per_input_token": 0.0,
                            "cost_per_output_token": 0.0,
                        }
                    )

            return summary
        except Exception as e:
            logger.error(f"Failed to get model status summary: {e}")
            return []

    async def get_registry_size(self) -> int:
        """Get the size of the model registry."""
        try:
            registry_data = await self.get_model_registry()
            return len(registry_data)
        except Exception as e:
            logger.error(f"Failed to get registry size: {e}")
            return 0

    async def save_registry_data(self, registry_data: dict[str, dict[str, Any]]) -> bool:
        """Save registry data (for compatibility with existing save_registry calls)."""
        # This is a no-op since we're using database persistence
        # The data is automatically saved when models are created/updated
        logger.debug("Registry data save requested - using database persistence")
        return True

    async def reload_registry_from_config(self, config_data: dict[str, Any]) -> bool:
        """Reload registry from configuration data."""
        try:
            # This would typically involve updating the database with new model configurations
            # For now, we'll log the reload request
            logger.info(f"Registry reload requested with {len(config_data)} models")

            # In a full implementation, we would:
            # 1. Validate the config data
            # 2. Update existing models or create new ones
            # 3. Disable models not in the config
            # 4. Log audit events for all changes

            return True
        except Exception as e:
            logger.error(f"Failed to reload registry from config: {e}")
            return False

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on the data service."""
        try:
            repo_health = await self.repo_manager.health_check()
            registry_size = await self.get_registry_size()

            return {
                "status": "healthy" if repo_health["database_connection"] else "unhealthy",
                "database_connection": repo_health["database_connection"],
                "registry_size": registry_size,
                "repositories": repo_health["repositories"],
                "cache_stats": repo_health["cache_stats"],
            }
        except Exception as e:
            logger.error(f"Data service health check failed: {e}")
            return {"status": "unhealthy", "error": str(e), "database_connection": False, "registry_size": 0}


# Global data service instance
_data_service: DataService | None = None


def get_data_service() -> DataService:
    """Get the global data service instance."""
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service
