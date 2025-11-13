import threading
import time

import requests
import uvicorn

PORT = 8785


def run_app():
    from router_service.service import app

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="error")


def wait():
    for _ in range(50):
        try:
            r = requests.get(f"http://127.0.0.1:{PORT}/healthz", timeout=0.3)
            if r.ok:
                return
        except Exception:
            time.sleep(0.1)
    raise AssertionError("service start timeout")


def test_alpha_endpoints():
    t = threading.Thread(target=run_app, daemon=True)
    t.start()
    wait()
    r_ready = requests.get(f"http://127.0.0.1:{PORT}/readyz", timeout=2)
    assert r_ready.status_code == 200 and r_ready.json().get("ready") is not None
    r_ver = requests.get(f"http://127.0.0.1:{PORT}/admin/version", timeout=2, headers={"x-api-key": "test"})
    assert r_ver.status_code == 200 and "service_version" in r_ver.json()
    # schema endpoint
    r_schema = requests.get(
        f"http://127.0.0.1:{PORT}/admin/observation_schema", timeout=2, headers={"x-api-key": "test"}
    )
    assert r_schema.status_code == 200 and r_schema.json().get("version") >= 2
    # generate a call to create lifecycle entries
    _ = requests.post(f"http://127.0.0.1:{PORT}/v1/ask", json={"prompt": "hello test"}, timeout=10)
    metrics = requests.get(f"http://127.0.0.1:{PORT}/metrics", timeout=4).text
    assert "atp_router_service_version_info" in metrics
    assert "atp_router_lifecycle_events_total" in metrics
