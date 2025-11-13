"""Database Management API Endpoints.

REST API endpoints for database administration, backup management,
and system health monitoring.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .database import get_database_manager
from .database_backup import get_backup_manager, get_backup_scheduler
from .enterprise_auth import UserInfo, require_admin

logger = logging.getLogger(__name__)

# Create router
database_router = APIRouter(prefix="/api/v1/database", tags=["database"])


# Pydantic models for API
class DatabaseHealthResponse(BaseModel):
    """Response model for database health check."""

    healthy: bool
    connection_pool_size: int
    active_connections: int
    database_version: str
    last_check: datetime


class BackupInfoModel(BaseModel):
    """API model for backup information."""

    name: str
    file: str
    size: int
    created_at: datetime
    compressed: bool
    type: str


class BackupRequest(BaseModel):
    """Request model for creating backups."""

    name: str = ""
    backup_type: str = "full"  # full, incremental
    base_backup: str = ""  # Required for incremental backups


class RestoreRequest(BaseModel):
    """Request model for database restore."""

    backup_file: str
    target_database: str = ""


@database_router.get("/health", response_model=DatabaseHealthResponse)
async def get_database_health(user: UserInfo = Depends(require_admin())) -> DatabaseHealthResponse:
    """Get database health status and connection information."""
    db_manager = get_database_manager()

    try:
        # Check database health
        is_healthy = await db_manager.health_check()

        # Get connection pool information
        pool_info = {"connection_pool_size": 0, "active_connections": 0, "database_version": "Unknown"}

        if db_manager.engine:
            pool = db_manager.engine.pool
            pool_info["connection_pool_size"] = pool.size()
            pool_info["active_connections"] = pool.checkedout()

            # Get database version
            try:
                async with db_manager.get_session() as session:
                    from sqlalchemy import text

                    result = await session.execute(text("SELECT version()"))
                    version = result.scalar()
                    if version:
                        pool_info["database_version"] = version.split()[0:2]  # PostgreSQL version
            except Exception as e:
                logger.warning(f"Failed to get database version: {e}")

        return DatabaseHealthResponse(
            healthy=is_healthy,
            connection_pool_size=pool_info["connection_pool_size"],
            active_connections=pool_info["active_connections"],
            database_version=pool_info["database_version"],
            last_check=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") from e


@database_router.get("/backups", response_model=list[BackupInfoModel])
async def list_backups(user: UserInfo = Depends(require_admin())) -> list[BackupInfoModel]:
    """List available database backups."""
    backup_manager = get_backup_manager()

    try:
        backups = await backup_manager.list_backups()

        return [
            BackupInfoModel(
                name=backup["name"],
                file=backup["file"],
                size=backup["size"],
                created_at=backup["created_at"],
                compressed=backup["compressed"],
                type=backup["type"],
            )
            for backup in backups
        ]

    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}") from e


@database_router.post("/backups")
async def create_backup(request: BackupRequest, user: UserInfo = Depends(require_admin())) -> dict[str, Any]:
    """Create a new database backup."""
    backup_manager = get_backup_manager()

    try:
        if request.backup_type == "full":
            backup_file = await backup_manager.create_full_backup(request.name if request.name else None)
        elif request.backup_type == "incremental":
            if not request.base_backup:
                raise HTTPException(status_code=400, detail="Base backup required for incremental backup")
            backup_file = await backup_manager.create_incremental_backup(
                request.base_backup, request.name if request.name else None
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid backup type: {request.backup_type}")

        logger.info(f"Backup created by user {user.user_id}: {backup_file}")

        return {
            "message": "Backup created successfully",
            "backup_file": backup_file,
            "backup_type": request.backup_type,
            "created_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup creation failed: {str(e)}") from e


@database_router.post("/restore")
async def restore_database(request: RestoreRequest, user: UserInfo = Depends(require_admin())) -> dict[str, str]:
    """Restore database from backup."""
    backup_manager = get_backup_manager()

    try:
        # Verify backup exists and is valid
        is_valid = await backup_manager.verify_backup(request.backup_file)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid or corrupted backup file: {request.backup_file}")

        # Perform restore
        success = await backup_manager.restore_backup(
            request.backup_file, request.target_database if request.target_database else None
        )

        if not success:
            raise HTTPException(status_code=500, detail="Database restore failed")

        logger.info(f"Database restored by user {user.user_id} from {request.backup_file}")

        return {
            "message": "Database restore completed successfully",
            "backup_file": request.backup_file,
            "restored_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database restore failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(e)}") from e


@database_router.post("/backups/{backup_name}/verify")
async def verify_backup(backup_name: str, user: UserInfo = Depends(require_admin())) -> dict[str, Any]:
    """Verify backup integrity."""
    backup_manager = get_backup_manager()

    try:
        # Find backup file
        backups = await backup_manager.list_backups()
        backup_file = None

        for backup in backups:
            if backup["name"] == backup_name:
                backup_file = backup["file"]
                break

        if not backup_file:
            raise HTTPException(status_code=404, detail=f"Backup not found: {backup_name}")

        # Verify backup
        is_valid = await backup_manager.verify_backup(backup_file)

        return {
            "backup_name": backup_name,
            "backup_file": backup_file,
            "valid": is_valid,
            "verified_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup verification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup verification failed: {str(e)}") from e


@database_router.get("/scheduler/status")
async def get_scheduler_status(user: UserInfo = Depends(require_admin())) -> dict[str, Any]:
    """Get backup scheduler status."""
    scheduler = get_backup_scheduler()

    return {
        "running": scheduler.running,
        "full_backup_interval_hours": scheduler.full_backup_interval,
        "incremental_backup_interval_hours": scheduler.incremental_backup_interval,
    }


@database_router.post("/scheduler/start")
async def start_scheduler(user: UserInfo = Depends(require_admin())) -> dict[str, str]:
    """Start the backup scheduler."""
    scheduler = get_backup_scheduler()

    try:
        await scheduler.start()
        logger.info(f"Backup scheduler started by user {user.user_id}")

        return {"message": "Backup scheduler started successfully", "started_at": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Failed to start backup scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}") from e


@database_router.post("/scheduler/stop")
async def stop_scheduler(user: UserInfo = Depends(require_admin())) -> dict[str, str]:
    """Stop the backup scheduler."""
    scheduler = get_backup_scheduler()

    try:
        await scheduler.stop()
        logger.info(f"Backup scheduler stopped by user {user.user_id}")

        return {"message": "Backup scheduler stopped successfully", "stopped_at": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Failed to stop backup scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler: {str(e)}") from e


@database_router.get("/migrations/status")
async def get_migration_status(user: UserInfo = Depends(require_admin())) -> dict[str, Any]:
    """Get database migration status."""
    try:
        # This would typically check the alembic_version table
        # For now, return basic information
        return {
            "current_revision": "001",  # Would be read from alembic_version table
            "pending_migrations": [],
            "last_migration": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get migration status: {str(e)}") from e


@database_router.get("/stats")
async def get_database_stats(user: UserInfo = Depends(require_admin())) -> dict[str, Any]:
    """Get database statistics and metrics."""
    db_manager = get_database_manager()

    try:
        stats = {
            "connection_pool": {"size": 0, "checked_out": 0, "overflow": 0, "checked_in": 0},
            "tables": {},
            "database_size": "Unknown",
        }

        if db_manager.engine:
            pool = db_manager.engine.pool
            stats["connection_pool"] = {
                "size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "checked_in": pool.checkedin(),
            }

            # Get table statistics
            try:
                async with db_manager.get_session() as session:
                    from sqlalchemy import text

                    # Get table row counts
                    # Define allowed tables (whitelist to prevent SQL injection)
                    allowed_tables = {
                        "requests",
                        "responses",
                        "providers",
                        "models",
                        "policies",
                        "audit_logs",
                        "compliance_violations",
                        "model_stats",
                    }

                    for table in allowed_tables:
                        try:
                            # Validate table name is in whitelist (already validated above, but explicit check)
                            if table not in allowed_tables:
                                raise ValueError(f"Invalid table name: {table}")
                            # Safe to use f-string here since table is from validated whitelist
                            result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                            count = result.scalar()
                            stats["tables"][table] = {"row_count": count}
                        except Exception:
                            stats["tables"][table] = {"row_count": 0}

                    # Get database size
                    result = await session.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))"))
                    size = result.scalar()
                    if size:
                        stats["database_size"] = size

            except Exception as e:
                logger.warning(f"Failed to get detailed database stats: {e}")

        return stats

    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}") from e
