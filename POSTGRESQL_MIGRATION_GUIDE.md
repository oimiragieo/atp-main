# PostgreSQL Migration Guide for ATP Platform

**Version:** 1.0
**Date:** 2025-11-17
**Status:** Ready for Implementation

---

## Overview

This guide provides step-by-step instructions for migrating ATP from SQLite to PostgreSQL for production deployment. PostgreSQL provides better performance, scalability, and concurrent access compared to SQLite.

## Current SQLite Usage

ATP currently uses SQLite in:
- **`router_service/adaptive_stats.py`** - Model selection statistics
  - Table: `model_stats` (cluster, model, calls, success, cost_sum, latency_sum)
  - Operations: Read/write statistics, UCB scoring, Thompson sampling

## Migration Strategy

### Phase 1: Parallel Operation (Recommended)
Run SQLite and PostgreSQL in parallel initially to verify correctness:
1. Write to both databases
2. Read from SQLite (existing behavior)
3. Compare results periodically
4. Switch reads to PostgreSQL after validation
5. Remove SQLite

### Phase 2: Direct Migration (Faster)
1. Export SQLite data
2. Import to PostgreSQL
3. Update code to use PostgreSQL
4. Deploy

---

## Prerequisites

### Install PostgreSQL

**Docker (Recommended for testing):**
```bash
docker run --name atp-postgres \
  -e POSTGRES_PASSWORD=atp_dev_password \
  -e POSTGRES_USER=atp \
  -e POSTGRES_DB=atp_stats \
  -p 5432:5432 \
  -d postgres:15-alpine
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

### Install Python Dependencies

```bash
pip install asyncpg psycopg2-binary sqlalchemy alembic
```

Add to `requirements.txt`:
```
asyncpg==0.29.0
psycopg2-binary==2.9.9
sqlalchemy[asyncio]==2.0.23
alembic==1.13.0
```

---

## Database Schema

### Create PostgreSQL Schema

```sql
-- Create database (if not using Docker)
CREATE DATABASE atp_stats;

-- Connect to database
\c atp_stats

-- Create schema
CREATE SCHEMA IF NOT EXISTS atp;

-- Create model_stats table
CREATE TABLE atp.model_stats (
    cluster VARCHAR(255) NOT NULL,
    model VARCHAR(255) NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    cost_sum DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    latency_sum DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cluster, model)
);

-- Create index for performance
CREATE INDEX idx_model_stats_cluster ON atp.model_stats(cluster);
CREATE INDEX idx_model_stats_updated ON atp.model_stats(updated_at);

-- Create update trigger for updated_at
CREATE OR REPLACE FUNCTION atp.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_model_stats_updated_at
    BEFORE UPDATE ON atp.model_stats
    FOR EACH ROW
    EXECUTE FUNCTION atp.update_updated_at_column();

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON SCHEMA atp TO atp;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA atp TO atp;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA atp TO atp;
```

Save this as: `database/migrations/001_initial_schema.sql`

---

## Configuration

### Environment Variables

Add to `.env`:
```bash
# PostgreSQL Configuration
DATABASE_URL=postgresql+asyncpg://atp:atp_dev_password@localhost:5432/atp_stats
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_ECHO=0  # Set to 1 for SQL logging

# Migration settings
USE_POSTGRESQL=1  # Set to 1 to enable PostgreSQL
POSTGRES_SCHEMA=atp  # Schema name
```

### Configuration Class

Update `router_service/config.py`:
```python
@dataclass(frozen=True)
class Settings:
    # ... existing settings ...

    # Database settings
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://atp:atp_dev_password@localhost:5432/atp_stats"
    )
    use_postgresql: bool = os.getenv("USE_POSTGRESQL", "0") == "1"
    postgres_schema: str = os.getenv("POSTGRES_SCHEMA", "atp")
    db_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "20"))
    db_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    db_pool_timeout: int = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
    db_echo: bool = os.getenv("DATABASE_ECHO", "0") == "1"
```

---

## Code Implementation

### Create Database Module

Create `router_service/database/postgres_stats.py`:

```python
"""PostgreSQL implementation for adaptive routing statistics."""

import logging
from typing import Any

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy metadata
metadata = MetaData(schema=settings.postgres_schema)

# Define model_stats table
model_stats_table = Table(
    "model_stats",
    metadata,
    Column("cluster", String(255), primary_key=True),
    Column("model", String(255), primary_key=True),
    Column("calls", Integer, nullable=False, default=0),
    Column("success", Integer, nullable=False, default=0),
    Column("cost_sum", Float, nullable=False, default=0.0),
    Column("latency_sum", Float, nullable=False, default=0.0),
)


