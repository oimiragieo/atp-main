"""Provider repository with specialized query methods."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.database import Provider, Model
from .base import BaseRepository

logger = logging.getLogger(__name__)


class ProviderRepository(BaseRepository[Provider]):
    """Repository for Provider entities with specialized query methods."""
    
    def __init__(self):
        super().__init__(Provider)
    
    async def get_by_name(self, name: str) -> Optional[Provider]:
        """Get provider by name."""
        return await self.find_one_by(name=name)
    
    async def get_enabled_providers(self) -> List[Provider]:
        """Get all enabled providers."""
        return await self.find_by(is_enabled=True)
    
    async def get_by_type(self, provider_type: str) -> List[Provider]:
        """Get providers by type."""
        return await self.find_by(provider_type=provider_type)
    
    async def get_healthy_providers(self) -> List[Provider]:
        """Get providers with healthy status."""
        return await self.find_by(health_status='healthy', is_enabled=True)
    
    async def get_with_models(self, provider_id: UUID) -> Optional[Provider]:
        """Get provider with all its models."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Provider)
                .where(Provider.id == provider_id)
                .where(Provider.is_deleted == False)
                .options(selectinload(Provider.models))
            )
            
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def get_providers_with_model_count(self) -> List[Dict[str, Any]]:
        """Get providers with their model counts."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(
                    Provider,
                    func.count(Model.id).label('model_count')
                )
                .outerjoin(Model, and_(
                    Model.provider_id == Provider.id,
                    Model.is_deleted == False
                ))
                .where(Provider.is_deleted == False)
                .group_by(Provider.id)
                .order_by(Provider.name)
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            return [
                {
                    'provider': row.Provider,
                    'model_count': row.model_count
                }
                for row in rows
            ]
    
    async def update_health_status(
        self,
        provider_id: UUID,
        health_status: str,
        last_health_check: Optional[datetime] = None
    ) -> bool:
        """Update provider health status."""
        updates = {
            'health_status': health_status,
            'last_health_check': last_health_check or datetime.utcnow()
        }
        
        updated_provider = await self.update(provider_id, **updates)
        return updated_provider is not None
    
    async def get_stale_health_checks(self, hours: int = 1) -> List[Provider]:
        """Get providers with stale health checks."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            stmt = (
                select(Provider)
                .where(Provider.is_deleted == False)
                .where(Provider.is_enabled == True)
                .where(
                    or_(
                        Provider.last_health_check.is_(None),
                        Provider.last_health_check < cutoff_time
                    )
                )
                .order_by(Provider.last_health_check.asc().nulls_first())
            )
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def bulk_update_health_status(
        self,
        provider_updates: List[Dict[str, Any]]
    ) -> int:
        """Bulk update health status for multiple providers."""
        updated_count = 0
        
        async with self.db_manager.get_session() as session:
            for update_data in provider_updates:
                provider_id = update_data.get('provider_id')
                health_status = update_data.get('health_status')
                
                if provider_id and health_status:
                    success = await self.update_health_status(
                        provider_id,
                        health_status,
                        datetime.utcnow()
                    )
                    if success:
                        updated_count += 1
        
        return updated_count
    
    async def get_provider_capabilities(self, provider_id: UUID) -> Dict[str, Any]:
        """Get provider capabilities summary."""
        provider = await self.get_by_id(provider_id)
        if not provider:
            return {}
        
        return {
            'provider_id': str(provider.id),
            'name': provider.name,
            'provider_type': provider.provider_type,
            'supports_streaming': provider.supports_streaming,
            'supports_function_calling': provider.supports_function_calling,
            'supports_vision': provider.supports_vision,
            'is_enabled': provider.is_enabled,
            'health_status': provider.health_status,
            'last_health_check': provider.last_health_check.isoformat() if provider.last_health_check else None
        }
    
    async def search_providers(
        self,
        search_term: str,
        provider_type: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[Provider]:
        """Search providers by name or display name."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(Provider)
                .where(
                    or_(
                        Provider.name.ilike(f'%{search_term}%'),
                        Provider.display_name.ilike(f'%{search_term}%')
                    )
                )
                .where(Provider.is_deleted == False)
            )
            
            if enabled_only:
                stmt = stmt.where(Provider.is_enabled == True)
            
            if provider_type:
                stmt = stmt.where(Provider.provider_type == provider_type)
            
            stmt = stmt.order_by(Provider.name)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_provider_statistics(self) -> Dict[str, Any]:
        """Get overall provider statistics."""
        async with self.db_manager.get_session() as session:
            # Total providers
            total_stmt = select(func.count(Provider.id)).where(Provider.is_deleted == False)
            total_result = await session.execute(total_stmt)
            total_providers = total_result.scalar() or 0
            
            # Enabled providers
            enabled_stmt = select(func.count(Provider.id)).where(
                and_(Provider.is_deleted == False, Provider.is_enabled == True)
            )
            enabled_result = await session.execute(enabled_stmt)
            enabled_providers = enabled_result.scalar() or 0
            
            # Healthy providers
            healthy_stmt = select(func.count(Provider.id)).where(
                and_(
                    Provider.is_deleted == False,
                    Provider.is_enabled == True,
                    Provider.health_status == 'healthy'
                )
            )
            healthy_result = await session.execute(healthy_stmt)
            healthy_providers = healthy_result.scalar() or 0
            
            # Provider types
            types_stmt = (
                select(Provider.provider_type, func.count(Provider.id))
                .where(Provider.is_deleted == False)
                .group_by(Provider.provider_type)
            )
            types_result = await session.execute(types_stmt)
            provider_types = {row[0]: row[1] for row in types_result.all()}
            
            return {
                'total_providers': total_providers,
                'enabled_providers': enabled_providers,
                'disabled_providers': total_providers - enabled_providers,
                'healthy_providers': healthy_providers,
                'unhealthy_providers': enabled_providers - healthy_providers,
                'provider_types': provider_types
            }