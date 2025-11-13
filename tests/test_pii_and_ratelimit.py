import importlib
import os

from fastapi.testclient import TestClient

os.environ["ROUTER_PII_SCRUB"] = "1"
os.environ["ROUTER_RPS_LIMIT"] = "5"
os.environ["ROUTER_RPS_BURST"] = "5"
os.environ["ROUTER_ENABLE_METRICS"] = "1"

service = importlib.import_module("router_service.service")
app = service.app
client = TestClient(app)


def test_pii_scrub_and_debug_endpoint():
    email = "user123@example.com"
    ssn = "123-45-6789"
    prompt = f"Please process {email} and {ssn}"
    r = client.post("/v1/ask", json={"prompt": prompt})
    assert r.status_code == 200
    dbg = client.get("/admin/_debug_last_prompt")
    assert dbg.status_code == 200
    body = dbg.json()
    snippet = body["snippet"]
    assert "[REDACTED_EMAIL]" in snippet
    assert "[REDACTED_ID]" in snippet


def test_rate_limit_dropped_metric():
    # exceed burst quickly
    for _ in range(7):
        client.post("/v1/ask", json={"prompt": "ping"})
    m = client.get("/metrics")
    assert "rate_limit_dropped_total" in m.text
