# Enterprise Data Access Layer

This document describes the enterprise data access layer that replaces the in-memory dictionary-based data storage with a production-ready database-backed system.

## Overview

The enterprise data access layer provides:

- **Repository Pattern**: Clean separation between data access and business logic
- **Database Persistence**: PostgreSQL-backed storage with async SQLAlchemy
- **Transaction Management**: ACID transactions across multiple repositories
- **Caching**: L1 in-memory caching with TTL support
- **Audit Trails**: Comprehensive logging of all data operations
- **Soft Deletes**: Data retention with logical deletion
- **Backward Compatibility**: Drop-in replacement for existing registry access

## Architecture

```
Router Service
     ↓
Data Service Layer (router_service/data_service.py)
     ↓
Repository Manager (router_service/repository_manager.py)
     ↓
Individual Repositories (router_service/repositories/)
     ↓
Database Models (router_service/models/database.py)
     ↓
PostgreSQL Database
```

## Key Components

### 1. Repository Manager (`repository_manager.py`)

Central coordinator for all data access operations:

```python
from router_service.repository_manager import get_repository_manager

repo_manager = get_repository_manager()

# Access individual repositories
models = await repo_manager.models.get_enabled_models()
providers = await repo_manager.providers.get_healthy_providers()

# Use transactions
async with repo_manager.transaction() as tx_manager:
    # All operations are atomic
    await tx_manager.models.create(...)
    await tx_manager.providers.update(...)
    # Automatically committed or rolled back
```

### 2. Data Service (`data_service.py`)

High-level service layer for common operations:

```python
from router_service.data_service import get_data_service

data_service = get_data_service()

# Get model registry (compatible with existing format)
registry = await data_service.get_model_registry()

# Log requests
await data_service.log_request(
    correlation_id="req-123",
    model_used="gpt-4",
    response_time_ms=250.0
)

# Model lifecycle operations
await data_service.promote_shadow_model("new-model")
```

### 3. Registry Adapter (`registry_adapter.py`)

Backward compatibility layer for existing code:

```python
from router_service.registry_adapter import get_registry_adapter

adapter = get_registry_adapter()

# Drop-in replacement for old _MODEL_REGISTRY
registry = await adapter.get_registry()
model_data = adapter.get("gpt-4")
shadow_models = await adapter.get_shadow_models()

# Synchronous access (for compatibility)
if "gpt-4" in adapter:
    model = adapter["gpt-4"]
```

### 4. Individual Repositories

Specialized data access for each entity type:

```python
# Model Repository
models = await repo_manager.models.get_by_provider(provider_id)
cheapest = await repo_manager.models.get_cheapest_models(limit=5)
await repo_manager.models.update_performance_metrics(model_id, quality_score=0.95)

# Request Repository  
recent = await repo_manager.requests.get_recent_requests(hours=24)
failed = await repo_manager.requests.get_failed_requests()
cost_summary = await repo_manager.requests.get_cost_summary(tenant_id="tenant-1")

# Provider Repository
healthy = await repo_manager.providers.get_healthy_providers()
await repo_manager.providers.update_health_status(provider_id, "healthy")

# Policy Repository
policies = await repo_manager.policies.get_enabled_policies(tenant_id="tenant-1")
await repo_manager.policies.enable_policy("policy-123")

# Compliance Repository
violations = await repo_manager.compliance.get_critical_violations()
await repo_manager.compliance.remediate_violation("violation-456", "Fixed issue")

# Audit Repository
events = await repo_manager.audit.get_security_events()
await repo_manager.audit.log_event("user_login", "login", "success")
```

## Migration Guide

### 1. Initialize the Data Layer

```python
from router_service.startup import initialize_enterprise_data_layer

# One-time initialization
await initialize_enterprise_data_layer(
    create_tables=True,      # Create database tables
    migrate_registry=True,   # Migrate from model_registry.json
    create_samples=False     # Don't create sample data
)
```

### 2. Replace Registry Access

