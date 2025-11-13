"""Tests for AGP trace utility functionality."""

import tempfile
from unittest.mock import patch

import pytest
import yaml

from tools.agptrace import AGPTracer


@pytest.fixture
def sample_route_table():
    """Sample route table for testing."""
    return {
        "router1": {"10.0.0.0/8": {"next_hop": "router2", "path": [65001, 65002], "local_pref": 100}},
        "router2": {"10.0.0.0/8": {"next_hop": "router3", "path": [65002, 65003], "local_pref": 150}},
        "router3": {"10.0.0.0/8": {"next_hop": "router3", "path": [65003], "local_pref": 200}},
    }


@pytest.fixture
def tracer_with_table(sample_route_table):
    """Create a tracer with the sample route table."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_route_table, f)
        f.flush()

        tracer = AGPTracer(f.name)
        return tracer


def test_trace_successful_route(tracer_with_table):
    """Test tracing a successful route."""
    result = tracer_with_table.trace_route("10.0.0.0/8", "router1")

    assert result["prefix"] == "10.0.0.0/8"
    assert result["initial_ttl"] == 64
    assert len(result["hops"]) == 3
    assert result["trace_complete"] is True

    # Check first hop
    hop1 = result["hops"][0]
    assert hop1["hop"] == 1
    assert hop1["router"] == "router1"
    assert hop1["ttl"] == 63
    assert hop1["status"] == "FORWARD"
    assert hop1["next_hop"] == "router2"
    assert hop1["path"] == [65001, 65002]
    assert hop1["local_pref"] == 100

    # Check destination hop
    hop3 = result["hops"][2]
    assert hop3["status"] == "DESTINATION_REACHED"


def test_trace_no_route():
    """Test tracing when no route exists."""
    route_table = {"router1": {}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(route_table, f)
        f.flush()

        tracer = AGPTracer(f.name)
        result = tracer.trace_route("10.0.0.0/8", "router1")

    assert len(result["hops"]) == 1
    assert result["hops"][0]["status"] == "NO_ROUTE"
    assert result["trace_complete"] is True


def test_trace_loop_detection():
    """Test loop detection in routing."""
    route_table = {
        "router1": {"10.0.0.0/8": {"next_hop": "router2"}},
        "router2": {"10.0.0.0/8": {"next_hop": "router1"}},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(route_table, f)
        f.flush()

        tracer = AGPTracer(f.name)
        result = tracer.trace_route("10.0.0.0/8", "router1", max_hops=5)

    assert len(result["hops"]) >= 2
    # Should detect loop and stop
    last_hop = result["hops"][-1]
    assert last_hop["status"] == "LOOP_DETECTED"


def test_trace_ttl_expiry():
    """Test TTL expiry handling."""
    route_table = {
        "router1": {"10.0.0.0/8": {"next_hop": "router2"}},
        "router2": {"10.0.0.0/8": {"next_hop": "router3"}},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(route_table, f)
        f.flush()

        tracer = AGPTracer(f.name)
        result = tracer.trace_route("10.0.0.0/8", "router1", initial_ttl=2)

    # Should have TTL expiry
    assert any(hop["status"] == "TTL_EXPIRED" for hop in result["hops"])


def test_trace_max_hops():
    """Test maximum hops limit."""
    route_table = {
        "router1": {"10.0.0.0/8": {"next_hop": "router2"}},
        "router2": {"10.0.0.0/8": {"next_hop": "router3"}},
        "router3": {"10.0.0.0/8": {"next_hop": "router4"}},
        "router4": {"10.0.0.0/8": {"next_hop": "router5"}},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(route_table, f)
        f.flush()

        tracer = AGPTracer(f.name)
        result = tracer.trace_route("10.0.0.0/8", "router1", max_hops=2)

    assert len(result["hops"]) == 2
    assert result["trace_complete"] is False


def test_cli_tool():
    """Test the CLI tool execution."""
    route_table = {"router1": {"10.0.0.0/8": {"next_hop": "router2", "path": [65001], "local_pref": 100}}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(route_table, f)
        f.flush()

        # Test CLI execution
        with patch("sys.argv", ["agptrace", f.name, "10.0.0.0/8", "--start-router", "router1"]):
            from tools.agptrace import main

            # Should not raise exception
            main()


# API Endpoint Tests


@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    from fastapi.testclient import TestClient

    from router_service.service import app

    return TestClient(app)


def test_agp_trace_api_basic(client):
    """Test basic AGP trace API endpoint."""
    response = client.get("/agp/trace?prefix=10.0.0.0/8&start_router=router1")

    assert response.status_code == 200
    data = response.json()
    assert "prefix" in data
    assert "start_router" in data
    assert "hops" in data
    assert "total_hops" in data
    assert "trace_complete" in data
    assert data["prefix"] == "10.0.0.0/8"
    assert data["start_router"] == "router1"


def test_agp_trace_api_with_parameters(client):
    """Test AGP trace API with custom parameters."""
    response = client.get("/agp/trace?prefix=10.0.0.0/8&start_router=router1&max_hops=5&ttl=32")

    assert response.status_code == 200
    data = response.json()
    assert data["initial_ttl"] == 32
    assert len(data["hops"]) <= 5


def test_agp_trace_api_missing_prefix(client):
    """Test AGP trace API with missing prefix parameter."""
    response = client.get("/agp/trace?start_router=router1")

    # FastAPI should return 422 for missing required parameter
    assert response.status_code == 422


def test_agp_trace_api_missing_start_router(client):
    """Test AGP trace API with missing start_router parameter."""
    response = client.get("/agp/trace?prefix=10.0.0.0/8")

    # FastAPI should return 422 for missing required parameter
    assert response.status_code == 422


def test_agp_trace_api_invalid_max_hops(client):
    """Test AGP trace API with invalid max_hops parameter."""
    response = client.get("/agp/trace?prefix=10.0.0.0/8&start_router=router1&max_hops=150")

    # Should return 422 for max_hops exceeding limit
    assert response.status_code == 422
