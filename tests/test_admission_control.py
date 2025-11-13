import pytest
from fastapi.testclient import TestClient

from router_service.service import _SESSION_ACTIVE, GLOBAL_AIMD, app


@pytest.fixture()
def client():
    return TestClient(app)


def test_admission_rejects_over_window(client):
    sess = "test-sess"
    # artificially set small window for determinism
    GLOBAL_AIMD.base = 1
    GLOBAL_AIMD.max_cap = 1
    GLOBAL_AIMD._states[sess] = GLOBAL_AIMD._states.get(sess) or GLOBAL_AIMD._states.setdefault(
        sess, GLOBAL_AIMD._ensure(sess)
    )
    GLOBAL_AIMD._states[sess].current = 1

    # occupy the session slot by simulating active stream
    _SESSION_ACTIVE[sess] = {"count": 1, "last_activity": 0.0}
    r = client.post(
        "/v1/ask",
        json={"prompt": "hi", "quality": "low", "latency_slo_ms": 500, "task_type": "qa", "conversation_id": sess},
    )
    assert r.status_code == 429, r.text
    _SESSION_ACTIVE.pop(sess, None)