**Before (in-memory dictionary):**
```python
# Old approach
model_data = _MODEL_REGISTRY.get("gpt-4")
shadow_models = [m for m, rec in _MODEL_REGISTRY.items() if rec.get("status") == "shadow"]
```

**After (database-backed):**
```python
# New approach - Option 1: Registry Adapter (minimal changes)
adapter = get_registry_adapter()
model_data = adapter.get("gpt-4")
shadow_models = await adapter.get_shadow_models()

# New approach - Option 2: Data Service (recommended)
data_service = get_data_service()
registry = await data_service.get_model_registry()
model_data = registry.get("gpt-4")
shadow_models = await data_service.get_shadow_models()
```

### 3. Add Request Logging

```python
# Replace manual logging with structured database logging
await data_service.log_request(
    correlation_id=correlation_id,
    user_id=user_id,
    tenant_id=tenant_id,
    model_used=selected_model,
    provider_used=provider_name,
    response_time_ms=response_time,
    tokens_input=input_tokens,
    tokens_output=output_tokens,
    cost_usd=calculated_cost,
    quality_score=quality_score
)
```

### 4. Update Model Lifecycle Operations

```python
# Replace direct dictionary updates
# Old: _MODEL_REGISTRY[model_name]["status"] = "active"
# New:
await data_service.promote_shadow_model(model_name)
await data_service.demote_to_shadow(model_name)
```

## Configuration

### Database Configuration

Set environment variables:

```bash
# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/atp_db

# Connection pooling
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30

# Caching
CACHE_TTL_SECONDS=300
CACHE_ENABLED=true
```

### Migration Configuration

```bash
# Registry migration
REGISTRY_FILE_PATH=./model_registry.json
MIGRATE_ON_STARTUP=true
CREATE_SAMPLE_DATA=false
```

## Performance Considerations

### Caching Strategy

- **L1 Cache**: In-memory caching with TTL (default 5 minutes)
- **Cache Invalidation**: Automatic on updates/deletes
- **Cache Statistics**: Available via `get_cache_statistics()`

### Query Optimization

- **Pagination**: All list operations support pagination
- **Filtering**: Efficient database-level filtering
- **Indexing**: Proper indexes on frequently queried columns
- **Soft Deletes**: Filtered at query level for performance

### Connection Management

- **Connection Pooling**: Configurable pool size and overflow
- **Health Monitoring**: Automatic connection health checks
- **Async Operations**: Non-blocking database operations

## Testing

Run the integration example:

```bash
python -m router_service.integration_example
```

Run the test suite:

```bash
python -m pytest tests/test_enterprise_data_layer.py -v
```

## Monitoring

### Health Checks

```python
# Check overall system health
health = await data_service.health_check()
print(f"Status: {health['status']}")
print(f"Database: {health['database_connection']}")
print(f"Registry size: {health['registry_size']}")
```

### Cache Statistics

```python
# Monitor cache performance
cache_stats = await repo_manager.get_cache_statistics()
for repo_name, stats in cache_stats.items():
    print(f"{repo_name}: {stats['active_entries']} active, {stats['expired_entries']} expired")
```

### Audit Trail

All operations are automatically logged to the audit repository:

```python
# Query audit events
events = await repo_manager.audit.get_recent_events(hours=24)
security_events = await repo_manager.audit.get_security_events()
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check `DATABASE_URL` environment variable
   - Verify database server is running
   - Check connection pool configuration

2. **Migration Failures**
   - Verify `model_registry.json` format
   - Check database permissions
   - Review migration logs

3. **Performance Issues**
   - Monitor cache hit rates
   - Check query patterns
   - Adjust connection pool size

### Debug Mode

Enable detailed logging:

```python
import logging
logging.getLogger('router_service').setLevel(logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## Future Enhancements

- **L2 Cache**: Redis-based distributed caching
- **Read Replicas**: Database read scaling
- **Metrics Integration**: Prometheus metrics for all operations
- **Data Archival**: Automated old data archival
- **Multi-tenant Isolation**: Enhanced tenant data separation