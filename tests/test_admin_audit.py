from fastapi.testclient import TestClient


def test_admin_audit_events(monkeypatch):
    monkeypatch.setenv("ROUTER_DISABLE_PERSIST_THREAD", "1")
    monkeypatch.setenv("ROUTER_ADMIN_KEYS", "seed:read+write")
    from router_service.service import app

    client = TestClient(app)
    # Create a new key (generates key.add)
    resp = client.post("/admin/keys", json={"roles": ["read"]}, headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    new_hash = resp.json()["hash"]
    # Delete newly created key (generates key.remove)
    resp = client.delete(f"/admin/keys/{new_hash}", headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    # Fetch audit log
    resp = client.get("/admin/audit", headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    events = {it["event"] for it in items}
    assert "key.add" in events and "key.remove" in events
