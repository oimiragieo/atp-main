from router_service.ack_logic import AckTracker


def test_ack_monotonic_and_nack_after_last_only():
    t = AckTracker()
    sid, st, msg = "sC", "stC", 11
    # ack starts at -1 internally; no events yet
    a0, n0, d0 = t.note(sid, st, msg, frag_seq=0, is_last=False)
    assert a0 == 0 and n0 == [] and d0 is False
    # Out-of-order 3 without last -> no nacks yet
    a1, n1, d1 = t.note(sid, st, msg, frag_seq=3, is_last=False)
    assert a1 == 0 and n1 == [] and d1 is False
    # Mark last at 3 -> nacks emitted for 1,2
    a2, n2, d2 = t.note(sid, st, msg, frag_seq=3, is_last=True)
    assert a2 == 0 and set(n2) == {1, 2} and d2 is False
    # Fill 1 -> ack should still be 0 (since 2 missing)
    a3, n3, d3 = t.note(sid, st, msg, frag_seq=1, is_last=False)
    assert a3 == 1 and 2 in n3 and d3 is False
    # Fill 2 -> completes and ack becomes 3
    a4, n4, d4 = t.note(sid, st, msg, frag_seq=2, is_last=False)
    assert a4 == 3 and n4 == [] and d4 is True
    # Monotonic: ack never decreased across steps
    assert a0 <= a1 <= a2 <= a3 <= a4


def test_ack_backpressure_simulation():
    """POC: Simulate backpressure based on NACK count."""
    t = AckTracker()
    sid, st, msg = "s", "st", 1
    # Receive fragments with gaps to generate NACKs
    t.note(sid, st, msg, frag_seq=0, is_last=False)
    t.note(sid, st, msg, frag_seq=2, is_last=True)  # last at 2, missing 1
    _, nacks, _ = t.note(sid, st, msg, frag_seq=1, is_last=False)  # fill 1
    assert nacks == []  # no more nacks
    # Simulate backpressure: if nacks > 0, reduce window
    window = 10
    if len(nacks) > 0:
        window = max(1, window // 2)
    assert window == 10  # since nacks == []
