import os

from router_service import tracing
from router_service.fragmentation import Reassembler, fragment_frame
from router_service.frame import Frame, Meta, Payload, Window


def make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="sessT",
        stream_id="streamT",
        msg_seq=42,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def test_reassembly_emits_span_with_attributes():
    os.environ["ROUTER_TEST_TRACING_MODE"] = "dummy"
    tracing.init_tracing()
    tracing.SPAN_RECORDS.clear()

    f = make_frame("X" * 520)
    frags = fragment_frame(f, max_fragment_size=128)
    assert len(frags) > 1
    r = Reassembler()
    out = None
    for frag in frags:
        maybe = r.push(frag)
        if maybe is not None:
            out = maybe
    assert out is not None
    # Find reassembly span
    spans = [s for s in tracing.SPAN_RECORDS if s.get("name") == "fragment.reassemble"]
    assert spans, "expected fragment.reassemble span recorded"
    attrs = spans[-1]["attributes"]
    # Check basic attributes present
    assert attrs.get("frag.parts") == len(frags)
    assert attrs.get("frag.msg_seq") == 42
    # bytes equals length of reassembled payload
    assert attrs.get("frag.bytes") == len(out.payload.content["text"])  # type: ignore[index]
