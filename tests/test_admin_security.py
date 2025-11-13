#!/usr/bin/env python3
"""
Test for admin authentication hardening - ensures no test-specific bypasses.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from router_service import admin_keys
from router_service.service import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_admin_keys():
    """Setup clean admin keys for each test."""
    # Clear any existing keys
    admin_keys._KEYS.clear()
    admin_keys._PLAIN_CACHE.clear()

    # Add a test key with read/write roles
    test_key = "test-admin-key-12345"
    admin_keys.add_key(test_key, roles={"read", "write"}, persist=False)

    yield

    # Cleanup
    admin_keys._KEYS.clear()
    admin_keys._PLAIN_CACHE.clear()


def test_admin_endpoint_requires_authentication(client):
    """Test that admin endpoints require proper authentication."""
    # Test without any API key
    response = client.get("/admin/keys")
    assert response.status_code == 401
    assert "unauthorized" in response.json().get("error", "").lower()


def test_admin_endpoint_requires_valid_key(client):
    """Test that admin endpoints reject invalid API keys."""
    # Test with invalid API key
    response = client.get("/admin/keys", headers={"x-api-key": "invalid-key"})
    assert response.status_code == 401
    assert "unauthorized" in response.json().get("error", "").lower()


def test_admin_endpoint_accepts_valid_key(client):
    """Test that admin endpoints accept valid API keys."""
    # Test with valid API key
    response = client.get("/admin/keys", headers={"x-api-key": "test-admin-key-12345"})
    # Should not be 401/403 (authentication/authorization errors)
    assert response.status_code != 401
    assert response.status_code != 403


def test_admin_endpoint_enforces_roles(client):
    """Test that admin endpoints enforce role-based access."""
    # Add a read-only key
    read_only_key = "read-only-key-67890"
    admin_keys.add_key(read_only_key, roles={"read"}, persist=False)

    # Test read-only key can access read endpoints
    response = client.get("/admin/keys", headers={"x-api-key": read_only_key})
    assert response.status_code != 401
    assert response.status_code != 403

    # Test read-only key cannot access write endpoints (if any exist)
    # Note: This would need to be tested with actual write endpoints when available


def test_no_test_specific_bypasses():
    """Test that there are no test-specific authentication bypasses."""
    import os

    from router_service.service import admin_guard

    # Ensure PYTEST_CURRENT_TEST doesn't affect authentication
    original_env = os.environ.get("PYTEST_CURRENT_TEST")
    try:
        # Set test environment variable
        os.environ["PYTEST_CURRENT_TEST"] = "some_test"

        # Create guard function
        guard = admin_guard("read")

        # Test that guard still requires authentication even in test mode
        with pytest.raises(HTTPException) as exc_info:
            guard(None)  # No API key provided

        assert exc_info.value.status_code == 401

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = original_env
        else:
            os.environ.pop("PYTEST_CURRENT_TEST", None)


def test_production_security_consistency():
    """Test that production and test modes have consistent security behavior."""
    import os

    from router_service.service import admin_guard

    # Test both with and without PYTEST_CURRENT_TEST set
    scenarios = [
        ("production", None),
        ("test_mode", "some_test_name"),
    ]

    for scenario_name, test_env_value in scenarios:
        original_env = os.environ.get("PYTEST_CURRENT_TEST")
        try:
            if test_env_value is not None:
                os.environ["PYTEST_CURRENT_TEST"] = test_env_value
            else:
                os.environ.pop("PYTEST_CURRENT_TEST", None)

            guard = admin_guard("read")

            # Both should behave the same way: require authentication when keys exist
            with pytest.raises(HTTPException) as exc_info:
                guard(None)  # No API key provided

            assert exc_info.value.status_code == 401, f"Failed in {scenario_name}"

        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["PYTEST_CURRENT_TEST"] = original_env
            else:
                os.environ.pop("PYTEST_CURRENT_TEST", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
