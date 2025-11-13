from fastapi.testclient import TestClient

from router_service.service import app


def test_state_health_memory_backend():
    client = TestClient(app)
    r = client.get("/admin/state_health")
    assert r.status_code == 200
    data = r.json()
    assert data["backend"] == "memory"
    assert data["status"] == "ok"
