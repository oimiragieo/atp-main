"""Authentication configuration management.

Provides configuration management for enterprise authentication providers
with environment variable support and validation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AuthConfig:
    """Main authentication configuration."""

    # Session settings
    session_duration_hours: int = 24
    session_cleanup_interval_minutes: int = 5

    # Security settings
    require_https: bool = True
    secure_cookies: bool = True
    csrf_protection: bool = True

    # Rate limiting
    auth_rate_limit_per_minute: int = 60
    failed_login_lockout_minutes: int = 15
    max_failed_attempts: int = 5

    # Token settings
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    refresh_token_expiration_days: int = 30

    # Provider settings
    enabled_providers: list[str] = field(default_factory=list)
    default_provider: str = "admin_keys"

    # MFA settings
    mfa_enabled: bool = False
    mfa_required_for_admin: bool = True
    mfa_grace_period_minutes: int = 60

    # Audit settings
    audit_all_auth_events: bool = True
    audit_retention_days: int = 90

    @classmethod
    def from_environment(cls) -> AuthConfig:
        """Load configuration from environment variables."""
        return cls(
            session_duration_hours=int(os.getenv("AUTH_SESSION_DURATION_HOURS", "24")),
            session_cleanup_interval_minutes=int(os.getenv("AUTH_SESSION_CLEANUP_MINUTES", "5")),
            require_https=os.getenv("AUTH_REQUIRE_HTTPS", "true").lower() == "true",
            secure_cookies=os.getenv("AUTH_SECURE_COOKIES", "true").lower() == "true",
            csrf_protection=os.getenv("AUTH_CSRF_PROTECTION", "true").lower() == "true",
            auth_rate_limit_per_minute=int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "60")),
            failed_login_lockout_minutes=int(os.getenv("AUTH_FAILED_LOGIN_LOCKOUT_MINUTES", "15")),
            max_failed_attempts=int(os.getenv("AUTH_MAX_FAILED_ATTEMPTS", "5")),
            jwt_algorithm=os.getenv("AUTH_JWT_ALGORITHM", "HS256"),
            jwt_expiration_minutes=int(os.getenv("AUTH_JWT_EXPIRATION_MINUTES", "60")),
            refresh_token_expiration_days=int(os.getenv("AUTH_REFRESH_TOKEN_EXPIRATION_DAYS", "30")),
            enabled_providers=_parse_list(os.getenv("AUTH_ENABLED_PROVIDERS", "admin_keys")),
            default_provider=os.getenv("AUTH_DEFAULT_PROVIDER", "admin_keys"),
            mfa_enabled=os.getenv("AUTH_MFA_ENABLED", "false").lower() == "true",
            mfa_required_for_admin=os.getenv("AUTH_MFA_REQUIRED_FOR_ADMIN", "true").lower() == "true",
            mfa_grace_period_minutes=int(os.getenv("AUTH_MFA_GRACE_PERIOD_MINUTES", "60")),
            audit_all_auth_events=os.getenv("AUTH_AUDIT_ALL_EVENTS", "true").lower() == "true",
            audit_retention_days=int(os.getenv("AUTH_AUDIT_RETENTION_DAYS", "90")),
        )


def _parse_list(value: str) -> list[str]:
    """Parse comma-separated list from environment variable."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# Environment variable documentation
