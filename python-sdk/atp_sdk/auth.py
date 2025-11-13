# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ATP SDK Authentication

Authentication management for the ATP SDK.
"""

import asyncio
import time
from typing import Dict, Optional
import jwt
from .config import ATPConfig
from .exceptions import AuthenticationError, ConfigurationError


class AuthManager:
    """Manages authentication for ATP API requests."""
    
    def __init__(self, config: ATPConfig):
        self.config = config
        self._token_cache: Optional[str] = None
        self._token_expires_at: Optional[float] = None
    
    def get_auth_header(self) -> Dict[str, str]:
        """Get authentication header for requests."""
        if not self.config.api_key:
            raise AuthenticationError("No API key configured")
        
        # Check if API key is a JWT token
        if self._is_jwt_token(self.config.api_key):
            token = self._get_or_refresh_token()
            return {"Authorization": f"Bearer {token}"}
        else:
            # Simple API key authentication
            return {"Authorization": f"Bearer {self.config.api_key}"}
    
    async def get_auth_header_async(self) -> Dict[str, str]:
        """Get authentication header for async requests."""
        if not self.config.api_key:
            raise AuthenticationError("No API key configured")
        
        # Check if API key is a JWT token
        if self._is_jwt_token(self.config.api_key):
            token = await self._get_or_refresh_token_async()
            return {"Authorization": f"Bearer {token}"}
        else:
            # Simple API key authentication
            return {"Authorization": f"Bearer {self.config.api_key}"}
    
    def _is_jwt_token(self, token: str) -> bool:
        """Check if the token is a JWT token."""
        try:
            # JWT tokens have 3 parts separated by dots
            parts = token.split('.')
            if len(parts) != 3:
                return False
            
            # Try to decode without verification (just to check format)
            jwt.decode(token, options={"verify_signature": False})
            return True
        except:
            return False
    
    def _get_or_refresh_token(self) -> str:
        """Get cached token or refresh if expired."""
        current_time = time.time()
        
        # Check if we have a cached token that's still valid
        if (self._token_cache and 
            self._token_expires_at and 
            current_time < self._token_expires_at - 60):  # 60 second buffer
            return self._token_cache
        
        # Refresh token
        return self._refresh_token()
    
    async def _get_or_refresh_token_async(self) -> str:
        """Get cached token or refresh if expired (async version)."""
        current_time = time.time()
        
        # Check if we have a cached token that's still valid
        if (self._token_cache and 
            self._token_expires_at and 
            current_time < self._token_expires_at - 60):  # 60 second buffer
            return self._token_cache
        
        # Refresh token
        return await self._refresh_token_async()
    
    def _refresh_token(self) -> str:
        """Refresh the authentication token."""
        try:
            # Decode the JWT to get expiration
            decoded = jwt.decode(self.config.api_key, options={"verify_signature": False})
            
            # Check if token is expired
            exp = decoded.get('exp')
            if exp and time.time() >= exp:
                raise AuthenticationError("JWT token has expired")
            
            # For now, we'll use the original token
            # In a real implementation, you might refresh with a refresh token
            self._token_cache = self.config.api_key
            self._token_expires_at = exp
            
            return self._token_cache
            
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid JWT token: {e}")
    
    async def _refresh_token_async(self) -> str:
        """Refresh the authentication token (async version)."""
        # For now, just call the sync version
        # In a real implementation, this might make async HTTP calls
        return self._refresh_token()
    
    def validate_token(self, token: Optional[str] = None) -> bool:
        """Validate the authentication token."""
        token_to_validate = token or self.config.api_key
        
        if not token_to_validate:
            return False
        
        try:
            if self._is_jwt_token(token_to_validate):
                # Decode JWT and check expiration
                decoded = jwt.decode(token_to_validate, options={"verify_signature": False})
                exp = decoded.get('exp')
                
                if exp and time.time() >= exp:
                    return False
            
            return True
            
        except:
            return False
    
    def get_token_info(self) -> Dict:
        """Get information about the current token."""
        if not self.config.api_key:
            raise AuthenticationError("No API key configured")
        
        if self._is_jwt_token(self.config.api_key):
            try:
                decoded = jwt.decode(self.config.api_key, options={"verify_signature": False})
                return {
                    "type": "jwt",
                    "subject": decoded.get('sub'),
                    "issuer": decoded.get('iss'),
                    "audience": decoded.get('aud'),
                    "expires_at": decoded.get('exp'),
                    "issued_at": decoded.get('iat'),
                    "tenant_id": decoded.get('tenant_id'),
                    "project_id": decoded.get('project_id'),
                    "scopes": decoded.get('scopes', [])
                }
            except jwt.InvalidTokenError as e:
                raise AuthenticationError(f"Invalid JWT token: {e}")
        else:
            return {
                "type": "api_key",
                "key_prefix": self.config.api_key[:8] + "..." if len(self.config.api_key) > 8 else "***"
            }


class TokenManager:
    """Advanced token management with automatic refresh."""
    
    def __init__(self, config: ATPConfig):
        self.config = config
        self.auth_manager = AuthManager(config)
        self._refresh_lock = asyncio.Lock()
    
    async def get_valid_token(self) -> str:
        """Get a valid token, refreshing if necessary."""
        async with self._refresh_lock:
            if not self.auth_manager.validate_token():
                # Token is invalid or expired, need to refresh
                await self._refresh_token()
            
            header = await self.auth_manager.get_auth_header_async()
            return header["Authorization"].replace("Bearer ", "")
    
    async def _refresh_token(self):
        """Refresh the token using refresh token or re-authentication."""
        # This would implement the actual token refresh logic
        # For now, we'll raise an error if the token is expired
        if not self.auth_manager.validate_token():
            raise AuthenticationError("Token expired and no refresh mechanism available")


class ServiceAccountAuth:
    """Service account authentication for server-to-server communication."""
    
    def __init__(self, service_account_key: str, scopes: Optional[list] = None):
        self.service_account_key = service_account_key
        self.scopes = scopes or ["atp:read", "atp:write"]
        self._token_cache: Optional[str] = None
        self._token_expires_at: Optional[float] = None
    
    def get_auth_header(self) -> Dict[str, str]:
        """Get authentication header using service account."""
        token = self._get_or_refresh_service_token()
        return {"Authorization": f"Bearer {token}"}
    
    def _get_or_refresh_service_token(self) -> str:
        """Get or refresh service account token."""
        current_time = time.time()
        
        # Check if we have a cached token that's still valid
        if (self._token_cache and 
            self._token_expires_at and 
            current_time < self._token_expires_at - 60):
            return self._token_cache
        
        # Generate new service account token
        return self._generate_service_token()
    
    def _generate_service_token(self) -> str:
        """Generate a new service account token."""
        import json
        
        try:
            # Load service account key
            if self.service_account_key.startswith('{'):
                # JSON string
                key_data = json.loads(self.service_account_key)
            else:
                # File path
                with open(self.service_account_key, 'r') as f:
                    key_data = json.load(f)
            
            # Create JWT payload
            now = int(time.time())
            payload = {
                'iss': key_data['client_email'],
                'sub': key_data['client_email'],
                'aud': 'https://api.atp.company.com',
                'iat': now,
                'exp': now + 3600,  # 1 hour
                'scope': ' '.join(self.scopes)
            }
            
            # Sign JWT
            token = jwt.encode(payload, key_data['private_key'], algorithm='RS256')
            
            self._token_cache = token
            self._token_expires_at = payload['exp']
            
            return token
            
        except Exception as e:
            raise AuthenticationError(f"Failed to generate service account token: {e}")