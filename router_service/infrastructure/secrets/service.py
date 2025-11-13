# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Secrets management service - Vault-ready abstraction."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class SecretsBackend(ABC):
    """Abstract secrets backend."""

    @abstractmethod
    async def get_secret(self, path: str, key: str | None = None) -> str | dict[str, Any]:
        """Get a secret from the backend."""

    @abstractmethod
    async def set_secret(self, path: str, data: dict[str, Any]) -> None:
        """Set a secret in the backend."""


class EnvironmentSecretsBackend(SecretsBackend):
    """Environment variable secrets backend (for development)."""

    async def get_secret(self, path: str, key: str | None = None) -> str | dict[str, Any]:
        """
        Get secret from environment variables.

        Args:
            path: Environment variable name (converted to uppercase)
            key: Optional key (ignored for env vars)

        Returns:
            Secret value
        """
        env_var = path.upper().replace("/", "_").replace("-", "_")
        value = os.getenv(env_var)

        if value is None:
            raise ValueError(f"Secret not found: {path}")

        logger.debug(f"Retrieved secret from environment: {env_var}")
        return value

    async def set_secret(self, path: str, data: dict[str, Any]) -> None:
        """Environment backend is read-only."""
        raise NotImplementedError("Environment backend is read-only")


class VaultSecretsBackend(SecretsBackend):
    """HashiCorp Vault secrets backend (for production)."""

    def __init__(
        self,
        vault_url: str,
        token: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
    ):
        """
        Initialize Vault backend.

        Args:
            vault_url: Vault server URL
            token: Vault token (for token auth)
            role_id: AppRole role ID (for AppRole auth)
            secret_id: AppRole secret ID (for AppRole auth)
        """
        self.vault_url = vault_url
        self._client = None

        # Try to import hvac
        try:
            import hvac

            self._client = hvac.Client(url=vault_url)

            # Authenticate
            if token:
                self._client.token = token
            elif role_id and secret_id:
                response = self._client.auth.approle.login(
                    role_id=role_id,
                    secret_id=secret_id,
                )
                self._client.token = response["auth"]["client_token"]
            else:
                raise ValueError("Must provide token or AppRole credentials")

            logger.info("Vault client initialized", url=vault_url)

        except ImportError:
            logger.error("hvac library not installed, Vault backend unavailable")
            raise

    async def get_secret(self, path: str, key: str | None = None) -> str | dict[str, Any]:
        """
        Get secret from Vault.

        Args:
            path: Secret path in Vault
            key: Optional key within secret

        Returns:
            Secret value or dict of values
        """
        if self._client is None:
            raise RuntimeError("Vault client not initialized")

        response = self._client.secrets.kv.v2.read_secret_version(path=path)
        data = response["data"]["data"]

        if key:
            return data[key]

        return data

    async def set_secret(self, path: str, data: dict[str, Any]) -> None:
        """
        Set secret in Vault.

        Args:
            path: Secret path in Vault
            data: Secret data
        """
        if self._client is None:
            raise RuntimeError("Vault client not initialized")

        self._client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
        logger.info(f"Secret updated in Vault: {path}")


class SecretsService:
    """
    Secrets management service.

    Provides a unified interface for accessing secrets from multiple backends.
    Supports environment variables (dev) and HashiCorp Vault (production).
    """

    def __init__(self, backend: SecretsBackend | None = None):
        """
        Initialize secrets service.

        Args:
            backend: Secrets backend (defaults to environment)
        """
        self.backend = backend or EnvironmentSecretsBackend()
        self._cache: dict[str, Any] = {}

    @staticmethod
    def from_config() -> SecretsService:
        """Create secrets service from configuration."""
        # Check if Vault is configured
        vault_url = os.getenv("VAULT_URL")

        if vault_url:
            # Use Vault backend
            token = os.getenv("VAULT_TOKEN")
            role_id = os.getenv("VAULT_ROLE_ID")
            secret_id = os.getenv("VAULT_SECRET_ID")

            backend = VaultSecretsBackend(
                vault_url=vault_url,
                token=token,
                role_id=role_id,
                secret_id=secret_id,
            )
            logger.info("Using Vault secrets backend")
        else:
            # Use environment backend
            backend = EnvironmentSecretsBackend()
            logger.info("Using environment secrets backend")

        return SecretsService(backend=backend)

    async def get(self, path: str, key: str | None = None, cache: bool = True) -> str | dict:
        """
        Get a secret.

        Args:
            path: Secret path
            key: Optional key within secret
            cache: Whether to cache the secret

        Returns:
            Secret value
        """
        cache_key = f"{path}:{key}" if key else path

        # Check cache
        if cache and cache_key in self._cache:
            logger.debug(f"Secret retrieved from cache: {cache_key}")
            return self._cache[cache_key]

        # Get from backend
        value = await self.backend.get_secret(path, key)

        # Cache if requested
        if cache:
            self._cache[cache_key] = value

        return value

    async def set(self, path: str, data: dict[str, Any]) -> None:
        """
        Set a secret.

        Args:
            path: Secret path
            data: Secret data
        """
        await self.backend.set_secret(path, data)

        # Invalidate cache
        self._cache.clear()

    def clear_cache(self) -> None:
        """Clear the secrets cache."""
        self._cache.clear()
        logger.debug("Secrets cache cleared")

    # Convenience methods for common secrets
    async def get_database_password(self) -> str:
        """Get database password."""
        return await self.get("database/password", "password")

    async def get_admin_api_key(self) -> str:
        """Get admin API key."""
        return await self.get("router/admin", "api_key")

    async def get_redis_url(self) -> str:
        """Get Redis URL."""
        return await self.get("redis/url", "url")
