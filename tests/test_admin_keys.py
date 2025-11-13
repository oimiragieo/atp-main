import pytest
from fastapi.testclient import TestClient

# Optional 5s timeout if pytest-timeout is installed
if hasattr(pytest.mark, "timeout"):
    timeout = pytest.mark.timeout(5)
else:

    def timeout(fn):
        return fn


from router_service import admin_keys


def _reset():
    admin_keys.reset_for_tests()


@timeout
def test_admin_key_crud(monkeypatch):
    # Enable lightweight timing instrumentation
    monkeypatch.setenv("ADMIN_TIMING", "1")
    _reset()
    monkeypatch.setenv("ROUTER_DISABLE_PERSIST_THREAD", "1")
    monkeypatch.setenv("ROUTER_ADMIN_KEYS", "seed:read+write")
    from router_service.service import app

    client = TestClient(app)
    resp = client.get("/admin/keys", headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    assert len(resp.json()["keys"]) == 1
    # Create new write key
    resp = client.post("/admin/keys", json={"roles": ["read", "write"]}, headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    new_plain = resp.json()["key"]
    new_hash = resp.json()["hash"]
    # Verify list has 2
    resp = client.get("/admin/keys", headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    assert len(resp.json()["keys"]) == 2
    # New key can read
    assert client.get("/admin/version", headers={"x-api-key": new_plain}).status_code == 200
    # Delete new key using seed
    assert client.delete(f"/admin/keys/{new_hash}", headers={"x-api-key": "seed"}).status_code == 200
    # Create another write key so we can delete seed (avoid last-key rule)
    resp = client.post("/admin/keys", json={"roles": ["read", "write"]}, headers={"x-api-key": "seed"})
    assert resp.status_code == 200
    second_plain = resp.json()["key"]
    second_hash = resp.json()["hash"]
    # Delete seed using second key
    seed_hash = admin_keys.hash_key("seed")
    assert client.delete(f"/admin/keys/{seed_hash}", headers={"x-api-key": second_plain}).status_code == 200
    # Only one key left; deleting it should fail (400)
    assert client.delete(f"/admin/keys/{second_hash}", headers={"x-api-key": second_plain}).status_code == 400
