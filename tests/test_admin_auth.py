from fastapi.testclient import TestClient

from router_service import admin_keys
from router_service.service import app


def _reset():
    admin_keys.reset_for_tests()


client = TestClient(app)


def test_admin_guard_open_when_no_keys(monkeypatch):
    _reset()
    # No keys configured -> endpoints open (backwards compat) unless single api key set
    monkeypatch.delenv("ROUTER_ADMIN_KEYS", raising=False)
    resp = client.get("/admin/version")
    assert resp.status_code == 200


def test_admin_guard_enforces_roles(monkeypatch):
    _reset()
    monkeypatch.setenv("ROUTER_ADMIN_KEYS", "k1:read,k2:read+write")
    # Missing key
    resp = client.get("/admin/version")
    assert resp.status_code == 401
    # Read key works for GET
    resp = client.get("/admin/version", headers={"x-api-key": "k1"})
    assert resp.status_code == 200
    # Write required endpoint with read-only key fails
    resp = client.post("/admin/fair/weight?session=S&weight=2.0", headers={"x-api-key": "k1"})
    assert resp.status_code == 403
    # Write key succeeds
    resp = client.post("/admin/fair/weight?session=S&weight=2.0", headers={"x-api-key": "k2"})
    assert resp.status_code == 200
