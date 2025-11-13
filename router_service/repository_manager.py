"""Repository manager for coordinating all data access operations."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from .database import get_database_manager
from .repositories import (
    AuditRepository,
    ComplianceRepository,
    ModelRepository,
    PolicyRepository,
    ProviderRepository,
    RequestRepository,
)

logger = logging.getLogger(__name__)


class RepositoryManager:
    """Centralized manager for all repositories with transaction support."""

    def __init__(self):
        self.db_manager = get_database_manager()

        # Initialize repositories
        self.models = ModelRepository()
        self.providers = ProviderRepository()
        self.requests = RequestRepository()
        self.policies = PolicyRepository()
        self.compliance = ComplianceRepository()
        self.audit = AuditRepository()

        logger.info("Repository manager initialized with all repositories")

    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions across multiple repositories."""
        async with self.db_manager.get_session() as session:
            try:
                # Begin transaction
                await session.begin()

                # Provide session to all repositories for this transaction
                original_sessions = {}
                for repo_name in ["models", "providers", "requests", "policies", "compliance", "audit"]:
                    repo = getattr(self, repo_name)
                    original_sessions[repo_name] = repo.db_manager
                    # Temporarily override the session getter for this transaction
                    repo._transaction_session = session

                yield self

                # Commit transaction
                await session.commit()
                logger.debug("Transaction committed successfully")

            except Exception as e:
                # Rollback transaction
                await session.rollback()
                logger.error(f"Transaction rolled back due to error: {e}")
                raise
            finally:
                # Restore original session getters
                for repo_name in ["models", "providers", "requests", "policies", "compliance", "audit"]:
                    repo = getattr(self, repo_name)
                    if hasattr(repo, "_transaction_session"):
                        delattr(repo, "_transaction_session")

    async def get_model_registry_data(self) -> dict[str, dict[str, Any]]:
        """Get model registry data in the format expected by the router service."""
        models = await self.models.get_enabled_models()

        registry_data = {}
        for model in models:
            # Get provider information
            provider = await self.providers.get_by_id(model.provider_id)
            if not provider:
                continue

            registry_data[model.name] = {
                "id": str(model.id),
                "name": model.name,
                "display_name": model.display_name,
                "provider": provider.name,
                "provider_id": str(provider.id),
                "status": model.status,
                "is_enabled": model.is_enabled,
                "model_family": model.model_family,
                "context_window": model.context_window,
                "max_output_tokens": model.max_output_tokens,
                "supports_streaming": model.supports_streaming,
                "supports_function_calling": model.supports_function_calling,
                "supports_vision": model.supports_vision,
                "cost_per_input_token": float(model.cost_per_input_token or 0),
                "cost_per_output_token": float(model.cost_per_output_token or 0),
                "cost_per_request": float(model.cost_per_request or 0),
                "latency_p50_ms": float(model.latency_p50_ms or 0),
                "latency_p95_ms": float(model.latency_p95_ms or 0),
                "quality_score": float(model.quality_score or 0),
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            }

        logger.debug(f"Retrieved model registry data for {len(registry_data)} models")
        return registry_data

    async def get_shadow_models(self) -> dict[str, dict[str, Any]]:
        """Get shadow models in registry format."""
        shadow_models = await self.models.get_shadow_models()

        registry_data = {}
        for model in shadow_models:
            provider = await self.providers.get_by_id(model.provider_id)
            if not provider:
                continue

            registry_data[model.name] = {
                "id": str(model.id),
                "name": model.name,
                "display_name": model.display_name,
                "provider": provider.name,
                "provider_id": str(provider.id),
                "status": model.status,
                "is_enabled": model.is_enabled,
                "model_family": model.model_family,
                "context_window": model.context_window,
                "max_output_tokens": model.max_output_tokens,
                "supports_streaming": model.supports_streaming,
                "supports_function_calling": model.supports_function_calling,
                "supports_vision": model.supports_vision,
                "cost_per_input_token": float(model.cost_per_input_token or 0),
                "cost_per_output_token": float(model.cost_per_output_token or 0),
                "cost_per_request": float(model.cost_per_request or 0),
                "latency_p50_ms": float(model.latency_p50_ms or 0),
                "latency_p95_ms": float(model.latency_p95_ms or 0),
                "quality_score": float(model.quality_score or 0),
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            }

        return registry_data

    async def update_model_performance(
        self,
        model_name: str,
        latency_p50_ms: float | None = None,
        latency_p95_ms: float | None = None,
        quality_score: float | None = None,
    ) -> bool:
        """Update model performance metrics."""
        model = await self.models.get_by_name(model_name)
        if not model:
            logger.warning(f"Model {model_name} not found for performance update")
            return False

        return await self.models.update_performance_metrics(
            model.id, latency_p50_ms=latency_p50_ms, latency_p95_ms=latency_p95_ms, quality_score=quality_score
        )

    async def promote_shadow_model(self, model_name: str) -> bool:
        """Promote a shadow model to active status."""
        model = await self.models.get_by_name(model_name)
        if not model:
            logger.warning(f"Model {model_name} not found for promotion")
            return False

        return await self.models.promote_shadow_model(model.id)

    async def demote_to_shadow(self, model_name: str) -> bool:
        """Demote an active model to shadow status."""
        model = await self.models.get_by_name(model_name)
        if not model:
            logger.warning(f"Model {model_name} not found for demotion")
            return False

        return await self.models.demote_to_shadow(model.id)

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
        return await self.requests.create(
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

    async def log_audit_event(
        self,
        event_type: str,
        action: str,
        outcome: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        event_data: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        """Log an audit event."""
        return await self.audit.log_event(
            event_type=event_type,
            action=action,
            outcome=outcome,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            event_data=event_data,
            correlation_id=correlation_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_cache_statistics(self) -> dict[str, Any]:
        """Get cache statistics from all repositories."""
        return {
            "models": self.models.get_cache_stats(),
            "providers": self.providers.get_cache_stats(),
            "requests": self.requests.get_cache_stats(),
            "policies": self.policies.get_cache_stats(),
            "compliance": self.compliance.get_cache_stats(),
            "audit": self.audit.get_cache_stats(),
        }

    async def clear_all_caches(self) -> None:
        """Clear all repository caches."""
        self.models.clear_cache()
        self.providers.clear_cache()
        self.requests.clear_cache()
        self.policies.clear_cache()
        self.compliance.clear_cache()
        self.audit.clear_cache()
        logger.info("All repository caches cleared")

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on all repositories."""
        health_status = {"database_connection": False, "repositories": {}, "cache_stats": {}}

        try:
            # Test database connection
            async with self.db_manager.get_session() as session:
                await session.execute("SELECT 1")
                health_status["database_connection"] = True

            # Test each repository
            for repo_name in ["models", "providers", "requests", "policies", "compliance", "audit"]:
                repo = getattr(self, repo_name)
                try:
                    # Test basic count operation
                    count = await repo.count()
                    health_status["repositories"][repo_name] = {"status": "healthy", "record_count": count}
                except Exception as e:
                    health_status["repositories"][repo_name] = {"status": "unhealthy", "error": str(e)}

            # Get cache statistics
            health_status["cache_stats"] = await self.get_cache_statistics()

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["error"] = str(e)

        return health_status


# Global repository manager instance
_repository_manager: RepositoryManager | None = None


def get_repository_manager() -> RepositoryManager:
    """Get the global repository manager instance."""
    global _repository_manager
    if _repository_manager is None:
        _repository_manager = RepositoryManager()
    return _repository_manager


async def initialize_repository_manager() -> RepositoryManager:
    """Initialize and return the repository manager."""
    repo_manager = get_repository_manager()

    # Perform initial health check
    health = await repo_manager.health_check()
    if not health["database_connection"]:
        logger.error("Failed to initialize repository manager: database connection failed")
        raise RuntimeError("Database connection failed during repository manager initialization")

    logger.info("Repository manager initialized successfully")
    return repo_manager
