"""Enhanced base repository with multi-tier caching support."""

from __future__ import annotations

import json
import logging
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import desc, func, select, update

from ..cache import get_cache_manager
from ..database import get_database_manager
from ..models.database import Base

logger = logging.getLogger(__name__)

# Type variable for model classes
ModelType = TypeVar("ModelType", bound=Base)


class CachedBaseRepository(Generic[ModelType]):
    """Enhanced base repository with multi-tier caching support."""

    def __init__(self, model_class: type[ModelType], cache_prefix: str | None = None):
        self.model_class = model_class
        self.db_manager = get_database_manager()
        self.cache_manager = get_cache_manager()

        # Cache configuration
        self.cache_prefix = cache_prefix or f"{model_class.__tablename__}:"
        self.default_ttl = 300  # 5 minutes
        self.list_cache_ttl = 60  # 1 minute for list queries

        # Query optimization settings
        self._default_page_size = 50
        self._max_page_size = 1000

    async def _execute_with_session(self, operation):
        """Execute an operation with the appropriate session."""
        if hasattr(self, "_transaction_session"):
            # Use existing transaction session
            return await operation(self._transaction_session)
        else:
            # Create new session
            async with self.db_manager.get_session() as session:
                return await operation(session)

    def _make_cache_key(self, key: str | UUID | int, suffix: str = "") -> str:
        """Generate cache key with prefix."""
        base_key = f"{self.cache_prefix}{str(key)}"
        return f"{base_key}:{suffix}" if suffix else base_key

    def _make_list_cache_key(
        self, filters: dict[str, Any] | None = None, page: int = 1, page_size: int = 50, order_by: str | None = None
    ) -> str:
        """Generate cache key for list queries."""
        # Create a deterministic key from query parameters
        key_parts = [f"page:{page}", f"size:{page_size}", f"order:{order_by or 'default'}"]

        if filters:
            # Sort filters for consistent key generation
            sorted_filters = sorted(filters.items())
            filter_str = json.dumps(sorted_filters, sort_keys=True, default=str)
            key_parts.append(f"filters:{hash(filter_str)}")

        return self._make_cache_key("list", ":".join(key_parts))

    async def _invalidate_related_caches(self, entity_id: UUID | str | int) -> None:
        """Invalidate caches related to an entity."""
        # Invalidate direct cache
        await self.cache_manager.invalidate(self._make_cache_key(entity_id))

        # Invalidate list caches (pattern-based)
        list_pattern = self._make_cache_key("list", "*")
        await self.cache_manager.invalidate_pattern(list_pattern)

        # Invalidate count caches
        count_pattern = self._make_cache_key("count", "*")
        await self.cache_manager.invalidate_pattern(count_pattern)

    # CRUD operations with caching
    async def create(self, **kwargs) -> ModelType:
        """Create a new entity with cache invalidation."""

        async def _create_operation(session):
            entity = self.model_class(**kwargs)
            session.add(entity)

            if hasattr(self, "_transaction_session"):
                # In transaction - just flush to get ID
                await session.flush()
            else:
                # Not in transaction - commit
                await session.commit()

            await session.refresh(entity)

            # Cache the new entity
            cache_key = self._make_cache_key(entity.id)
            await self.cache_manager.set(cache_key, entity, self.default_ttl)

            # Invalidate list caches
            await self._invalidate_related_caches(entity.id)

            logger.debug(f"Created {self.model_class.__name__} with id {entity.id}")
            return entity

        return await self._execute_with_session(_create_operation)

    async def get_by_id(self, entity_id: UUID | str | int) -> ModelType | None:
        """Get entity by ID with caching."""
        cache_key = self._make_cache_key(entity_id)

        # Try cache first
        cached_entity = await self.cache_manager.get(cache_key)
        if cached_entity is not None:
            return cached_entity

        # Query database
        async def _get_operation(session):
            stmt = select(self.model_class).where(self.model_class.id == entity_id)

            # Add soft delete filter if model supports it
            if hasattr(self.model_class, "is_deleted"):
                stmt = stmt.where(not self.model_class.is_deleted)

            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()

            if entity:
                # Cache the result
                await self.cache_manager.set(cache_key, entity, self.default_ttl)

            return entity

        return await self._execute_with_session(_get_operation)

    async def get_all(
        self,
        page: int = 1,
        page_size: int = None,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        include_deleted: bool = False,
        use_cache: bool = True,
    ) -> list[ModelType]:
        """Get all entities with pagination, filtering, and caching."""
        page_size = min(page_size or self._default_page_size, self._max_page_size)

        # Try cache first if enabled
        if use_cache:
            cache_key = self._make_list_cache_key(filters, page, page_size, order_by)
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result

        async def _get_all_operation(session):
            offset = (page - 1) * page_size

            stmt = select(self.model_class)

            # Apply soft delete filter
            if hasattr(self.model_class, "is_deleted") and not include_deleted:
                stmt = stmt.where(not self.model_class.is_deleted)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        column = getattr(self.model_class, key)
                        if isinstance(value, list):
                            stmt = stmt.where(column.in_(value))
                        else:
                            stmt = stmt.where(column == value)

            # Apply ordering
            if order_by:
                if order_by.startswith("-"):
                    # Descending order
                    column_name = order_by[1:]
                    if hasattr(self.model_class, column_name):
                        column = getattr(self.model_class, column_name)
                        stmt = stmt.order_by(desc(column))
                else:
                    # Ascending order
                    if hasattr(self.model_class, order_by):
                        column = getattr(self.model_class, order_by)
                        stmt = stmt.order_by(column)
            else:
                # Default ordering by created_at if available
                if hasattr(self.model_class, "created_at"):
                    stmt = stmt.order_by(desc(self.model_class.created_at))

            # Apply pagination
            stmt = stmt.offset(offset).limit(page_size)

            result = await session.execute(stmt)
            entities = list(result.scalars().all())

            # Cache the result if enabled
            if use_cache:
                cache_key = self._make_list_cache_key(filters, page, page_size, order_by)
                await self.cache_manager.set(cache_key, entities, self.list_cache_ttl)

            return entities

        return await self._execute_with_session(_get_all_operation)

    async def count(
        self, filters: dict[str, Any] | None = None, include_deleted: bool = False, use_cache: bool = True
    ) -> int:
        """Count entities with optional filtering and caching."""
        # Try cache first if enabled
        if use_cache:
            cache_key = self._make_cache_key("count", json.dumps(filters or {}, sort_keys=True, default=str))
            cached_count = await self.cache_manager.get(cache_key)
            if cached_count is not None:
                return cached_count

        async def _count_operation(session):
            stmt = select(func.count(self.model_class.id))

            # Apply soft delete filter
            if hasattr(self.model_class, "is_deleted") and not include_deleted:
                stmt = stmt.where(not self.model_class.is_deleted)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        column = getattr(self.model_class, key)
                        if isinstance(value, list):
                            stmt = stmt.where(column.in_(value))
                        else:
                            stmt = stmt.where(column == value)

            result = await session.execute(stmt)
            count = result.scalar() or 0

            # Cache the result if enabled
            if use_cache:
                cache_key = self._make_cache_key("count", json.dumps(filters or {}, sort_keys=True, default=str))
                await self.cache_manager.set(cache_key, count, self.default_ttl)

            return count

        return await self._execute_with_session(_count_operation)

    async def update(self, entity_id: UUID | str | int, **kwargs) -> ModelType | None:
        """Update entity by ID with cache invalidation."""

        async def _update_operation(session):
            # Add updated_at timestamp if model supports it
            if hasattr(self.model_class, "updated_at"):
                from datetime import datetime

                kwargs["updated_at"] = datetime.utcnow()

            stmt = (
                update(self.model_class)
                .where(self.model_class.id == entity_id)
                .values(**kwargs)
                .returning(self.model_class)
            )

            # Add soft delete filter if model supports it
            if hasattr(self.model_class, "is_deleted"):
                stmt = stmt.where(not self.model_class.is_deleted)

            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()

            if entity:
                if not hasattr(self, "_transaction_session"):
                    await session.commit()

                # Update cache
                cache_key = self._make_cache_key(entity_id)
                await self.cache_manager.set(cache_key, entity, self.default_ttl)

                # Invalidate related caches
                await self._invalidate_related_caches(entity_id)

                logger.debug(f"Updated {self.model_class.__name__} with id {entity_id}")

            return entity

        return await self._execute_with_session(_update_operation)

    async def delete(self, entity_id: UUID | str | int, soft_delete: bool = True) -> bool:
        """Delete entity by ID with cache invalidation."""

        async def _delete_operation(session):
            if soft_delete and hasattr(self.model_class, "is_deleted"):
                # Soft delete
                from datetime import datetime

                stmt = (
                    update(self.model_class)
                    .where(self.model_class.id == entity_id)
                    .where(not self.model_class.is_deleted)
                    .values(
                        is_deleted=True,
                        deleted_at=datetime.utcnow(),
                        updated_at=datetime.utcnow() if hasattr(self.model_class, "updated_at") else None,
                    )
                )

                result = await session.execute(stmt)
                success = result.rowcount > 0
            else:
                # Hard delete
                entity = await session.get(self.model_class, entity_id)
                if entity:
                    await session.delete(entity)
                    success = True
                else:
                    success = False

            if success:
                if not hasattr(self, "_transaction_session"):
                    await session.commit()

                # Invalidate caches
                await self._invalidate_related_caches(entity_id)

                logger.debug(f"Deleted {self.model_class.__name__} with id {entity_id}")

            return success

        return await self._execute_with_session(_delete_operation)

    # Advanced query methods
    async def find_by(self, use_cache: bool = True, **kwargs) -> list[ModelType]:
        """Find entities by arbitrary field values."""
        return await self.get_all(filters=kwargs, use_cache=use_cache)

    async def find_one_by(self, use_cache: bool = True, **kwargs) -> ModelType | None:
        """Find single entity by arbitrary field values."""
        entities = await self.get_all(filters=kwargs, page_size=1, use_cache=use_cache)
        return entities[0] if entities else None

    async def exists(self, entity_id: UUID | str | int) -> bool:
        """Check if entity exists."""
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # Cache management methods
    async def clear_cache(self, entity_id: UUID | str | int | None = None) -> None:
        """Clear cache for specific entity or all entities of this type."""
        if entity_id:
            await self._invalidate_related_caches(entity_id)
        else:
            # Clear all caches for this model type
            pattern = f"{self.cache_prefix}*"
            await self.cache_manager.invalidate_pattern(pattern)

    async def warm_cache(self, entity_ids: list[UUID | str | int]) -> int:
        """Pre-warm cache with specific entities."""
        warmed_count = 0

        for entity_id in entity_ids:
            entity = await self.get_by_id(entity_id)
            if entity:
                warmed_count += 1

        return warmed_count

    def get_cache_statistics(self) -> dict[str, Any]:
        """Get cache statistics for this repository."""
        return self.cache_manager.get_statistics()
