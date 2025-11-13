"""Audit repository with specialized query methods."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import AuditLog
from .base import BaseRepository

logger = logging.getLogger(__name__)


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog entities with specialized query methods."""
    
    def __init__(self):
        super().__init__(AuditLog)
    
    async def get_by_event_type(
        self,
        event_type: str,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get audit logs by event type."""
        filters = {'event_type': event_type}
        if tenant_id:
            filters['tenant_id'] = tenant_id
        
        return await self.get_all(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by='-created_at'
        )
    
    async def get_by_user(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get audit logs for a specific user."""
        filters = {'user_id': user_id}
        if tenant_id:
            filters['tenant_id'] = tenant_id
        
        return await self.get_all(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by='-created_at'
        )
    
    async def get_by_correlation_id(self, correlation_id: str) -> List[AuditLog]:
        """Get all audit logs for a correlation ID."""
        return await self.find_by(correlation_id=correlation_id)
    
    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get audit logs for a specific resource."""
        filters = {'resource_type': resource_type}
        if resource_id:
            filters['resource_id'] = resource_id
        if tenant_id:
            filters['tenant_id'] = tenant_id
        
        return await self.get_all(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by='-created_at'
        )
    
    async def get_recent_events(
        self,
        hours: int = 24,
        tenant_id: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get recent audit events within specified hours."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            stmt = (
                select(AuditLog)
                .where(AuditLog.created_at >= cutoff_time)
            )
            
            if tenant_id:
                stmt = stmt.where(AuditLog.tenant_id == tenant_id)
            
            if event_types:
                stmt = stmt.where(AuditLog.event_type.in_(event_types))
            
            stmt = stmt.order_by(desc(AuditLog.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_failed_events(
        self,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get audit logs with failure outcomes."""
        filters = {'outcome': 'failure'}
        if tenant_id:
            filters['tenant_id'] = tenant_id
        
        return await self.get_all(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by='-created_at'
        )
    
    async def get_security_events(
        self,
        tenant_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Get security-related audit events."""
        security_event_types = [
            'user_login',
            'user_logout',
            'authentication_failed',
            'authorization_denied',
            'policy_violation',
            'admin_action',
            'privilege_escalation'
        ]
        
        async with self.db_manager.get_session() as session:
            stmt = (
                select(AuditLog)
                .where(AuditLog.event_type.in_(security_event_types))
            )
            
            if tenant_id:
                stmt = stmt.where(AuditLog.tenant_id == tenant_id)
            
            stmt = stmt.order_by(desc(AuditLog.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def search_events(
        self,
        search_term: str,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AuditLog]:
        """Search audit events by various fields."""
        async with self.db_manager.get_session() as session:
            stmt = (
                select(AuditLog)
                .where(
                    or_(
                        AuditLog.event_type.ilike(f'%{search_term}%'),
                        AuditLog.action.ilike(f'%{search_term}%'),
                        AuditLog.user_id.ilike(f'%{search_term}%'),
                        AuditLog.resource_type.ilike(f'%{search_term}%'),
                        AuditLog.resource_id.ilike(f'%{search_term}%')
                    )
                )
            )
            
            if tenant_id:
                stmt = stmt.where(AuditLog.tenant_id == tenant_id)
            
            if start_date:
                stmt = stmt.where(AuditLog.created_at >= start_date)
            
            if end_date:
                stmt = stmt.where(AuditLog.created_at <= end_date)
            
            stmt = stmt.order_by(desc(AuditLog.created_at))
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def get_event_statistics(
        self,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit event statistics."""
        async with self.db_manager.get_session() as session:
            # Base query
            base_stmt = select(func.count(AuditLog.id))
            
            if tenant_id:
                base_stmt = base_stmt.where(AuditLog.tenant_id == tenant_id)
            
            if start_date:
                base_stmt = base_stmt.where(AuditLog.created_at >= start_date)
            
            if end_date:
                base_stmt = base_stmt.where(AuditLog.created_at <= end_date)
            
            # Total events
            total_result = await session.execute(base_stmt)
            total_events = total_result.scalar() or 0
            
            # Events by outcome
            outcome_stmt = (
                select(AuditLog.outcome, func.count(AuditLog.id))
                .group_by(AuditLog.outcome)
            )
            
            if tenant_id:
                outcome_stmt = outcome_stmt.where(AuditLog.tenant_id == tenant_id)
            
            if start_date:
                outcome_stmt = outcome_stmt.where(AuditLog.created_at >= start_date)
            
            if end_date:
                outcome_stmt = outcome_stmt.where(AuditLog.created_at <= end_date)
            
            outcome_result = await session.execute(outcome_stmt)
            events_by_outcome = {row[0]: row[1] for row in outcome_result.all()}
            
            # Events by type (top 10)
            type_stmt = (
                select(AuditLog.event_type, func.count(AuditLog.id))
                .group_by(AuditLog.event_type)
                .order_by(func.count(AuditLog.id).desc())
                .limit(10)
            )
            
            if tenant_id:
                type_stmt = type_stmt.where(AuditLog.tenant_id == tenant_id)
            
            if start_date:
                type_stmt = type_stmt.where(AuditLog.created_at >= start_date)
            
            if end_date:
                type_stmt = type_stmt.where(AuditLog.created_at <= end_date)
            
            type_result = await session.execute(type_stmt)
            events_by_type = {row[0]: row[1] for row in type_result.all()}
            
            # Unique users
            users_stmt = select(func.count(func.distinct(AuditLog.user_id)))
            
            if tenant_id:
                users_stmt = users_stmt.where(AuditLog.tenant_id == tenant_id)
            
            if start_date:
                users_stmt = users_stmt.where(AuditLog.created_at >= start_date)
            
            if end_date:
                users_stmt = users_stmt.where(AuditLog.created_at <= end_date)
            
            users_result = await session.execute(users_stmt)
            unique_users = users_result.scalar() or 0
            
            return {
                'total_events': total_events,
                'unique_users': unique_users,
                'events_by_outcome': events_by_outcome,
                'top_event_types': events_by_type,
                'success_rate': (
                    events_by_outcome.get('success', 0) / total_events * 100
                    if total_events > 0 else 0
                )
            }
    
    async def get_user_activity_summary(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get activity summary for a specific user."""
        async with self.db_manager.get_session() as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Base query for user
            base_stmt = (
                select(func.count(AuditLog.id))
                .where(AuditLog.user_id == user_id)
                .where(AuditLog.created_at >= cutoff_time)
            )
            
            if tenant_id:
                base_stmt = base_stmt.where(AuditLog.tenant_id == tenant_id)
            
            # Total events
            total_result = await session.execute(base_stmt)
            total_events = total_result.scalar() or 0
            
            # Events by action
            action_stmt = (
                select(AuditLog.action, func.count(AuditLog.id))
                .where(AuditLog.user_id == user_id)
                .where(AuditLog.created_at >= cutoff_time)
                .group_by(AuditLog.action)
            )
            
            if tenant_id:
                action_stmt = action_stmt.where(AuditLog.tenant_id == tenant_id)
            
            action_result = await session.execute(action_stmt)
            events_by_action = {row[0]: row[1] for row in action_result.all()}
            
            # Last activity
            last_stmt = (
                select(AuditLog.created_at)
                .where(AuditLog.user_id == user_id)
                .order_by(desc(AuditLog.created_at))
                .limit(1)
            )
            
            if tenant_id:
                last_stmt = last_stmt.where(AuditLog.tenant_id == tenant_id)
            
            last_result = await session.execute(last_stmt)
            last_activity = last_result.scalar()
            
            return {
                'user_id': user_id,
                'total_events': total_events,
                'events_by_action': events_by_action,
                'last_activity': last_activity.isoformat() if last_activity else None,
                'period_hours': hours
            }
    
    async def log_event(
        self,
        event_type: str,
        action: str,
        outcome: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """Create a new audit log entry."""
        audit_data = {
            'event_type': event_type,
            'action': action,
            'outcome': outcome,
            'user_id': user_id,
            'tenant_id': tenant_id,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'event_data': event_data,
            'correlation_id': correlation_id,
            'session_id': session_id,
            'ip_address': ip_address,
            'user_agent': user_agent
        }
        
        return await self.create(**audit_data)
    
    async def get_compliance_report(
        self,
        tenant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Generate compliance report from audit logs."""
        stats = await self.get_event_statistics(tenant_id, start_date, end_date)
        
        # Get security events
        security_events = await self.get_security_events(tenant_id, page_size=1000)
        
        # Get failed events
        failed_events = await self.get_failed_events(tenant_id, page_size=1000)
        
        return {
            'report_generated_at': datetime.utcnow().isoformat(),
            'period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None
            },
            'tenant_id': tenant_id,
            'statistics': stats,
            'security_events_count': len(security_events),
            'failed_events_count': len(failed_events),
            'compliance_indicators': {
                'audit_coverage': stats['total_events'] > 0,
                'security_monitoring': len(security_events) >= 0,
                'error_tracking': len(failed_events) >= 0
            }
        }