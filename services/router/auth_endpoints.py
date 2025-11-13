"""Authentication endpoints for enterprise identity providers.

Provides OAuth/OIDC authentication flows, session management, and token handling
for enterprise identity providers like Okta, Azure AD, and Auth0.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .enterprise_auth import (
    AuthProvider,
    UserInfo,
    get_authenticator,
    require_authentication,
    require_admin
)

logger = logging.getLogger(__name__)

# Create router for authentication endpoints
auth_router = APIRouter(prefix="/auth", tags=["authentication"])

# In-memory state store for OAuth flows (in production, use Redis)
_oauth_states: Dict[str, Dict[str, Any]] = {}


class LoginRequest(BaseModel):
    """Login request model."""
    provider: str
    redirect_url: Optional[str] = None


class TokenRequest(BaseModel):
    """Token request model."""
    username: str
    password: str
    provider: Optional[str] = "admin_keys"


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    user_info: Dict[str, Any]


class UserInfoResponse(BaseModel):
    """User info response model."""
    user_id: str
    email: str
    name: str
    roles: list[str]
    groups: list[str]
    tenant_id: Optional[str] = None
    provider: str
    mfa_verified: bool


@auth_router.get("/providers")
async def list_providers():
    """List available authentication providers."""
    authenticator = get_authenticator()
    providers = []
    
    for name, config in authenticator.providers.items():
        if config.enabled:
            providers.append({
                "name": name,
                "type": config.provider_type.value,
                "authorization_url": f"/auth/login/{name}",
                "mfa_required": config.mfa_required
            })
    
    # Always include admin keys as a provider
    providers.append({
        "name": "admin_keys",
        "type": "admin_keys",
        "authorization_url": "/auth/token",
        "mfa_required": False
    })
    
    return {"providers": providers}


@auth_router.get("/login/{provider}")
async def initiate_login(
    provider: str,
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL to redirect to after login")
):
    """Initiate OAuth login flow for a provider."""
    authenticator = get_authenticator()
    
    if provider not in authenticator.providers:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    
    # Generate state parameter for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state and redirect URL
    _oauth_states[state] = {
        "provider": provider,
        "redirect_url": redirect_url,
        "created_at": datetime.utcnow(),
        "client_ip": request.client.host if request.client else None
    }
    
    # Get authorization URL
    auth_url = authenticator.get_authorization_url(provider, state)
    if not auth_url:
        raise HTTPException(status_code=500, detail="Failed to generate authorization URL")
    
    return RedirectResponse(url=auth_url)


@auth_router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter"),
    error: Optional[str] = Query(None, description="OAuth error")
):
    """Handle OAuth callback from identity provider."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    # Validate state parameter
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")
    
    oauth_state = _oauth_states.pop(state)
    
    # Check state expiration (5 minutes)
    if datetime.utcnow() - oauth_state["created_at"] > timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="State parameter expired")
    
    # Verify provider matches
    if oauth_state["provider"] != provider:
        raise HTTPException(status_code=400, detail="Provider mismatch")
    
    authenticator = get_authenticator()
    
    # Exchange code for token
    token_data = await authenticator.exchange_code_for_token(provider, code, state)
    if not token_data:
        raise HTTPException(status_code=500, detail="Failed to exchange code for token")
    
    # Validate the access token and get user info
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="No access token received")
    
    user_info = await authenticator._validate_jwt_token(access_token)
    if not user_info:
        raise HTTPException(status_code=500, detail="Failed to validate token")
    
    # Create session
    session_id = await authenticator.create_session(user_info)
    
    # Create response with session cookie
    redirect_url = oauth_state.get("redirect_url", "/")
    response = RedirectResponse(url=redirect_url)
    
    # Set secure session cookie
    response.set_cookie(
        key="atp_session",
        value=session_id,
        max_age=86400,  # 24 hours
        httponly=True,
        secure=True,  # Only over HTTPS in production
        samesite="lax"
    )
    
    logger.info(f"User {user_info.user_id} logged in via {provider}")
    return response


@auth_router.post("/token", response_model=TokenResponse)
async def create_token(
    username: str = Form(...),
    password: str = Form(...),
    provider: str = Form("admin_keys")
):
    """Create access token using username/password (for API access)."""
    authenticator = get_authenticator()
    
    if provider == "admin_keys":
        # Validate against admin keys system
        user_info = authenticator._validate_admin_key(password)
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # For admin keys, use the password as the token (it's already the API key)
        return TokenResponse(
            access_token=password,
            token_type="bearer",
            expires_in=86400,  # 24 hours
            user_info={
                "user_id": user_info.user_id,
                "email": user_info.email,
                "name": user_info.name,
                "roles": list(user_info.roles),
                "groups": list(user_info.groups),
                "provider": user_info.provider.value
            }
        )
    else:
        # For other providers, this would implement Resource Owner Password Credentials flow
        # This is generally not recommended for security reasons
        raise HTTPException(status_code=400, detail="Password flow not supported for this provider")


