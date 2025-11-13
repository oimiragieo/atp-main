"""Tests for AGP explain endpoint functionality."""

import pytest
from fastapi.testclient import TestClient

from router_service.service import app


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


def test_agp_explain_basic(client):
    """Test basic AGP explain endpoint functionality."""
    response = client.get("/agp/explain?prefix=test")

    assert response.status_code == 200
    data = response.json()
    assert "prefix" in data
    assert "context" in data
    assert "decision" in data
    assert "rule_evaluation_trace" in data
    assert data["prefix"] == "test"
    assert data["context"] == {}


def test_agp_explain_with_context(client):
    """Test AGP explain endpoint with policy context."""
    response = client.get("/agp/explain?prefix=test&tenant=acme&task_type=qa&data_scope=secrets&data_scope=pci")

    assert response.status_code == 200
    data = response.json()
    assert data["prefix"] == "test"
    assert data["context"]["tenant"] == "acme"
    assert data["context"]["task_type"] == "qa"
    assert data["context"]["data_scope"] == ["secrets", "pci"]
    assert "decision" in data
    assert "rule_evaluation_trace" in data


def test_agp_explain_policy_evaluation(client):
    """Test that policy evaluation works correctly."""
    # Test with context that should match the allow rule
    response = client.get("/agp/explain?prefix=test&tenant=acme&task_type=qa&data_scope=public")

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "allow"
    assert len(data["rule_evaluation_trace"]) > 0

    # Check that the first rule matched
    first_rule = data["rule_evaluation_trace"][0]
    assert "rule" in first_rule
    assert "reasons" in first_rule


def test_agp_explain_deny_case(client):
    """Test policy evaluation that results in deny."""
    response = client.get("/agp/explain?prefix=test&tenant=unknown&task_type=unknown")

    assert response.status_code == 200
    data = response.json()
    # Should eventually deny due to the catch-all deny rule
    assert "decision" in data
    assert "rule_evaluation_trace" in data


def test_agp_explain_missing_prefix(client):
    """Test that missing prefix parameter returns error."""
    response = client.get("/agp/explain")

    # FastAPI should return 422 for missing required parameter
    assert response.status_code == 422


def test_agp_explain_empty_data_scope(client):
    """Test with empty data scope list."""
    response = client.get("/agp/explain?prefix=test&data_scope=")

    assert response.status_code == 200
    data = response.json()
    assert data["context"]["data_scope"] == [""]
