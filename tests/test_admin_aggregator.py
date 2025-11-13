from typing import Any

import httpx
from fastapi.testclient import TestClient
from ui.admin_aggregator.app import app


class MockRouter:
    def __init__(self, base: str, version: str = "1.2.3", backend: str = "memory", status: str = "ok") -> None:
        self.base = base.rstrip("/")
        self.version = version
        self.backend = backend
        self.status = status

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/admin/version"):
            return httpx.Response(
                200,
                json={
                    "service_version": self.version,
                    "bandit_strategy": "ucb",
                    "schema_version": 1,
                    "max_prompt_chars": 6000,
                },
            )
        if path.endswith("/admin/state_health"):
            return httpx.Response(
                200,
                json={
                    "backend": self.backend,
                    "status": self.status,
                    "detail": {},
                },
            )
        if path.endswith("/admin/cluster_stats"):
            return httpx.Response(
                200,
                json={
                    "stats": [
                        {"cluster": "c1", "model": "mA", "calls": 10},
                        {"cluster": "c1", "model": "mB", "calls": 5},
                    ]
                },
            )
        if path.endswith("/admin/model_status"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"model": "mA", "status": "prod", "capabilities": ["chat"], "safety_grade": "A"},
                    ],
                    "promotions": 2,
                    "demotions": 1,
                },
            )
        return httpx.Response(404, json={"error": "not_found", "path": path})


def build_mock_client(timeout: float) -> httpx.AsyncClient:  # type: ignore[override]
    routers = [
        MockRouter("http://router-0:8000"),
        MockRouter("http://router-1:8000", status="error"),
    ]

    def transport_send(request: httpx.Request) -> httpx.Response:  # sync for MockTransport
        for r in routers:
            if request.url.host == httpx.URL(r.base).host and request.url.port == httpx.URL(r.base).port:
                return r.handler(request)
        return httpx.Response(400, json={"error": "bad_host"})

    transport = httpx.MockTransport(transport_send)
    return httpx.AsyncClient(transport=transport, timeout=timeout)


def test_summary_and_aggregates(monkeypatch: Any) -> None:
    # Configure env for app
    monkeypatch.setenv("ROUTERS", "http://router-0:8000,http://router-1:8000")
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")

    # Patch HTTP client builder
    monkeypatch.setattr("admin_aggregator.app._build_client", build_mock_client)

    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["routers_configured"] == 2

    r = client.get("/routers")
    assert r.status_code == 200
    assert len(r.json()["routers"]) == 2

    r = client.get("/summary")
    assert r.status_code == 200
    data = r.json()["routers"]
    assert "http://router-0:8000" in data
    assert "version" in data["http://router-0:8000"]
    assert "state_health" in data["http://router-0:8000"]

    r = client.get("/cluster_stats")
    assert r.status_code == 200
    cs = r.json()
    assert cs["errors"] == {}  # mock returns 200 for both
    assert len(cs["stats"]) == 4  # two routers x two models

    r = client.get("/model_status")
    assert r.status_code == 200
    ms = r.json()
    assert ms["promotions"] == 4  # 2 per router
    assert ms["demotions"] == 2  # 1 per router
    assert len(ms["models"]) == 2  # one per router
