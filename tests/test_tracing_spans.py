import asyncio  # noqa: I001 (ordered intentionally with env setup)
import os  # noqa: I001
import pytest  # noqa: I001

# Enable tracing via env then import service to trigger init
os.environ["ROUTER_ENABLE_TRACING"] = "1"
os.environ["ROUTER_TEST_TRACING_MODE"] = "dummy"
os.environ["ROUTER_DISABLE_OTLP_EXPORT"] = "1"
from router_service import service  # noqa: E402,I001
from router_service import tracing  # noqa: E402,I001

tracing.init_tracing()  # ensure tracer active


def _find_span(name):
    return [s for s in tracing.SPAN_RECORDS if s["name"] == name]


@pytest.mark.asyncio
async def test_fair_scheduler_tracing_fast_path():
    # Acquire directly (fast path) to emit fair.acquire span
    sched = service.FAIR_SCHED
    # Minimal window so fast path likely; ensure empty queue
    tracing.init_tracing()
    ok = await sched.acquire("sessA", window_allowed=5, timeout=0.0)
    assert ok
    await sched.release("sessA")
    # Allow event loop to process any span exits
    await asyncio.sleep(0)
    spans = _find_span("fair.acquire")
    assert spans, "expected fair.acquire span"
    # last span should have fast_path attribute
    assert any(s.get("attributes", {}).get("fair.fast_path") for s in spans)


@pytest.mark.asyncio
async def test_aimd_feedback_span():
    from router_service.window_update import GLOBAL_AIMD

    tracing.init_tracing()
    GLOBAL_AIMD.feedback("sessB", latency_ms=50, ok=True)
    # feedback is sync but span recorded on exit
    spans = _find_span("aimd.feedback")
    assert spans, "expected aimd.feedback span"
    last = spans[-1]
    attrs = last["attributes"]
    assert attrs.get("aimd.session") == "sessB"
    assert "aimd.before" in attrs and "aimd.after" in attrs


@pytest.mark.asyncio
async def test_bandit_select_span(monkeypatch):
    # Force bandit strategy to thompson and instrument choose path
    import router_service.service as svc

    svc.BANDIT_STRATEGY = "thompson"
    # Craft minimal AskRequest
    from router_service.models import AskRequest

    req = AskRequest(prompt="hi", quality="standard")

    # Need event loop context for ask
    class DummyClient:
        host = "localtest"

    class DummyReq:
        client = DummyClient()
        headers = {}
        state = type("s", (), {})()

    # ensure tracer present
    tracing.init_tracing()
    await svc.ask(req, DummyReq())
    spans = _find_span("bandit.select")
    assert spans, "expected bandit.select span"
    assert spans[-1]["attributes"].get("bandit.strategy") == "thompson"