@auth_router.post("/refresh")
async def refresh_token(
    refresh_token: str = Form(...),
    provider: str = Form(...)
):
    """Refresh an access token."""
    authenticator = get_authenticator()
    
    token_data = await authenticator.refresh_token(refresh_token, provider)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    return token_data


@auth_router.get("/me", response_model=UserInfoResponse)
async def get_current_user(user_info: UserInfo = Depends(require_authentication())):
    """Get current user information."""
    return UserInfoResponse(
        user_id=user_info.user_id,
        email=user_info.email,
        name=user_info.name,
        roles=list(user_info.roles),
        groups=list(user_info.groups),
        tenant_id=user_info.tenant_id,
        provider=user_info.provider.value,
        mfa_verified=user_info.mfa_verified
    )


@auth_router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session_id: Optional[str] = Cookie(None, alias="atp_session")
):
    """Logout and revoke session."""
    if session_id:
        authenticator = get_authenticator()
        await authenticator.revoke_session(session_id)
    
    # Clear session cookie
    response.delete_cookie("atp_session")
    
    return {"message": "Logged out successfully"}


@auth_router.get("/sessions")
async def list_sessions(user_info: UserInfo = Depends(require_admin())):
    """List active sessions (admin only)."""
    authenticator = get_authenticator()
    
    sessions = []
    async with authenticator.session_lock:
        for session_id, session in authenticator.sessions.items():
            sessions.append({
                "session_id": session_id,
                "user_id": session.user_info.user_id,
                "email": session.user_info.email,
                "provider": session.user_info.provider.value,
                "created_at": session.created_at.isoformat(),
                "last_accessed": session.last_accessed.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "mfa_verified": session.mfa_verified
            })
    
    return {"sessions": sessions}


@auth_router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user_info: UserInfo = Depends(require_admin())
):
    """Revoke a specific session (admin only)."""
    authenticator = get_authenticator()
    
    success = await authenticator.revoke_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": f"Session {session_id} revoked"}


@auth_router.get("/config")
async def get_auth_config(user_info: UserInfo = Depends(require_admin())):
    """Get authentication configuration (admin only)."""
    authenticator = get_authenticator()
    
    config = {}
    for name, provider_config in authenticator.providers.items():
        config[name] = {
            "provider_type": provider_config.provider_type.value,
            "client_id": provider_config.client_id,
            "issuer": provider_config.issuer,
            "enabled": provider_config.enabled,
            "mfa_required": provider_config.mfa_required,
            "scopes": provider_config.scopes,
            "role_mapping": {k: list(v) for k, v in provider_config.role_mapping.items()}
        }
    
    return {"providers": config}


@auth_router.put("/config/{provider}")
async def update_provider_config(
    provider: str,
    config: Dict[str, Any],
    user_info: UserInfo = Depends(require_admin())
):
    """Update provider configuration (admin only)."""
    authenticator = get_authenticator()
    
    if provider not in authenticator.providers:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    
    provider_config = authenticator.providers[provider]
    
    # Update allowed fields
    if "enabled" in config:
        provider_config.enabled = bool(config["enabled"])
    if "mfa_required" in config:
        provider_config.mfa_required = bool(config["mfa_required"])
    if "role_mapping" in config:
        provider_config.role_mapping = {k: set(v) for k, v in config["role_mapping"].items()}
    
    logger.info(f"Updated configuration for provider {provider}")
    return {"message": f"Provider {provider} configuration updated"}


# Cleanup expired OAuth states periodically
async def cleanup_oauth_states():
    """Clean up expired OAuth states."""
    import asyncio
    
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            now = datetime.utcnow()
            expired_states = []
            
            for state, data in _oauth_states.items():
                if now - data["created_at"] > timedelta(minutes=10):
                    expired_states.append(state)
            
            for state in expired_states:
                _oauth_states.pop(state, None)
            
            if expired_states:
                logger.info(f"Cleaned up {len(expired_states)} expired OAuth states")
                
        except Exception as e:
            logger.error(f"OAuth state cleanup error: {e}")


# Background task management
_cleanup_task = None

def start_background_tasks():
    """Start background tasks if not already running."""
    global _cleanup_task
    if _cleanup_task is None:
        try:
            import asyncio
            _cleanup_task = asyncio.create_task(cleanup_oauth_states())
        except RuntimeError:
            # No event loop running, task will be started later
            pass