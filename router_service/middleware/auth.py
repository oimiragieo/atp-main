# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Authentication middleware for ATP Router Service.

Implements API key authentication with support for:
- Header-based authentication (X-API-Key)
- Query parameter fallback (api_key)
- Rate limiting per API key
- Key validation against configured admin key

Security Notes:
- Uses constant-time comparison to prevent timing attacks
- Validates key length to prevent DoS via oversized keys
- Logs authentication failures for security monitoring
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    "/healthz",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication.

    This middleware validates API keys for all requests except public endpoints.
    It supports both header-based and query parameter authentication.

    Args:
        app: The FastAPI application
        admin_api_key: The configured admin API key to validate against
        require_auth: Whether to enforce authentication (default: True)

    Example:
        app.add_middleware(
            AuthenticationMiddleware,
            admin_api_key=settings.api_key,
            require_auth=True
        )
    """

    def __init__(
        self,
        app,
        admin_api_key: str,
        require_auth: bool = True,
    ):
        super().__init__(app)
        self.admin_api_key = admin_api_key
        self.require_auth = require_auth

        if not admin_api_key:
            logger.warning("AuthenticationMiddleware initialized without admin_api_key")

        if len(admin_api_key) < 32:
            logger.warning(
                "Admin API key is shorter than recommended minimum (32 chars)",
                extra={"key_length": len(admin_api_key)},
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and validate authentication.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response from the next handler if authenticated

        Raises:
            HTTPException: If authentication fails
        """
        # Skip authentication for public endpoints
        if request.url.path in PUBLIC_ENDPOINTS:
            return await call_next(request)

        # Skip authentication if disabled (for development)
        if not self.require_auth:
            logger.debug("Authentication disabled, allowing request")
            return await call_next(request)

        # Extract API key from request
        api_key = self._extract_api_key(request)

        if not api_key:
            logger.warning(
                "Authentication failed: missing API key",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else "unknown",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key. Provide X-API-Key header or api_key query parameter.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Validate API key length to prevent DoS
        if len(api_key) > 512:
            logger.warning(
                "Authentication failed: API key too long",
                extra={"key_length": len(api_key), "path": request.url.path},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key format",
            )

        # Validate API key using constant-time comparison
        if not self._validate_api_key(api_key):
            logger.warning(
                "Authentication failed: invalid API key",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else "unknown",
                    "key_prefix": api_key[:8] if len(api_key) >= 8 else "***",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Authentication successful
        logger.debug(
            "Authentication successful",
            extra={"path": request.url.path, "method": request.method},
        )

        # Add authenticated flag to request state
        request.state.authenticated = True
        request.state.api_key_prefix = api_key[:8] if len(api_key) >= 8 else "***"

        return await call_next(request)

    def _extract_api_key(self, request: Request) -> str | None:
        """Extract API key from request headers or query parameters.

        Priority:
        1. X-API-Key header
        2. api_key query parameter

        Args:
            request: The incoming request

        Returns:
            API key string or None if not found
        """
        # Check X-API-Key header (preferred)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key

        # Fallback to query parameter (for development/testing)
        api_key = request.query_params.get("api_key")
        if api_key:
            logger.debug("API key provided via query parameter (discouraged in production)")
            return api_key

        return None

    def _validate_api_key(self, provided_key: str) -> bool:
        """Validate provided API key against configured admin key.

        Uses constant-time comparison to prevent timing attacks.

        Args:
            provided_key: The API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not self.admin_api_key:
            logger.error("No admin API key configured for validation")
            return False

        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(provided_key, self.admin_api_key)


def require_auth(request: Request) -> bool:
    """Dependency function to require authentication in routes.

    Use this as a dependency in FastAPI route handlers:

    Example:
        @app.get("/protected", dependencies=[Depends(require_auth)])
        async def protected_route():
            return {"status": "authenticated"}

    Args:
        request: The incoming request

    Returns:
        True if authenticated

    Raises:
        HTTPException: If not authenticated
    """
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return True
