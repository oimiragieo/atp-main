"""Startup utilities for initializing the enterprise data access layer."""

import asyncio
import logging
import os
from typing import Optional

from .database import get_database_manager, init_database
from .registry_migration import create_sample_models, migrate_registry_to_database
from .repository_manager import initialize_repository_manager
from .registry_adapter import initialize_registry_adapter

logger = logging.getLogger(__name__)


async def initialize_enterprise_data_layer(
    create_tables: bool = True,
    migrate_registry: bool = True,
    registry_file_path: Optional[str] = None,
    create_samples: bool = False
) -> bool:
    """Initialize the enterprise data access layer."""
    try:
        logger.info("Initializing enterprise data access layer...")
        
        # 1. Initialize database
        if create_tables:
            logger.info("Initializing database tables...")
            await init_database()
            logger.info("Database tables initialized")
        
        # 2. Initialize repository manager
        logger.info("Initializing repository manager...")
        repo_manager = await initialize_repository_manager()
        logger.info("Repository manager initialized")
        
        # 3. Migrate existing registry if requested
        if migrate_registry:
            if not registry_file_path:
                # Try to find the default registry file
                registry_file_path = os.path.join(
                    os.path.dirname(__file__), "model_registry.json"
                )
            
            if os.path.exists(registry_file_path):
                logger.info(f"Migrating registry from {registry_file_path}...")
                migration_success = await migrate_registry_to_database(registry_file_path)
                if migration_success:
                    logger.info("Registry migration completed successfully")
                else:
                    logger.warning("Registry migration failed or no data to migrate")
            else:
                logger.info(f"Registry file not found at {registry_file_path}, skipping migration")
        
        # 4. Create sample data if requested and no models exist
        if create_samples:
            logger.info("Creating sample models if needed...")
            await create_sample_models()
        
        # 5. Initialize registry adapter
        logger.info("Initializing registry adapter...")
        await initialize_registry_adapter()
        logger.info("Registry adapter initialized")
        
        # 6. Perform health check
        health = await repo_manager.health_check()
        if health["database_connection"]:
            logger.info("Enterprise data layer initialization completed successfully")
            logger.info(f"Repository health: {health['repositories']}")
            return True
        else:
            logger.error("Enterprise data layer initialization failed: database connection failed")
            return False
        
    except Exception as e:
        logger.error(f"Failed to initialize enterprise data layer: {e}")
        return False


async def startup_health_check() -> dict:
    """Perform startup health check on all components."""
    health_status = {
        "database": False,
        "repositories": False,
        "registry_adapter": False,
        "overall": False
    }
    
    try:
        # Check database
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            await session.execute("SELECT 1")
            health_status["database"] = True
        
        # Check repositories
        from .repository_manager import get_repository_manager
        repo_manager = get_repository_manager()
        repo_health = await repo_manager.health_check()
        health_status["repositories"] = repo_health["database_connection"]
        
        # Check registry adapter
        from .registry_adapter import get_registry_adapter
        adapter = get_registry_adapter()
        registry = await adapter.get_registry()
        health_status["registry_adapter"] = isinstance(registry, dict)
        
        # Overall health
        health_status["overall"] = all([
            health_status["database"],
            health_status["repositories"],
            health_status["registry_adapter"]
        ])
        
    except Exception as e:
        logger.error(f"Startup health check failed: {e}")
        health_status["error"] = str(e)
    
    return health_status


def setup_logging():
    """Setup logging for the enterprise data layer."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set specific log levels for database components
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)


async def main():
    """Main startup function for testing."""
    setup_logging()
    
    logger.info("Starting enterprise data layer initialization...")
    
    success = await initialize_enterprise_data_layer(
        create_tables=True,
        migrate_registry=True,
        create_samples=True
    )
    
    if success:
        logger.info("Initialization successful!")
        
        # Perform health check
        health = await startup_health_check()
        logger.info(f"Health check results: {health}")
        
        # Test basic functionality
        from .data_service import get_data_service
        data_service = get_data_service()
        
        registry_size = await data_service.get_registry_size()
        logger.info(f"Registry contains {registry_size} models")
        
        shadow_models = await data_service.get_shadow_models()
        logger.info(f"Shadow models: {shadow_models}")
        
    else:
        logger.error("Initialization failed!")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())