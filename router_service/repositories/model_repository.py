"""Model repository with specialized query methods."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from ..models.database import Model, Provider
from .base import BaseRepository

logger = logging.getLogger(__name__)


class ModelRepository(BaseRepository[Model]):
    """Repository for Model entities with specialized query methods."""

    def __init__(self):
        super().__init__(Model)

    async def get_by_name(self, name: str, provider_id: UUID | None = None) -> Model | None:
        """Get model by name, optionally filtered by provider."""
        filters = {"name": name}
        if provider_id:
            filters["provider_id"] = provider_id

        return await self.find_one_by(**filters)

    async def get_by_provider(self, provider_id: UUID) -> list[Model]:
        """Get all models for a specific provider."""
        return await self.find_by(provider_id=provider_id)

    async def get_enabled_models(self, provider_id: UUID | None = None) -> list[Model]:
        """Get all enabled models, optionally filtered by provider."""
        filters = {"is_enabled": True, "status": "active"}
        if provider_id:
            filters["provider_id"] = provider_id

        return await self.find_by(**filters)

    async def get_by_status(self, status: str) -> list[Model]:
        """Get models by status (active, shadow, deprecated)."""
        return await self.find_by(status=status)

    async def get_shadow_models(self) -> list[Model]:
        """Get all shadow models."""
        return await self.get_by_status("shadow")

    async def get_active_models(self) -> list[Model]:
        """Get all active models."""
        return await self.get_by_status("active")

    async def get_with_provider(self, model_id: UUID) -> Model | None:
        """Get model with its provider information."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Model)
                .where(Model.id == model_id)
                .where(not Model.is_deleted)
                .options(selectinload(Model.provider))
            )

            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_models_with_provider_info(
        self, enabled_only: bool = True, status_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Get models with their provider information."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Model, Provider)
                .join(Provider, Model.provider_id == Provider.id)
                .where(not Model.is_deleted)
                .where(not Provider.is_deleted)
            )

            if enabled_only:
                stmt = stmt.where(Model.is_enabled)
                stmt = stmt.where(Provider.is_enabled)

            if status_filter:
                stmt = stmt.where(Model.status == status_filter)

            stmt = stmt.order_by(Provider.name, Model.name)

            result = await session.execute(stmt)
            rows = result.all()

            return [{"model": row.Model, "provider": row.Provider} for row in rows]

    async def get_by_family(self, model_family: str) -> list[Model]:
        """Get models by family."""
        return await self.find_by(model_family=model_family)

    async def search_models(
        self, search_term: str, provider_id: UUID | None = None, enabled_only: bool = True
    ) -> list[Model]:
        """Search models by name or display name."""
        async with self.db_manager.get_session() as session:
            # Escape wildcards to prevent SQL injection
            safe_search = search_term.replace("%", "\\%").replace("_", "\\_")
            search_pattern = f"%{safe_search}%"
            stmt = (
                select(Model)
                .where(or_(Model.name.ilike(search_pattern), Model.display_name.ilike(search_pattern)))
                .where(not Model.is_deleted)
            )

            if enabled_only:
                stmt = stmt.where(Model.is_enabled)

            if provider_id:
                stmt = stmt.where(Model.provider_id == provider_id)

            stmt = stmt.order_by(Model.name)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_models_by_cost_range(
        self,
        min_cost_per_token: float | None = None,
        max_cost_per_token: float | None = None,
        token_type: str = "input",  # 'input' or 'output'
    ) -> list[Model]:
        """Get models within a cost range."""
        async with self.db_manager.get_session() as session:
            stmt = select(Model).where(not Model.is_deleted)

            cost_column = Model.cost_per_input_token if token_type == "input" else Model.cost_per_output_token

            if min_cost_per_token is not None:
                stmt = stmt.where(cost_column >= min_cost_per_token)

            if max_cost_per_token is not None:
                stmt = stmt.where(cost_column <= max_cost_per_token)

            stmt = stmt.order_by(cost_column)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_models_by_performance(
        self, max_latency_p95: float | None = None, min_quality_score: float | None = None
    ) -> list[Model]:
        """Get models by performance criteria."""
        async with self.db_manager.get_session() as session:
            stmt = select(Model).where(not Model.is_deleted)

            if max_latency_p95 is not None:
                stmt = stmt.where(Model.latency_p95_ms <= max_latency_p95)

            if min_quality_score is not None:
                stmt = stmt.where(Model.quality_score >= min_quality_score)

            stmt = stmt.order_by(Model.quality_score.desc(), Model.latency_p95_ms)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_performance_metrics(
        self,
        model_id: UUID,
        latency_p50_ms: float | None = None,
        latency_p95_ms: float | None = None,
        quality_score: float | None = None,
    ) -> bool:
        """Update model performance metrics."""
        updates = {}

        if latency_p50_ms is not None:
            updates["latency_p50_ms"] = latency_p50_ms

        if latency_p95_ms is not None:
            updates["latency_p95_ms"] = latency_p95_ms

        if quality_score is not None:
            updates["quality_score"] = quality_score

        if not updates:
            return False

        updated_model = await self.update(model_id, **updates)
        return updated_model is not None

    async def update_pricing(
        self,
        model_id: UUID,
        cost_per_input_token: float | None = None,
        cost_per_output_token: float | None = None,
        cost_per_request: float | None = None,
    ) -> bool:
        """Update model pricing information."""
        updates = {}

        if cost_per_input_token is not None:
            updates["cost_per_input_token"] = cost_per_input_token

        if cost_per_output_token is not None:
            updates["cost_per_output_token"] = cost_per_output_token

        if cost_per_request is not None:
            updates["cost_per_request"] = cost_per_request

        if not updates:
            return False

        updated_model = await self.update(model_id, **updates)
        return updated_model is not None

    async def promote_shadow_model(self, model_id: UUID) -> bool:
        """Promote a shadow model to active status."""
        model = await self.get_by_id(model_id)
        if not model or model.status != "shadow":
            return False

        updated_model = await self.update(model_id, status="active")
        return updated_model is not None

    async def demote_to_shadow(self, model_id: UUID) -> bool:
        """Demote an active model to shadow status."""
        model = await self.get_by_id(model_id)
        if not model or model.status != "active":
            return False

        updated_model = await self.update(model_id, status="shadow")
        return updated_model is not None

    async def deprecate_model(self, model_id: UUID) -> bool:
        """Mark a model as deprecated."""
        updated_model = await self.update(model_id, status="deprecated", is_enabled=False)
        return updated_model is not None

    async def get_model_statistics(self) -> dict[str, Any]:
        """Get overall model statistics."""
        async with self.db_manager.get_session() as session:
            # Total models
            total_stmt = select(func.count(Model.id)).where(not Model.is_deleted)
            total_result = await session.execute(total_stmt)
            total_models = total_result.scalar() or 0

            # Models by status
            status_stmt = select(Model.status, func.count(Model.id)).where(not Model.is_deleted).group_by(Model.status)
            status_result = await session.execute(status_stmt)
            models_by_status = {row[0]: row[1] for row in status_result.all()}

            # Enabled models
            enabled_stmt = select(func.count(Model.id)).where(and_(not Model.is_deleted, Model.is_enabled))
            enabled_result = await session.execute(enabled_stmt)
            enabled_models = enabled_result.scalar() or 0

            # Average costs
            cost_stmt = select(
                func.avg(Model.cost_per_input_token).label("avg_input_cost"),
                func.avg(Model.cost_per_output_token).label("avg_output_cost"),
                func.avg(Model.latency_p95_ms).label("avg_latency_p95"),
                func.avg(Model.quality_score).label("avg_quality_score"),
            ).where(not Model.is_deleted)

            cost_result = await session.execute(cost_stmt)
            cost_row = cost_result.first()

            return {
                "total_models": total_models,
                "enabled_models": enabled_models,
                "disabled_models": total_models - enabled_models,
                "models_by_status": models_by_status,
                "avg_input_cost_per_token": float(cost_row.avg_input_cost or 0),
                "avg_output_cost_per_token": float(cost_row.avg_output_cost or 0),
                "avg_latency_p95_ms": float(cost_row.avg_latency_p95 or 0),
                "avg_quality_score": float(cost_row.avg_quality_score or 0),
            }

    async def get_cheapest_models(self, limit: int = 10) -> list[Model]:
        """Get the cheapest models by input token cost."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Model)
                .where(not Model.is_deleted)
                .where(Model.is_enabled)
                .where(Model.cost_per_input_token.is_not(None))
                .order_by(Model.cost_per_input_token)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_fastest_models(self, limit: int = 10) -> list[Model]:
        """Get the fastest models by P95 latency."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Model)
                .where(not Model.is_deleted)
                .where(Model.is_enabled)
                .where(Model.latency_p95_ms.is_not(None))
                .order_by(Model.latency_p95_ms)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_highest_quality_models(self, limit: int = 10) -> list[Model]:
        """Get the highest quality models."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Model)
                .where(not Model.is_deleted)
                .where(Model.is_enabled)
                .where(Model.quality_score.is_not(None))
                .order_by(Model.quality_score.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())
