import os

from fastapi.testclient import TestClient

from router_service.service import FAIR_SCHED, app

client = TestClient(app)


def test_fair_served_endpoint_basic():
    # Ensure no admin keys are loaded for this test
    os.environ.pop("ROUTER_ADMIN_KEYS", None)
    os.environ.pop("ROUTER_ADMIN_API_KEY", None)

    # Ensure clean state (test isolation)
    FAIR_SCHED._served.clear()  # type: ignore
    FAIR_SCHED._weights.clear()  # type: ignore
    # seed served counts by simulating grants
    FAIR_SCHED.set_weight("A", 2.0)
    FAIR_SCHED.set_weight("B", 1.0)
    # Directly manipulate internal served for test determinism (would normally acquire/release)
    FAIR_SCHED._served["A"] = 10  # type: ignore
    FAIR_SCHED._served["B"] = 4  # type: ignore
    resp = client.get("/admin/fair/served?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "served" in data
    # Ensure ordering by served desc
    assert data["served"][0]["session"] == "A"
    assert data["served"][0]["served"] == 10
    # Contains weight and ratio
    assert "served_per_weight" in data["served"][0]