ENV_VAR_DOCS = {
    # Session settings
    "AUTH_SESSION_DURATION_HOURS": "Duration of authentication sessions in hours (default: 24)",
    "AUTH_SESSION_CLEANUP_MINUTES": "Interval for cleaning up expired sessions in minutes (default: 5)",
    # Security settings
    "AUTH_REQUIRE_HTTPS": "Require HTTPS for authentication endpoints (default: true)",
    "AUTH_SECURE_COOKIES": "Use secure flag for session cookies (default: true)",
    "AUTH_CSRF_PROTECTION": "Enable CSRF protection for authentication (default: true)",
    # Rate limiting
    "AUTH_RATE_LIMIT_PER_MINUTE": "Authentication attempts per minute per IP (default: 60)",
    "AUTH_FAILED_LOGIN_LOCKOUT_MINUTES": "Lockout duration after max failed attempts (default: 15)",
    "AUTH_MAX_FAILED_ATTEMPTS": "Maximum failed login attempts before lockout (default: 5)",
    # Token settings
    "AUTH_JWT_ALGORITHM": "JWT signing algorithm (default: HS256)",
    "AUTH_JWT_EXPIRATION_MINUTES": "JWT token expiration in minutes (default: 60)",
    "AUTH_REFRESH_TOKEN_EXPIRATION_DAYS": "Refresh token expiration in days (default: 30)",
    # Provider settings
    "AUTH_ENABLED_PROVIDERS": "Comma-separated list of enabled auth providers (default: admin_keys)",
    "AUTH_DEFAULT_PROVIDER": "Default authentication provider (default: admin_keys)",
    # MFA settings
    "AUTH_MFA_ENABLED": "Enable multi-factor authentication (default: false)",
    "AUTH_MFA_REQUIRED_FOR_ADMIN": "Require MFA for admin users (default: true)",
    "AUTH_MFA_GRACE_PERIOD_MINUTES": "Grace period for MFA verification (default: 60)",
    # Audit settings
    "AUTH_AUDIT_ALL_EVENTS": "Audit all authentication events (default: true)",
    "AUTH_AUDIT_RETENTION_DAYS": "Audit log retention period in days (default: 90)",
    # OIDC Generic Provider
    "OIDC_CLIENT_ID": "OIDC client ID",
    "OIDC_CLIENT_SECRET": "OIDC client secret",
    "OIDC_DISCOVERY_URL": "OIDC discovery URL (.well-known/openid_configuration)",
    "OIDC_ISSUER": "OIDC issuer URL",
    "OIDC_AUTH_ENDPOINT": "OIDC authorization endpoint",
    "OIDC_TOKEN_ENDPOINT": "OIDC token endpoint",
    "OIDC_USERINFO_ENDPOINT": "OIDC userinfo endpoint",
    "OIDC_JWKS_URI": "OIDC JWKS URI",
    "OIDC_AUDIENCE": "OIDC audience",
    "OIDC_REDIRECT_URI": "OIDC redirect URI",
    "OIDC_MFA_REQUIRED": "Require MFA for OIDC users (default: false)",
    # Okta Provider
    "OKTA_CLIENT_ID": "Okta client ID",
    "OKTA_CLIENT_SECRET": "Okta client secret",
    "OKTA_DOMAIN": "Okta domain (e.g., company.okta.com)",
    "OKTA_AUDIENCE": "Okta audience (default: api://default)",
    "OKTA_REDIRECT_URI": "Okta redirect URI",
    "OKTA_MFA_REQUIRED": "Require MFA for Okta users (default: false)",
    # Azure AD Provider
    "AZURE_CLIENT_ID": "Azure AD client ID",
    "AZURE_CLIENT_SECRET": "Azure AD client secret",
    "AZURE_TENANT_ID": "Azure AD tenant ID (default: common)",
    "AZURE_AUDIENCE": "Azure AD audience",
    "AZURE_REDIRECT_URI": "Azure AD redirect URI",
    "AZURE_MFA_REQUIRED": "Require MFA for Azure AD users (default: false)",
    # Auth0 Provider
    "AUTH0_CLIENT_ID": "Auth0 client ID",
    "AUTH0_CLIENT_SECRET": "Auth0 client secret",
    "AUTH0_DOMAIN": "Auth0 domain (e.g., company.auth0.com)",
    "AUTH0_AUDIENCE": "Auth0 audience",
    "AUTH0_REDIRECT_URI": "Auth0 redirect URI",
    "AUTH0_MFA_REQUIRED": "Require MFA for Auth0 users (default: false)",
}


def get_config_documentation() -> dict[str, str]:
    """Get documentation for all authentication environment variables."""
    return ENV_VAR_DOCS.copy()


def validate_config(config: AuthConfig) -> list[str]:
    """Validate authentication configuration and return list of issues."""
    issues = []

    # Validate session settings
    if config.session_duration_hours < 1:
        issues.append("Session duration must be at least 1 hour")
    if config.session_duration_hours > 168:  # 1 week
        issues.append("Session duration should not exceed 1 week")

    # Validate rate limiting
    if config.auth_rate_limit_per_minute < 1:
        issues.append("Auth rate limit must be at least 1 per minute")
    if config.max_failed_attempts < 1:
        issues.append("Max failed attempts must be at least 1")

    # Validate JWT settings
    if config.jwt_algorithm not in ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]:
        issues.append(f"Unsupported JWT algorithm: {config.jwt_algorithm}")
    if config.jwt_expiration_minutes < 5:
        issues.append("JWT expiration must be at least 5 minutes")

    # Validate providers
    valid_providers = ["admin_keys", "oidc", "okta", "azure_ad", "auth0", "saml"]
    for provider in config.enabled_providers:
        if provider not in valid_providers:
            issues.append(f"Unknown provider: {provider}")

    if config.default_provider not in valid_providers:
        issues.append(f"Unknown default provider: {config.default_provider}")

    # Validate audit settings
    if config.audit_retention_days < 1:
        issues.append("Audit retention must be at least 1 day")

    return issues


def get_required_env_vars_for_provider(provider: str) -> list[str]:
    """Get required environment variables for a specific provider."""
    provider_vars = {
        "oidc": ["OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"],
        "okta": ["OKTA_CLIENT_ID", "OKTA_CLIENT_SECRET", "OKTA_DOMAIN"],
        "azure_ad": ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"],
        "auth0": ["AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "AUTH0_DOMAIN"],
        "admin_keys": [],  # Uses existing admin keys system
        "saml": [],  # Not implemented yet
    }

    return provider_vars.get(provider, [])


def check_provider_configuration(provider: str) -> dict[str, bool]:
    """Check if a provider is properly configured."""
    required_vars = get_required_env_vars_for_provider(provider)
    config_status = {}

    for var in required_vars:
        config_status[var] = bool(os.getenv(var))

    return config_status
