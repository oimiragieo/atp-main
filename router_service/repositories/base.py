"""Base repository class with common CRUD operations and caching."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from ..database import get_database_manager
from ..models.database import Base

logger = logging.getLogger(__name__)

# Type variable for model classes
ModelType = TypeVar("ModelType", bound=Base)


class CacheEntry:
    """Cache entry with TTL support."""
    
    def __init__(self, data: Any, ttl_seconds: int = 300):
        self.data = data
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class BaseRepository(Generic[ModelType], ABC):
    """Base repository class with common CRUD operations and caching."""
    
    def __init__(self, model_class: Type[ModelType]):
        self.model_class = model_class
        self.db_manager = get_database_manager()
        
        # L1 cache (in-memory)
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_enabled = True
        self._default_ttl = 300  # 5 minutes
        
        # Query optimization settings
        self._default_page_size = 50
        self._max_page_size = 1000
    
    async def _execute_with_session(self, operation):
        """Execute an operation with the appropriate session."""
        if hasattr(self, '_transaction_session'):
            # Use existing transaction session
            return await operation(self._transaction_session)
        else:
            # Create new session
            async with self.db_manager.get_session() as session:
                return await operation(session)
    
    # Cache management
    def _get_cache_key(self, key: Union[str, UUID, int]) -> str:
        """Generate cache key."""
        return f"{self.model_class.__tablename__}:{str(key)}"
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get item from L1 cache."""
        if not self._cache_enabled:
            return None
        
        entry = self._cache.get(key)
        if entry and not entry.is_expired():
            return entry.data
        elif entry:
            # Remove expired entry
            del self._cache[key]
        
        return None
    
    def _set_cache(self, key: str, data: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set item in L1 cache."""
        if not self._cache_enabled:
            return
        
        ttl = ttl_seconds or self._default_ttl
        self._cache[key] = CacheEntry(data, ttl)
    
    def _invalidate_cache(self, key: Optional[str] = None) -> None:
        """Invalidate cache entry or entire cache."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()
    
    # CRUD operations
    async def create(self, **kwargs) -> ModelType:
        """Create a new entity."""
        async def _create_operation(session):
            entity = self.model_class(**kwargs)
            session.add(entity)
            
            if hasattr(self, '_transaction_session'):
                # In transaction - just flush to get ID
                await session.flush()
            else:
                # Not in transaction - commit
                await session.commit()
            
            await session.refresh(entity)
            
            # Cache the new entity
            cache_key = self._get_cache_key(entity.id)
            self._set_cache(cache_key, entity)
            
            logger.debug(f"Created {self.model_class.__name__} with id {entity.id}")
            return entity
        
        return await self._execute_with_session(_create_operation)
    
    async def get_by_id(self, entity_id: Union[UUID, str, int]) -> Optional[ModelType]:
        """Get entity by ID with caching."""
        cache_key = self._get_cache_key(entity_id)
        
        # Check L1 cache first
        cached_entity = self._get_from_cache(cache_key)
        if cached_entity:
            return cached_entity
        
        # Query database
        async def _get_operation(session):
            stmt = select(self.model_class).where(self.model_class.id == entity_id)
            
            # Add soft delete filter if model supports it
            if hasattr(self.model_class, 'is_deleted'):
                stmt = stmt.where(self.model_class.is_deleted == False)
            
            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()
            
            if entity:
                # Cache the result
                self._set_cache(cache_key, entity)
            
            return entity
        
        return await self._execute_with_session(_get_operation)
    
    async def get_all(
        self,
        page: int = 1,
        page_size: int = None,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[ModelType]:
        """Get all entities with pagination and filtering."""
        page_size = min(page_size or self._default_page_size, self._max_page_size)
        offset = (page - 1) * page_size
        
        async with self.db_manager.get_session() as session:
            stmt = select(self.model_class)
            
            # Apply soft delete filter
            if hasattr(self.model_class, 'is_deleted') and not include_deleted:
                stmt = stmt.where(self.model_class.is_deleted == False)
            
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
                if order_by.startswith('-'):
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
                if hasattr(self.model_class, 'created_at'):
                    stmt = stmt.order_by(desc(self.model_class.created_at))
            
            # Apply pagination
            stmt = stmt.offset(offset).limit(page_size)
            
            result = await session.execute(stmt)
            entities = result.scalars().all()
            
            return list(entities)
    
    async def count(
        self,
        filters: Optional[Dict[str, Any]] = None,
        include_deleted: bool = False
    ) -> int:
        """Count entities with optional filtering."""
        async with self.db_manager.get_session() as session:
            stmt = select(func.count(self.model_class.id))
            
            # Apply soft delete filter
            if hasattr(self.model_class, 'is_deleted') and not include_deleted:
                stmt = stmt.where(self.model_class.is_deleted == False)
            
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
            return result.scalar() or 0
    
    async def update(self, entity_id: Union[UUID, str, int], **kwargs) -> Optional[ModelType]:
        """Update entity by ID."""
        async with self.db_manager.get_session() as session:
            # Add updated_at timestamp if model supports it
            if hasattr(self.model_class, 'updated_at'):
                kwargs['updated_at'] = datetime.utcnow()
            
            stmt = (
                update(self.model_class)
                .where(self.model_class.id == entity_id)
                .values(**kwargs)
                .returning(self.model_class)
            )
            
            # Add soft delete filter if model supports it
            if hasattr(self.model_class, 'is_deleted'):
                stmt = stmt.where(self.model_class.is_deleted == False)
            
            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()
            
            if entity:
                await session.commit()
                
                # Invalidate cache
                cache_key = self._get_cache_key(entity_id)
                self._invalidate_cache(cache_key)
                
                logger.debug(f"Updated {self.model_class.__name__} with id {entity_id}")
            
            return entity
    
    async def delete(self, entity_id: Union[UUID, str, int], soft_delete: bool = True) -> bool:
        """Delete entity by ID (soft delete by default)."""
        async with self.db_manager.get_session() as session:
            if soft_delete and hasattr(self.model_class, 'is_deleted'):
                # Soft delete
                stmt = (
                    update(self.model_class)
                    .where(self.model_class.id == entity_id)
                    .where(self.model_class.is_deleted == False)
                    .values(
                        is_deleted=True,
                        deleted_at=datetime.utcnow(),
                        updated_at=datetime.utcnow() if hasattr(self.model_class, 'updated_at') else None
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
                await session.commit()
                
                # Invalidate cache
                cache_key = self._get_cache_key(entity_id)
                self._invalidate_cache(cache_key)
                
                logger.debug(f"Deleted {self.model_class.__name__} with id {entity_id}")
            
            return success
    
    async def bulk_create(self, entities_data: List[Dict[str, Any]]) -> List[ModelType]:
        """Bulk create entities."""
        async with self.db_manager.get_session() as session:
            entities = [self.model_class(**data) for data in entities_data]
            session.add_all(entities)
            await session.commit()
            
            # Refresh all entities to get generated IDs
            for entity in entities:
                await session.refresh(entity)
            
            logger.debug(f"Bulk created {len(entities)} {self.model_class.__name__} entities")
            return entities
    
    async def bulk_update(
        self,
        filters: Dict[str, Any],
        updates: Dict[str, Any]
    ) -> int:
        """Bulk update entities matching filters."""
        async with self.db_manager.get_session() as session:
            stmt = update(self.model_class)
            
            # Apply filters
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    column = getattr(self.model_class, key)
                    stmt = stmt.where(column == value)
            
            # Add updated_at timestamp if model supports it
            if hasattr(self.model_class, 'updated_at'):
                updates['updated_at'] = datetime.utcnow()
            
            stmt = stmt.values(**updates)
            
            result = await session.execute(stmt)
            updated_count = result.rowcount
            
            if updated_count > 0:
                await session.commit()
                
                # Invalidate entire cache for this model
                self._invalidate_cache()
                
                logger.debug(f"Bulk updated {updated_count} {self.model_class.__name__} entities")
            
            return updated_count
    
    # Advanced query methods
    async def find_by(self, **kwargs) -> List[ModelType]:
        """Find entities by arbitrary field values."""
        return await self.get_all(filters=kwargs)
    
    async def find_one_by(self, **kwargs) -> Optional[ModelType]:
        """Find single entity by arbitrary field values."""
        entities = await self.get_all(filters=kwargs, page_size=1)
        return entities[0] if entities else None
    
    async def exists(self, entity_id: Union[UUID, str, int]) -> bool:
        """Check if entity exists."""
        entity = await self.get_by_id(entity_id)
        return entity is not None
    
    # Tenant-aware methods (for models with tenant_id)
    async def get_by_tenant(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """Get entities filtered by tenant ID."""
        if not hasattr(self.model_class, 'tenant_id'):
            raise ValueError(f"{self.model_class.__name__} does not support tenant filtering")
        
        tenant_filters = {'tenant_id': tenant_id}
        if filters:
            tenant_filters.update(filters)
        
        return await self.get_all(
            page=page,
            page_size=page_size,
            filters=tenant_filters
        )
    
    async def count_by_tenant(
        self,
        tenant_id: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count entities filtered by tenant ID."""
        if not hasattr(self.model_class, 'tenant_id'):
            raise ValueError(f"{self.model_class.__name__} does not support tenant filtering")
        
        tenant_filters = {'tenant_id': tenant_id}
        if filters:
            tenant_filters.update(filters)
        
        return await self.count(filters=tenant_filters)
    
    # Cache management methods
    def enable_cache(self) -> None:
        """Enable L1 caching."""
        self._cache_enabled = True
    
    def disable_cache(self) -> None:
        """Disable L1 caching."""
        self._cache_enabled = False
        self._cache.clear()
    
    def clear_cache(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self._cache)
        expired_entries = sum(1 for entry in self._cache.values() if entry.is_expired())
        
        return {
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "cache_enabled": self._cache_enabled
        }