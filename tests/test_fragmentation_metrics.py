from metrics.registry import REGISTRY
from router_service.fragmentation import fragment_frame
from router_service.frame import Frame, Meta, Payload, Window


def make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="s",
        stream_id="st",
        msg_seq=1,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def test_fragment_count_histogram_updates():
    # snapshot pre
    pre = REGISTRY.export()["histograms"].get("fragment_count_per_message")
    # ensure predictable sizes -> 1 fragment and >1 fragments
    f_small = make_frame("a" * 10)
    frags_small = fragment_frame(f_small, max_fragment_size=1024)
    assert len(frags_small) == 1

    f_big = make_frame("b" * 600)
    frags_big = fragment_frame(f_big, max_fragment_size=128)
    assert len(frags_big) > 1

    snap = REGISTRY.export()["histograms"].get("fragment_count_per_message")
    assert snap is not None
    # counts array length equals buckets+1 (overflow)
    assert len(snap["counts"]) == len(snap["buckets"]) + 1
    # Ensure the histogram changed compared to pre-snapshot (or that counts increased from zero)
    if pre is not None:
        assert sum(snap["counts"]) >= sum(pre["counts"]) + 2
    else:
        assert sum(snap["counts"]) >= 2
