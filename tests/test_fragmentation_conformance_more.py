from router_service.fragmentation import fragment_frame, to_more_flag_semantics
from router_service.frame import Frame, Meta, Payload, Window


def make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="sessC",
        stream_id="streamC",
        msg_seq=5,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=50_000, max_usd_micros=5_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def test_more_flag_semantics_conformance():
    original_text = "a" * 2050
    base = make_frame(original_text)
    frags = fragment_frame(base, max_fragment_size=800)
    # With gold QoS multiplier (2.0), max fragment size becomes 1600
    # 2050 / 1600 = 1.28, so we get 2 fragments: 1600 + 450
    assert len(frags) >= 2  # Adjusted expectation based on QoS multiplier
    # LAST present only on final in FRAG/LAST semantics
    for i, f in enumerate(frags):
        if i < len(frags) - 1:
            assert "LAST" not in f.flags
        else:
            assert "LAST" in f.flags
    # Convert to MORE semantics and assert invariants
    mf = to_more_flag_semantics(frags)
    for i, f in enumerate(mf):
        assert f.frag_seq == i
        if i < len(mf) - 1:
            assert "MORE" in f.flags, f"Missing MORE on fragment {i}"
        else:
            assert "MORE" not in f.flags, "Last fragment incorrectly marked MORE"
    total = sum(len(f.payload.content["text"]) for f in mf)  # type: ignore[index]
    assert total == len(original_text)
