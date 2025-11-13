from router_service.fragmentation import Reassembler, fragment_frame
from router_service.frame import Frame, Meta, Payload, Window


def make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="s",
        stream_id="st",
        msg_seq=42,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def test_fragmentation_conformance_entry_flags_and_sequence():
    # Arrange: payload large enough to fragment into multiple frames
    base = make_frame("X" * 700)
    frags = fragment_frame(base, max_fragment_size=200)

    # Assert: contiguous frag_seq starting from 0
    assert [f.frag_seq for f in frags] == list(range(len(frags)))

    # Assert: every fragment has FRAG; only last has LAST
    assert all("FRAG" in f.flags for f in frags)
    assert all(("LAST" in f.flags) == (i == len(frags) - 1) for i, f in enumerate(frags))

    # Reassembly conformance: produces a single REASSEMBLED frame with same msg_seq
    r = Reassembler()
    final = None
    for f in frags:
        out = r.push(f)
        if out is not None:
            final = out
    assert final is not None
    assert final.msg_seq == base.msg_seq
    assert "REASSEMBLED" in final.flags
    assert "FRAG" not in final.flags and "LAST" not in final.flags
    # Payload integrity
    assert isinstance(final.payload.content, dict)
    assert final.payload.content.get("text") == base.payload.content.get("text")
