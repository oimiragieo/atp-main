"""Tenant Isolation and ABAC Integration.

Middleware and utilities for implementing tenant isolation and integrating
ABAC policies with request processing.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .enterprise_auth import UserInfo, get_authenticator
from .policy_engine import Context, Effect, get_policy_engine

logger = logging.getLogger(__name__)


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce tenant isolation and ABAC policies."""

    def __init__(self, app, enforce_abac: bool = True):
        super().__init__(app)
        self.enforce_abac = enforce_abac
        self.authenticator = get_authenticator()
        self.policy_engine = get_policy_engine()

        # Paths that bypass ABAC (health checks, auth endpoints, etc.)
        self.bypass_paths = {
            "/healthz",
            "/health",
            "/metrics",
            "/api/v1/auth/login",
            "/api/v1/auth/callback",
            "/api/v1/auth/refresh",
            "/docs",
            "/openapi.json",
            "/redoc",
        }

    async def dispatch(self, request: Request, call_next):
        """Process request with tenant isolation and ABAC enforcement."""
        # Skip ABAC for bypass paths
        if request.url.path in self.bypass_paths or request.url.path.startswith("/static"):
            return await call_next(request)

        # Skip ABAC if not enforced
        if not self.enforce_abac:
            return await call_next(request)

        try:
            # Authenticate user
            user_info = await self.authenticator.authenticate_request(request)
            if not user_info:
                raise HTTPException(status_code=401, detail="Authentication required")

            # Add user info to request state for downstream use
            request.state.user_info = user_info

            # Determine resource and action from request
            resource, action = self._extract_resource_action(request)

            if resource and action:
                # Create ABAC context
                ctx = Context(
                    user_id=user_info.user_id,
                    tenant_id=user_info.tenant_id,
                    roles=user_info.roles,
                    groups=user_info.groups,
                    attributes=user_info.attributes,
                    resource=resource,
                    action=action,
                    environment={
                        "ip_address": self._get_client_ip(request),
                        "user_agent": request.headers.get("user-agent", ""),
                        "method": request.method,
                        "path": request.url.path,
                    },
                )

                # Evaluate ABAC policies
                decision = self.policy_engine.evaluate_abac(ctx)

                if not decision.permitted:
                    logger.warning(
                        f"ABAC denied access for user {user_info.user_id} to {resource}:{action}",
                        extra={
                            "user_id": user_info.user_id,
                            "tenant_id": user_info.tenant_id,
                            "resource": resource,
                            "action": action,
                            "applicable_policies": decision.applicable_policies,
                        },
                    )
                    raise HTTPException(status_code=403, detail=f"Access denied to {resource}:{action}")

                # Add decision to request state for logging/auditing
                request.state.abac_decision = decision

            # Process request
            response = await call_next(request)

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"ABAC middleware error: {e}")
            # In case of ABAC system failure, allow request to proceed
            # This ensures system availability even if ABAC is down
            return await call_next(request)

    def _extract_resource_action(self, request: Request) -> tuple[str | None, str | None]:
        """Extract resource and action from HTTP request."""
        path = request.url.path
        method = request.method.upper()

        # Map HTTP methods to actions
        method_action_map = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
            "HEAD": "read",
            "OPTIONS": "read",
        }

        action = method_action_map.get(method, method.lower())

        # Extract resource from path
        resource = self._path_to_resource(path)

        return resource, action

    def _path_to_resource(self, path: str) -> str | None:
        """Convert URL path to resource identifier."""
        # Remove leading/trailing slashes and split
        parts = path.strip("/").split("/")

        if not parts or parts[0] == "":
            return None

        # Handle API versioning
        if parts[0] == "api" and len(parts) > 1:
            if parts[1].startswith("v"):  # e.g., v1, v2
                parts = parts[2:]  # Skip api/v1
            else:
                parts = parts[1:]  # Skip api

        if not parts:
            return None

        # Build resource hierarchy
        resource_parts = []
        for _i, part in enumerate(parts):
            # Skip dynamic IDs (assume they're UUIDs or numeric)
            if self._is_dynamic_id(part):
                continue
            resource_parts.append(part)

        return "/".join(resource_parts) if resource_parts else None

    def _is_dynamic_id(self, part: str) -> bool:
        """Check if path part is likely a dynamic ID."""
        # UUID pattern
        if len(part) == 36 and part.count("-") == 4:
            return True

        # Numeric ID
        if part.isdigit():
            return True

        # Other common ID patterns
        if len(part) > 10 and (part.isalnum() or "_" in part or "-" in part):
            return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded headers (load balancer/proxy)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback to direct connection
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "unknown"


