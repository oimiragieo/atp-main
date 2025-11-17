# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Integration tests for authentication middleware.

Tests the AuthenticationMiddleware implementation including:
- API key validation
- Public endpoint access
- Header and query parameter authentication
- Security features (constant-time comparison, DoS prevention)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from router_service.middleware.auth import PUBLIC_ENDPOINTS, AuthenticationMiddleware


@pytest.fixture
def app_with_auth():
    """Create FastAPI app with authentication middleware."""
    app = FastAPI()

    # Add authentication middleware
    app.add_middleware(
        AuthenticationMiddleware,
        admin_api_key="test-admin-key-32-characters-long-enough",
        require_auth=True,
    )

    # Add test endpoints
    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected():
        return {"message": "authenticated"}

    @app.post("/api/v1/ask")
    async def ask():
        return {"response": "test"}

    return app


@pytest.fixture
def client_with_auth(app_with_auth):
    """Create test client with authentication."""
    return TestClient(app_with_auth)


class TestPublicEndpoints:
    """Test that public endpoints don't require authentication."""

    def test_healthz_accessible_without_auth(self, client_with_auth):
        """Health check should be accessible without authentication."""
        response = client_with_auth.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_metrics_accessible_without_auth(self, client_with_auth):
        """Metrics endpoint should be accessible without authentication."""
        # Note: This will 404 as we don't have metrics endpoint in test app
        # but it shouldn't return 401
        response = client_with_auth.get("/metrics")
        assert response.status_code != 401


class TestAuthenticationRequired:
    """Test that protected endpoints require authentication."""

    def test_protected_endpoint_without_auth_returns_401(self, client_with_auth):
        """Protected endpoint should return 401 without API key."""
        response = client_with_auth.get("/protected")
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_ask_endpoint_without_auth_returns_401(self, client_with_auth):
        """Ask endpoint should require authentication."""
        response = client_with_auth.post("/api/v1/ask")
        assert response.status_code == 401


class TestHeaderAuthentication:
    """Test API key authentication via X-API-Key header."""

    def test_valid_api_key_in_header_grants_access(self, client_with_auth):
        """Valid API key in header should grant access."""
        headers = {"X-API-Key": "test-admin-key-32-characters-long-enough"}
        response = client_with_auth.get("/protected", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"message": "authenticated"}

    def test_invalid_api_key_in_header_returns_401(self, client_with_auth):
        """Invalid API key should return 401."""
        headers = {"X-API-Key": "wrong-key"}
        response = client_with_auth.get("/protected", headers=headers)
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_empty_api_key_returns_401(self, client_with_auth):
        """Empty API key should return 401."""
        headers = {"X-API-Key": ""}
        response = client_with_auth.get("/protected", headers=headers)
        assert response.status_code == 401


class TestQueryParameterAuthentication:
    """Test API key authentication via query parameter."""

    def test_valid_api_key_in_query_grants_access(self, client_with_auth):
        """Valid API key in query parameter should grant access."""
        response = client_with_auth.get("/protected?api_key=test-admin-key-32-characters-long-enough")
        assert response.status_code == 200

    def test_invalid_api_key_in_query_returns_401(self, client_with_auth):
        """Invalid API key in query should return 401."""
        response = client_with_auth.get("/protected?api_key=wrong-key")
        assert response.status_code == 401


class TestSecurityFeatures:
    """Test security features like DoS prevention."""

    def test_oversized_api_key_returns_401(self, client_with_auth):
        """Oversized API key should be rejected to prevent DoS."""
        oversized_key = "a" * 1000  # 1000 chars > 512 limit
        headers = {"X-API-Key": oversized_key}
        response = client_with_auth.get("/protected", headers=headers)
        assert response.status_code == 401
        assert "Invalid API key format" in response.json()["detail"]

    def test_header_takes_precedence_over_query(self, client_with_auth):
        """Header authentication should take precedence over query parameter."""
        headers = {"X-API-Key": "test-admin-key-32-characters-long-enough"}
        response = client_with_auth.get(
            "/protected?api_key=wrong-key",  # Wrong in query
            headers=headers,  # Correct in header
        )
        assert response.status_code == 200


class TestAuthenticationDisabled:
    """Test authentication middleware when disabled."""

    def test_disabled_auth_allows_all_requests(self):
        """When auth is disabled, all requests should be allowed."""
        app = FastAPI()

        # Add middleware with auth disabled
        app.add_middleware(
            AuthenticationMiddleware,
            admin_api_key="test-key",
            require_auth=False,
        )

        @app.get("/protected")
        async def protected():
            return {"message": "accessible"}

        client = TestClient(app)
        response = client.get("/protected")
        assert response.status_code == 200
        assert response.json() == {"message": "accessible"}


class TestRequestState:
    """Test that request state is properly set after authentication."""

    def test_authenticated_request_has_state(self):
        """Authenticated requests should have state.authenticated set."""
        app = FastAPI()

        app.add_middleware(
            AuthenticationMiddleware,
            admin_api_key="test-key-32-chars-long-enough-now",
            require_auth=True,
        )

        @app.get("/check-state")
        async def check_state(request):

            return {
                "authenticated": getattr(request.state, "authenticated", False),
                "has_key_prefix": hasattr(request.state, "api_key_prefix"),
            }

        client = TestClient(app)
        headers = {"X-API-Key": "test-key-32-chars-long-enough-now"}
        response = client.get("/check-state", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["has_key_prefix"] is True


@pytest.mark.parametrize("endpoint", PUBLIC_ENDPOINTS)
def test_all_public_endpoints_accessible(endpoint):
    """Verify all defined public endpoints are accessible without auth."""
    app = FastAPI()

    app.add_middleware(
        AuthenticationMiddleware,
        admin_api_key="test-key-long-enough-for-validation",
        require_auth=True,
    )

    # Add a catch-all route
    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def catch_all(path: str):
        return {"path": path}

    client = TestClient(app)

    # Remove leading slash for request
    path = endpoint.lstrip("/")

    # Try GET request
    response = client.get(f"/{path}")
    # Should not be 401 (Unauthorized)
    assert response.status_code != 401, f"Public endpoint {endpoint} returned 401"
