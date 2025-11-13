#!/usr/bin/env python3
"""
Enterprise AI Platform - Authentication Service

Handles authentication and authorization for the ATP platform.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the router service to the Python path for shared components
sys.path.insert(0, str(Path(__file__).parent.parent / "router"))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

# Import authentication components from router service
try:
    from enterprise_auth import EnterpriseAuthenticator
    from tenant_isolation import TenantIsolationMiddleware
except ImportError:
    # Fallback if components don't exist
    logging.warning("Authentication components not found, using mock implementations")
    
    class EnterpriseAuthenticator:
        async def authenticate(self, token: str):
            return {"user_id": "mock_user", "tenant_id": "mock_tenant"}
    
    class TenantIsolationMiddleware:
        def __init__(self, app):
            self.app = app

app = FastAPI(title="ATP Authentication Service", version="1.0.0")
security = HTTPBearer()
authenticator = EnterpriseAuthenticator()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "auth"}

@app.post("/auth/validate")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate an authentication token."""
    try:
        token = credentials.credentials
        user_info = await authenticator.authenticate(token)
        return {"valid": True, "user": user_info}
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/auth/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Refresh an authentication token."""
    try:
        token = credentials.credentials
        # Implementation would refresh the token
        return {"token": "new_token", "expires_in": 3600}
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Token refresh failed")

async def main():
    """Main entry point for the authentication service."""
    logger.info("Starting ATP Authentication Service...")
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8081,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())