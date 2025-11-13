from fastapi.testclient import TestClient


def test_fair_wait_percentiles(monkeypatch):
    monkeypatch.setenv("ROUTER_DISABLE_PERSIST_THREAD", "1")
    from router_service.service import FAIR_SCHED, app  # import after env

    # Simulate wait observations directly (bypass scheduling complexity)
    # Buckets defined: [1,5,10,25,50,100,250,500,1000]
    FAIR_SCHED._wait_hist.observe(2)  # falls in <=5
    FAIR_SCHED._wait_hist.observe(7)  # <=10
    FAIR_SCHED._wait_hist.observe(30)  # <=50
    FAIR_SCHED._wait_hist.observe(400)  # <=500
    FAIR_SCHED._wait_hist.observe(900)  # <=1000
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text.splitlines()
    # Extract percentile lines
    p_lines = {line.split()[0]: line for line in body if line.startswith("fair_sched_wait_ms_p")}
    # Expect p50, p90, p95, p99 present
    for p in ("fair_sched_wait_ms_p50", "fair_sched_wait_ms_p90", "fair_sched_wait_ms_p95", "fair_sched_wait_ms_p99"):
        assert p in p_lines, f"missing {p} in metrics output"

    # Basic sanity: p50 bucket boundary should be >= one of inserted low latencies; p99 likely highest bucket
    def parse_val(line):
        return float(line.split()[1])

    v50 = parse_val(p_lines["fair_sched_wait_ms_p50"])
    v99 = parse_val(p_lines["fair_sched_wait_ms_p99"])
    assert v50 <= v99