class TenantScopedService:
    """Base class for services that need tenant scoping."""

    def __init__(self):
        self.policy_engine = get_policy_engine()

    def check_tenant_access(self, user_info: UserInfo, resource: str, action: str) -> bool:
        """Check if user has access to resource within their tenant scope."""
        ctx = Context(
            user_id=user_info.user_id,
            tenant_id=user_info.tenant_id,
            roles=user_info.roles,
            groups=user_info.groups,
            attributes=user_info.attributes,
            resource=resource,
            action=action,
        )

        decision = self.policy_engine.evaluate_abac(ctx)
        return decision.permitted

    def get_tenant_filter(self, user_info: UserInfo) -> dict[str, Any]:
        """Get database filter for tenant isolation."""
        # Base tenant filter
        tenant_filter = {}

        if user_info.tenant_id:
            tenant_filter["tenant_id"] = user_info.tenant_id

        # Add additional filters based on roles
        if "admin" not in user_info.roles:
            # Non-admin users can only see their own data
            tenant_filter["user_id"] = user_info.user_id

        return tenant_filter

    def apply_tenant_scoping(self, query_params: dict[str, Any], user_info: UserInfo) -> dict[str, Any]:
        """Apply tenant scoping to query parameters."""
        scoped_params = query_params.copy()

        # Apply tenant filter
        tenant_filter = self.get_tenant_filter(user_info)
        scoped_params.update(tenant_filter)

        return scoped_params


def get_current_user(request: Request) -> UserInfo | None:
    """Get current user from request state."""
    return getattr(request.state, "user_info", None)


def require_tenant_access(resource: str, action: str):
    """Decorator to require tenant-scoped access to a resource."""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request from args (FastAPI dependency injection)
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                raise HTTPException(status_code=500, detail="Request not found")

            user_info = get_current_user(request)
            if not user_info:
                raise HTTPException(status_code=401, detail="Authentication required")

            # Check ABAC permissions
            service = TenantScopedService()
            if not service.check_tenant_access(user_info, resource, action):
                raise HTTPException(status_code=403, detail=f"Access denied to {resource}:{action}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def create_default_policies() -> None:
    """Create default ABAC policies for common scenarios."""
    from .policy_engine import ABACPolicy, AttributeCondition, Operator, PolicyRule

    engine = get_policy_engine()

    # Admin access policy
    admin_policy = ABACPolicy(
        policy_id="admin_full_access",
        name="Administrator Full Access",
        description="Administrators have full access to all resources",
        priority=1000,
        rules=[
            PolicyRule(
                rule_id="admin_permit_all",
                description="Permit all actions for admin role",
                effect=Effect.PERMIT,
                conditions=[AttributeCondition(attribute="user.roles", operator=Operator.CONTAINS, value="admin")],
            )
        ],
    )

    # Tenant isolation policy
    tenant_policy = ABACPolicy(
        policy_id="tenant_isolation",
        name="Tenant Isolation",
        description="Users can only access resources within their tenant",
        priority=900,
        rules=[
            PolicyRule(
                rule_id="same_tenant_access",
                description="Allow access to resources in same tenant",
                effect=Effect.PERMIT,
                conditions=[AttributeCondition(attribute="user.tenant_id", operator=Operator.EXISTS, value=None)],
                resources=["requests/*", "models/*", "policies/*"],
            )
        ],
    )

    # Read-only user policy
    readonly_policy = ABACPolicy(
        policy_id="readonly_user_access",
        name="Read-Only User Access",
        description="Read-only users can only perform read operations",
        priority=800,
        rules=[
            PolicyRule(
                rule_id="readonly_permit_read",
                description="Permit read actions for read role",
                effect=Effect.PERMIT,
                conditions=[AttributeCondition(attribute="user.roles", operator=Operator.CONTAINS, value="read")],
                actions=["read"],
            )
        ],
    )

    # Add policies to engine
    for policy in [admin_policy, tenant_policy, readonly_policy]:
        try:
            engine.add_abac_policy(policy)
            logger.info(f"Created default ABAC policy: {policy.policy_id}")
        except Exception as e:
            logger.error(f"Failed to create default policy {policy.policy_id}: {e}")
