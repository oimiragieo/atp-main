"""Database models for the ATP Router service.

Defines SQLAlchemy models for all persistent entities including requests,
providers, policies, audit logs, and system configuration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
        nullable=False
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""
    
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TenantMixin:
    """Mixin for tenant isolation."""
    
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)


# Request and Response Models
class Request(Base, TimestampMixin, SoftDeleteMixin, TenantMixin):
    """Model for API requests."""
    
    __tablename__ = "requests"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Request identification
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Request details
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    query_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    headers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Request content
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    model_requested: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Response details
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Cost and billing
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provider_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Quality and performance
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Error handling
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    request_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    responses: Mapped[List["Response"]] = relationship("Response", back_populates="request")
    
    __table_args__ = (
        Index("idx_requests_created_at", "created_at"),
        Index("idx_requests_tenant_user", "tenant_id", "user_id"),
        Index("idx_requests_status_time", "status_code", "created_at"),
    )


class Response(Base, TimestampMixin, TenantMixin):
    """Model for API responses."""
    
    __tablename__ = "responses"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requests.id"),
        nullable=False,
        index=True
    )
    
    # Response content
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/plain")
    
    # Streaming details
    chunk_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Provider details
    provider_response_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    provider_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    request: Mapped["Request"] = relationship("Request", back_populates="responses")


# Provider and Model Management
class Provider(Base, TimestampMixin, SoftDeleteMixin):
    """Model for AI providers."""
    
    __tablename__ = "providers"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Provider identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)  # openai, anthropic, etc.
    
    # Configuration
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    api_key_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Capabilities
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_function_calling: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Status and health
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Configuration and metadata
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    provider_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    models: Mapped[List["Model"]] = relationship("Model", back_populates="provider")
    
    __table_args__ = (
        Index("idx_providers_type_enabled", "provider_type", "is_enabled"),
    )


class Model(Base, TimestampMixin, SoftDeleteMixin):
    """Model for AI models."""
    
    __tablename__ = "models"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id"),
        nullable=False,
        index=True
    )
    
    # Model identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_family: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Capabilities
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    supports_system_prompt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Performance characteristics
    latency_p50_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Pricing
    cost_per_input_token: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_per_output_token: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_per_request: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Status and lifecycle
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active, shadow, deprecated
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Configuration and metadata
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    model_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    provider: Mapped["Provider"] = relationship("Provider", back_populates="models")
    
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_provider_model"),
        Index("idx_models_status_enabled", "status", "is_enabled"),
    )


# Policy and Security Models
class Policy(Base, TimestampMixin, SoftDeleteMixin, TenantMixin):
    """Model for ABAC policies."""
    
    __tablename__ = "policies"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Policy identification
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Policy configuration
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Policy content
    rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    # Metadata
    policy_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    __table_args__ = (
        Index("idx_policies_tenant_enabled", "tenant_id", "is_enabled"),
        Index("idx_policies_priority", "priority"),
    )


# Audit and Compliance Models
class AuditLog(Base, TimestampMixin, TenantMixin):
    """Model for audit log entries."""
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Event identification
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Actor information
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 compatible
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Resource information
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    # Event details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failure, error
    
    # Event data
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Integrity
    hash_chain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    __table_args__ = (
        Index("idx_audit_logs_event_time", "event_type", "created_at"),
        Index("idx_audit_logs_user_time", "user_id", "created_at"),
        Index("idx_audit_logs_tenant_time", "tenant_id", "created_at"),
    )


class ComplianceViolation(Base, TimestampMixin, TenantMixin):
    """Model for compliance violations."""
    
    __tablename__ = "compliance_violations"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Violation identification
    violation_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Compliance framework
    framework: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    
    # Violation details
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Resource information
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    remediated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Remediation
    remediation_steps: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    remediation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    violation_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    __table_args__ = (
        Index("idx_violations_framework_status", "framework", "status"),
        Index("idx_violations_severity_detected", "severity", "detected_at"),
    )


# System Configuration Models
class SystemConfig(Base, TimestampMixin):
    """Model for system configuration."""
    
    __tablename__ = "system_config"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Configuration identification
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Configuration value
    value: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    __table_args__ = (
        Index("idx_system_config_category", "category"),
    )


class ModelStats(Base, TimestampMixin):
    """Model for model performance statistics."""
    
    __tablename__ = "model_stats"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id"),
        nullable=False,
        index=True
    )
    
    # Time window
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_size_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Request statistics
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Performance statistics
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p50_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p99_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Token statistics
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_tokens_per_request: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Cost statistics
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_cost_per_request: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Quality statistics
    avg_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    __table_args__ = (
        UniqueConstraint("model_id", "window_start", "window_size_minutes", name="uq_model_stats_window"),
        Index("idx_model_stats_window", "window_start", "window_end"),
    )