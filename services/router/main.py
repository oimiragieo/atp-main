#!/usr/bin/env python3
"""
Enterprise AI Platform - Router Service Main Entry Point

This is the main entry point for the ATP router service in production.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the router service to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from service import ATPService
from startup import initialize_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    """Main entry point for the router service."""
    try:
        logger.info("Starting ATP Router Service...")
        
        # Initialize the service
        service = await initialize_service()
        
        # Start the service
        await service.start()
        
        logger.info("ATP Router Service started successfully")
        
        # Keep the service running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            await service.stop()
            logger.info("ATP Router Service stopped")
            
    except Exception as e:
        logger.error(f"Failed to start ATP Router Service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())