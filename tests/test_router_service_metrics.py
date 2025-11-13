import json
import threading
import time

import requests
import uvicorn


def run_app():
    from router_service.service import app

    uvicorn.run(app, host="127.0.0.1", port=8779, log_level="error")


def test_router_service_metrics():
    t = threading.Thread(target=run_app, daemon=True)
    t.start()
    for _ in range(50):
        try:
            r = requests.get("http://127.0.0.1:8779/healthz", timeout=0.3)
            if r.ok:
                break
        except Exception:
            time.sleep(0.1)
    else:
        raise AssertionError("router service failed to start")

    # generate a call
    resp = requests.post(
        "http://127.0.0.1:8779/v1/ask",
        json={"prompt": "Classify this bug report"},
        stream=True,
        timeout=10,
    )
    lines = [json.loads(line) for line in resp.iter_lines() if line]
    finals = [line for line in lines if line.get("type") == "final"]
    final = finals[0]
    assert "energy_kwh" in final and "co2e_grams" in final
    m = requests.get("http://127.0.0.1:8779/metrics", timeout=3)
    assert m.status_code == 200
    body = m.text
    assert "atp_router_total_calls" in body
    assert "atp_router_model_calls" in body
    print("OK: metrics test passed")


if __name__ == "__main__":
    test_router_service_metrics()