class PostgresStatsBackend:
    """Async PostgreSQL backend for statistics."""

    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_maker: sessionmaker | None = None

    async def initialize(self) -> None:
        """Initialize database connection pool."""
        if self.engine is not None:
            return

        logger.info("Initializing PostgreSQL connection pool")

        self.engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            echo=settings.db_echo,
        )

        self.session_maker = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create tables if they don't exist
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        logger.info("PostgreSQL connection pool initialized")

    async def close(self) -> None:
        """Close database connection pool."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None
            logger.info("PostgreSQL connection pool closed")

    async def update_stat(
        self,
        cluster: str,
        model: str,
        success: bool,
        cost: float,
        latency: float,
    ) -> None:
        """Update or insert model statistics."""
        if not self.session_maker:
            await self.initialize()

        async with self.session_maker() as session:
            # Try to fetch existing record
            stmt = select(model_stats_table).where(
                model_stats_table.c.cluster == cluster,
                model_stats_table.c.model == model,
            )
            result = await session.execute(stmt)
            row = result.first()

            if row:
                # Update existing
                stmt = (
                    update(model_stats_table)
                    .where(
                        model_stats_table.c.cluster == cluster,
                        model_stats_table.c.model == model,
                    )
                    .values(
                        calls=row.calls + 1,
                        success=row.success + (1 if success else 0),
                        cost_sum=row.cost_sum + cost,
                        latency_sum=row.latency_sum + latency,
                    )
                )
                await session.execute(stmt)
            else:
                # Insert new
                stmt = model_stats_table.insert().values(
                    cluster=cluster,
                    model=model,
                    calls=1,
                    success=1 if success else 0,
                    cost_sum=cost,
                    latency_sum=latency,
                )
                await session.execute(stmt)

            await session.commit()

    async def fetch_stats(self, cluster: str) -> list[tuple[str, int, int, float, float]]:
        """Fetch statistics for a cluster."""
        if not self.session_maker:
            await self.initialize()

        async with self.session_maker() as session:
            stmt = select(model_stats_table).where(model_stats_table.c.cluster == cluster)
            result = await session.execute(stmt)

            return [
                (row.model, row.calls, row.success, row.cost_sum, row.latency_sum)
                for row in result
            ]

    async def fetch_all_clusters(self) -> list[str]:
        """Fetch all unique clusters."""
        if not self.session_maker:
            await self.initialize()

        async with self.session_maker() as session:
            stmt = select(model_stats_table.c.cluster).distinct()
            result = await session.execute(stmt)

            return [row[0] for row in result]


# Global instance
_postgres_backend: PostgresStatsBackend | None = None


def get_postgres_backend() -> PostgresStatsBackend:
    """Get or create PostgreSQL backend."""
    global _postgres_backend
    if _postgres_backend is None:
        _postgres_backend = PostgresStatsBackend()
    return _postgres_backend
```

### Update adaptive_stats.py

Modify `router_service/adaptive_stats.py` to support both backends:

```python
# At the top of the file, add:
from .config import settings

# Add backend selection
if settings.use_postgresql:
    from .database.postgres_stats import get_postgres_backend
    import asyncio

    _pg_backend = get_postgres_backend()

    # Async wrappers
    def update_stat(...):
        asyncio.create_task(_pg_backend.update_stat(...))

    def fetch_stats(cluster: str):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_pg_backend.fetch_stats(cluster))

    def fetch_all_clusters():
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_pg_backend.fetch_all_clusters())
else:
    # Keep existing SQLite implementation
    # ... existing code ...
```

---

## Data Migration

### Export from SQLite

```python
# scripts/export_sqlite_stats.py
import sqlite3
import json

DB_PATH = "router_service/router_stats.sqlite"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT * FROM model_stats")
rows = cursor.fetchall()

data = []
for row in rows:
    data.append({
        "cluster": row[0],
        "model": row[1],
        "calls": row[2],
        "success": row[3],
        "cost_sum": row[4],
        "latency_sum": row[5],
    })

with open("model_stats_export.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Exported {len(data)} records to model_stats_export.json")
conn.close()
```

### Import to PostgreSQL

```python
# scripts/import_to_postgres.py
import asyncio
import json

from router_service.database.postgres_stats import get_postgres_backend

async def import_data():
    backend = get_postgres_backend()
    await backend.initialize()

    with open("model_stats_export.json") as f:
        data = json.load(f)

    for record in data:
        await backend.update_stat(
            cluster=record["cluster"],
            model=record["model"],
            success=True,  # Placeholder
            cost=record["cost_sum"] / max(record["calls"], 1),
            latency=record["latency_sum"] / max(record["calls"], 1),
        )
        # Adjust calls to match export
        # This is a simplified version - production should do bulk insert

    print(f"Imported {len(data)} records")
    await backend.close()

if __name__ == "__main__":
    asyncio.run(import_data())
```

---

## Testing

### Verify Migration

```bash
# 1. Export SQLite data
python3 scripts/export_sqlite_stats.py

# 2. Start PostgreSQL
docker compose up postgres -d

# 3. Apply schema
psql -h localhost -U atp -d atp_stats -f database/migrations/001_initial_schema.sql

# 4. Import data
python3 scripts/import_to_postgres.py

# 5. Verify count
psql -h localhost -U atp -d atp_stats -c "SELECT COUNT(*) FROM atp.model_stats;"

# 6. Enable PostgreSQL in .env
echo "USE_POSTGRESQL=1" >> .env

# 7. Restart ATP
docker compose restart router

# 8. Verify stats still work
curl http://localhost:7443/metrics | grep model_stats
```

### Performance Testing

```bash
# Test concurrent writes
python3 scripts/test_db_concurrency.py --backend postgres --workers 50 --requests 1000

# Compare with SQLite
python3 scripts/test_db_concurrency.py --backend sqlite --workers 50 --requests 1000
```

---

## Monitoring

### Health Checks

Add to router service:
```python
@app.get("/health/database")
async def database_health():
    """Check database connectivity."""
    try:
        backend = get_postgres_backend()
        clusters = await backend.fetch_all_clusters()
        return {
            "status": "healthy",
            "backend": "postgresql",
            "clusters": len(clusters),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
```

### Metrics

Monitor:
- Connection pool usage
- Query latency
- Error rates
- Transaction throughput

---

## Rollback Plan

If issues occur:

1. **Immediate**: Set `USE_POSTGRESQL=0` in environment
2. **Restart**: `docker compose restart router`
3. **Verify**: Check SQLite still has data
4. **Investigate**: Review PostgreSQL logs
5. **Fix**: Address issues in test environment
6. **Retry**: Re-enable after fixes validated

---

## Production Checklist

- [ ] PostgreSQL deployed with replication
- [ ] Connection pooling configured (pgBouncer recommended)
- [ ] Backups automated (pg_dump or WAL archiving)
- [ ] Monitoring configured (queries, connections, errors)
- [ ] Data migrated and verified
- [ ] Performance tested under load
- [ ] Rollback plan tested
- [ ] Team trained on PostgreSQL operations
- [ ] Documentation updated

---

## Performance Tuning

### PostgreSQL Configuration

Optimize `postgresql.conf` for ATP workload:

```ini
# Memory
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

# Connections
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# Query Planning
random_page_cost = 1.1  # For SSD
effective_io_concurrency = 200

# WAL
wal_buffers = 16MB
checkpoint_completion_target = 0.9
```

### Connection Pooling

Use pgBouncer in production:

```ini
[databases]
atp_stats = host=localhost port=5432 dbname=atp_stats

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
```

---

## Troubleshooting

### Common Issues

**Connection Refused:**
```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Verify network
telnet localhost 5432
```

**Slow Queries:**
```sql
-- Enable query logging
SET log_statement = 'all';
SET log_min_duration_statement = 100;  -- Log queries >100ms

-- Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Lock Contention:**
```sql
-- Check locks
SELECT * FROM pg_locks WHERE NOT granted;

-- Check blocking queries
SELECT * FROM pg_stat_activity WHERE state = 'active';
```

---

## Next Steps

1. Review and approve migration plan
2. Test in staging environment
3. Schedule production migration window
4. Execute migration with monitoring
5. Validate performance improvements
6. Remove SQLite code after stabilization (2-4 weeks)

---

## References

- PostgreSQL Documentation: https://www.postgresql.org/docs/
- SQLAlchemy Async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- asyncpg: https://magicstack.github.io/asyncpg/
- Database Migrations: https://alembic.sqlalchemy.org/

---

**Prepared by:** ATP Security Audit Team
**Status:** Ready for Implementation
**Estimated Effort:** 2-4 days (including testing)
