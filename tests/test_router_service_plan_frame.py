import json
import threading
import time

import requests
import uvicorn


def run_app():
    from router_service.service import app

    uvicorn.run(app, host="127.0.0.1", port=8778, log_level="error")


def test_router_service_plan_frame():
    t = threading.Thread(target=run_app, daemon=True)
    t.start()
    for _ in range(50):
        try:
            r = requests.get("http://127.0.0.1:8778/healthz", timeout=0.3)
            if r.ok:
                break
        except Exception:
            time.sleep(0.1)
    else:
        raise AssertionError("router service failed to start")

    resp = requests.post(
        "http://127.0.0.1:8778/v1/ask",
        json={"prompt": "Summarize the following report: ..."},
        stream=True,
        timeout=5,
    )
    assert resp.status_code == 200
    lines = []
    for line in resp.iter_lines():
        if line:
            lines.append(json.loads(line))
    plan = lines[0]
    assert plan["type"] == "plan"
    assert "candidates" in plan and plan["candidates"]
    assert "prompt_hash" in plan and len(plan["prompt_hash"]) == 16
    final_candidates = [entry for entry in lines if entry.get("type") == "final"]
    assert final_candidates, "No final frame received"
    final = final_candidates[0]
    assert final.get("cluster_hint") == plan.get("cluster_hint")
    print("OK: plan frame test passed")


if __name__ == "__main__":
    test_router_service_plan_frame()
