import importlib
import os

from fastapi.testclient import TestClient

os.environ["ROUTER_MAX_PROMPT_CHARS"] = "50"
os.environ["ROUTER_ADMIN_API_KEY"] = "k"
os.environ["ROUTER_ENABLE_METRICS"] = "1"

service = importlib.import_module("router_service.service")
app = service.app
client = TestClient(app)


def test_prompt_size_limit():
    big = "x" * 60
    r = client.post("/v1/ask", json={"prompt": big})
    assert r.status_code == 413
    assert r.json()["detail"] == "prompt_too_large"


def test_correlation_and_metrics():
    r = client.post("/v1/ask", headers={"x-correlation-id": "abc-123"}, json={"prompt": "short question"})
    assert r.status_code == 200
    assert r.headers.get("x-correlation-id") == "abc-123"
    m = client.get("/metrics")
    assert m.status_code == 200
    assert "promotion_total" in m.text
