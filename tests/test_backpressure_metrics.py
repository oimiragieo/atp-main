from fastapi.testclient import TestClient

from router_service.errors import ErrorCode
from router_service.service import _SESSION_ACTIVE, GLOBAL_AIMD, app

client = TestClient(app)


def test_backpressure_error_code_and_metrics():
    sess = "bp-sess"
    # force window=1
    st = GLOBAL_AIMD._ensure(sess)  # type: ignore
    st.current = 1
    _SESSION_ACTIVE[sess] = {"count": 1, "last_activity": 0.0}  # occupy
    r = client.post(
        "/v1/ask",
        json={"prompt": "hello", "quality": "low", "latency_slo_ms": 400, "task_type": "qa", "conversation_id": sess},
    )
    assert r.status_code == 429
    body = r.json()
    assert body.get("error") == ErrorCode.BACKPRESSURE.value
    # metrics scrape includes utilization metrics
    m = client.get("/metrics").text
    assert "flow_active_sessions" in m
    assert "flow_window_utilization_pct" in m
    _SESSION_ACTIVE.pop(sess, None)
