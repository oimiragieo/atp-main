import time

from fastapi.testclient import TestClient

from router_service.service import app

client = TestClient(app)


def test_admin_rate_limit(monkeypatch):
    monkeypatch.setenv("ROUTER_ADMIN_KEYS", "k1:read+write")
    monkeypatch.setenv("ROUTER_ADMIN_RPS", "5")
    monkeypatch.setenv("ROUTER_ADMIN_RPS_BURST", "3")
    hit = 0
    limited = 0
    for _i in range(8):
        r = client.get("/admin/version", headers={"x-api-key": "k1"})
        if r.status_code == 200:
            hit += 1
        elif r.status_code == 429:
            limited += 1
        else:
            raise AssertionError(f"Unexpected status {r.status_code}")
        time.sleep(0.05)
    assert hit >= 3  # burst allowed
    assert limited >= 1  # some requests limited
