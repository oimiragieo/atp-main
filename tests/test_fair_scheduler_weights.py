from router_service.service import FAIR_SCHED


def test_set_and_snapshot_weights():
    FAIR_SCHED.set_weight("t1", 5.0)
    FAIR_SCHED.set_weight("t2", 2.5)
    snap = FAIR_SCHED.snapshot_weights()
    assert snap["t1"] == 5.0
    assert snap["t2"] == 2.5
    # ensure default weight remains 1.0 for unseen tenant
    assert snap.get("unseen", None) is None
