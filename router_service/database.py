"""Database configuration and connection management.

Provides async SQLAlchemy setup with connection pooling, health monitoring,
and proper configuration for production use.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class DatabaseConfig:
    """Database configuration management."""

    def __init__(self):
        # Database URL configuration
        self.database_url = self._get_database_url()

        # Connection pool configuration
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour

        # Connection configuration
        self.connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
        self.command_timeout = int(os.getenv("DB_COMMAND_TIMEOUT", "60"))

        # Feature flags
        self.enable_query_logging = os.getenv("DB_QUERY_LOGGING", "false").lower() == "true"
        self.enable_connection_events = os.getenv("DB_CONNECTION_EVENTS", "true").lower() == "true"

    def _get_database_url(self) -> str:
        """Get database URL from environment variables."""
        # Check for full database URL first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Ensure async driver
            if database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            return database_url

        # Build URL from components
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "atp_router")
        username = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")

        if not password:
            logger.warning("No database password configured - using empty password")

        return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"


class DatabaseManager:
    """Database connection and session management."""

    def __init__(self, config: DatabaseConfig | None = None):
        self.config = config or DatabaseConfig()
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database engine and session factory."""
        if self._initialized:
            return

        # Create engine with connection pooling
        engine_kwargs = {
            "url": self.config.database_url,
            "echo": self.config.enable_query_logging,
            "future": True,
        }

        # Configure connection pool
        if "sqlite" not in self.config.database_url:
            engine_kwargs.update(
                {
                    "poolclass": QueuePool,
                    "pool_size": self.config.pool_size,
                    "max_overflow": self.config.max_overflow,
                    "pool_timeout": self.config.pool_timeout,
                    "pool_recycle": self.config.pool_recycle,
                    "pool_pre_ping": True,  # Validate connections before use
                }
            )
        else:
            # SQLite doesn't support connection pooling
            engine_kwargs["poolclass"] = NullPool

        # Connection arguments
        connect_args = {}
        if "postgresql" in self.config.database_url:
            connect_args.update(
                {
                    "command_timeout": self.config.command_timeout,
                    "server_settings": {
                        "jit": "off",  # Disable JIT for better connection performance
                        "application_name": "atp_router",
                    },
                }
            )

        if connect_args:
            engine_kwargs["connect_args"] = connect_args

        self.engine = create_async_engine(**engine_kwargs)

        # Set up connection event listeners
        if self.config.enable_connection_events:
            self._setup_connection_events()

        # Create session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )

        self._initialized = True
        logger.info("Database manager initialized successfully")

    def _setup_connection_events(self) -> None:
        """Set up SQLAlchemy connection event listeners."""
        if not self.engine:
            return

        @event.listens_for(self.engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            logger.debug("Database connection established")

        @event.listens_for(self.engine.sync_engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            logger.debug("Database connection checked out from pool")

        @event.listens_for(self.engine.sync_engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            logger.debug("Database connection returned to pool")

        @event.listens_for(self.engine.sync_engine, "invalidate")
        def on_invalidate(dbapi_connection, connection_record, exception):
            logger.warning(f"Database connection invalidated: {exception}")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup."""
        if not self._initialized:
            await self.initialize()

        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check database connectivity and health."""
        try:
            if not self._initialized:
                await self.initialize()

            if not self.engine:
                return False

            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close database connections and clean up resources."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

        self._initialized = False
        self.engine = None
        self.session_factory = None


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        yield session


async def init_database() -> None:
    """Initialize database on application startup."""
    db_manager = get_database_manager()
    await db_manager.initialize()

    # Check database health
    is_healthy = await db_manager.health_check()
    if not is_healthy:
        logger.error("Database health check failed during initialization")
        raise RuntimeError("Database initialization failed")

    logger.info("Database initialized and health check passed")


async def close_database() -> None:
    """Close database connections on application shutdown."""
    db_manager = get_database_manager()
    await db_manager.close()
