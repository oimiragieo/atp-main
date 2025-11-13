"""Request repository with specialized query methods."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import selectinload

from ..models.database import Request
from .base import BaseRepository

logger = logging.getLogger(__name__)


class RequestRepository(BaseRepository[Request]):
    """Repository for Request entities with specialized query methods."""

    def __init__(self):
        super().__init__(Request)

    async def get_by_correlation_id(self, correlation_id: str) -> Request | None:
        """Get request by correlation ID."""
        return await self.find_one_by(correlation_id=correlation_id)

    async def get_by_session(self, session_id: str, page: int = 1, page_size: int = 50) -> list[Request]:
        """Get requests by session ID."""
        return await self.get_all(
            page=page, page_size=page_size, filters={"session_id": session_id}, order_by="-created_at"
        )

    async def get_by_user(
        self, user_id: str, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[Request]:
        """Get requests by user ID with optional tenant filtering."""
        filters = {"user_id": user_id}
        if tenant_id:
            filters["tenant_id"] = tenant_id

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-created_at")

    async def get_recent_requests(
        self, hours: int = 24, tenant_id: str | None = None, page: int = 1, page_size: int = 100
    ) -> list[Request]:
        """Get recent requests within specified hours."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(Request).where(Request.created_at >= cutoff_time).where(not Request.is_deleted)

            if tenant_id:
                stmt = stmt.where(Request.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Request.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_failed_requests(
        self, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[Request]:
        """Get requests with error status codes."""
        async with self.db_manager.get_session() as session:
            stmt = select(Request).where(Request.status_code >= 400).where(not Request.is_deleted)

            if tenant_id:
                stmt = stmt.where(Request.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Request.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_requests_by_model(
        self, model_name: str, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[Request]:
        """Get requests that used a specific model."""
        filters = {"model_used": model_name}
        if tenant_id:
            filters["tenant_id"] = tenant_id

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-created_at")

    async def get_requests_by_provider(
        self, provider_name: str, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[Request]:
        """Get requests that used a specific provider."""
        filters = {"provider_used": provider_name}
        if tenant_id:
            filters["tenant_id"] = tenant_id

        return await self.get_all(page=page, page_size=page_size, filters=filters, order_by="-created_at")

    async def get_cost_summary(
        self,
        tenant_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get cost summary for requests."""
        async with self.db_manager.get_session() as session:
            stmt = select(
                func.count(Request.id).label("total_requests"),
                func.sum(Request.cost_usd).label("total_cost"),
                func.avg(Request.cost_usd).label("avg_cost"),
                func.sum(Request.tokens_input).label("total_input_tokens"),
                func.sum(Request.tokens_output).label("total_output_tokens"),
            ).where(not Request.is_deleted)

            if tenant_id:
                stmt = stmt.where(Request.tenant_id == tenant_id)

            if start_date:
                stmt = stmt.where(Request.created_at >= start_date)

            if end_date:
                stmt = stmt.where(Request.created_at <= end_date)

            result = await session.execute(stmt)
            row = result.first()

            return {
                "total_requests": row.total_requests or 0,
                "total_cost_usd": float(row.total_cost or 0),
                "avg_cost_usd": float(row.avg_cost or 0),
                "total_input_tokens": row.total_input_tokens or 0,
                "total_output_tokens": row.total_output_tokens or 0,
            }

    async def get_performance_summary(
        self,
        tenant_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get performance summary for requests."""
        async with self.db_manager.get_session() as session:
            stmt = select(
                func.count(Request.id).label("total_requests"),
                func.avg(Request.response_time_ms).label("avg_response_time"),
                func.percentile_cont(0.5).within_group(Request.response_time_ms).label("p50_response_time"),
                func.percentile_cont(0.95).within_group(Request.response_time_ms).label("p95_response_time"),
                func.avg(Request.quality_score).label("avg_quality_score"),
                func.avg(Request.confidence_score).label("avg_confidence_score"),
            ).where(not Request.is_deleted)

            if tenant_id:
                stmt = stmt.where(Request.tenant_id == tenant_id)

            if start_date:
                stmt = stmt.where(Request.created_at >= start_date)

            if end_date:
                stmt = stmt.where(Request.created_at <= end_date)

            result = await session.execute(stmt)
            row = result.first()

            return {
                "total_requests": row.total_requests or 0,
                "avg_response_time_ms": float(row.avg_response_time or 0),
                "p50_response_time_ms": float(row.p50_response_time or 0),
                "p95_response_time_ms": float(row.p95_response_time or 0),
                "avg_quality_score": float(row.avg_quality_score or 0),
                "avg_confidence_score": float(row.avg_confidence_score or 0),
            }

    async def get_error_summary(
        self,
        tenant_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get error summary for requests."""
        async with self.db_manager.get_session() as session:
            # Total requests
            total_stmt = select(func.count(Request.id)).where(not Request.is_deleted)

            # Error requests
            error_stmt = select(func.count(Request.id)).where(and_(not Request.is_deleted, Request.status_code >= 400))

            # Apply filters
            if tenant_id:
                total_stmt = total_stmt.where(Request.tenant_id == tenant_id)
                error_stmt = error_stmt.where(Request.tenant_id == tenant_id)

            if start_date:
                total_stmt = total_stmt.where(Request.created_at >= start_date)
                error_stmt = error_stmt.where(Request.created_at >= start_date)

            if end_date:
                total_stmt = total_stmt.where(Request.created_at <= end_date)
                error_stmt = error_stmt.where(Request.created_at <= end_date)

            total_result = await session.execute(total_stmt)
            error_result = await session.execute(error_stmt)

            total_requests = total_result.scalar() or 0
            error_requests = error_result.scalar() or 0

            error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

            return {
                "total_requests": total_requests,
                "error_requests": error_requests,
                "success_requests": total_requests - error_requests,
                "error_rate_percent": round(error_rate, 2),
            }

    async def search_by_prompt(
        self, search_term: str, tenant_id: str | None = None, page: int = 1, page_size: int = 50
    ) -> list[Request]:
        """Search requests by prompt content."""
        async with self.db_manager.get_session() as session:
            # Escape wildcards to prevent SQL injection
            safe_search = search_term.replace("%", "\\%").replace("_", "\\_")
            search_pattern = f"%{safe_search}%"
            stmt = select(Request).where(Request.prompt.ilike(search_pattern)).where(not Request.is_deleted)

            if tenant_id:
                stmt = stmt.where(Request.tenant_id == tenant_id)

            stmt = stmt.order_by(desc(Request.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_with_responses(self, request_id: UUID) -> Request | None:
        """Get request with all its responses."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Request)
                .where(Request.id == request_id)
                .where(not Request.is_deleted)
                .options(selectinload(Request.responses))
            )

            result = await session.execute(stmt)
            return result.scalar_one_or_none()
