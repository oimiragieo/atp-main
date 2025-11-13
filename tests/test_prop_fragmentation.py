import os
import random

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from router_service.fragmentation import Reassembler, fragment_frame
from router_service.frame import Frame, Meta, Payload, Window

# Strategy for random text (including empty) limited size for speed
text_st = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=0, max_size=800)


def make_frame(txt: str) -> Frame:
    return Frame(
        v=1,
        session_id="sess",
        stream_id="strm",
        msg_seq=0,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": txt}),
    )


_HIGH_EXAMPLES = int(os.environ.get("PROP_FRAG_HIGH_EXAMPLES", "0"))

# Default moderate examples; allow scaling up via env for CI stress runs
_ROUND_TRIP_EXAMPLES = 800 if _HIGH_EXAMPLES else 400


@settings(max_examples=_ROUND_TRIP_EXAMPLES, suppress_health_check=[HealthCheck.too_slow])
@given(text_st, st.integers(min_value=32, max_value=256))
def test_prop_fragment_round_trip(txt, frag_size):
    f = make_frame(txt)
    frags = fragment_frame(f, max_fragment_size=frag_size)
    # shuffle order
    random.shuffle(frags)
    # optionally insert a duplicate
    if frags:
        frags.insert(random.randint(0, len(frags)), frags[0])
    r = Reassembler()
    out = None
    for frag in frags:
        try:
            maybe = r.push(frag)
        except ValueError as err:  # B904
            raise AssertionError("Unexpected error during reassembly") from err
        if maybe:
            out = maybe
    assert out is not None
    assert out.payload.content["text"] == txt
    # checksum must match recomputed
    from router_service.fragmentation import _compute_checksum  # type: ignore

    if isinstance(out.payload.content, dict):
        assert out.payload.checksum == _compute_checksum(out.payload.content["text"])


_CORRUPT_EXAMPLES = 400 if _HIGH_EXAMPLES else 200


@settings(max_examples=_CORRUPT_EXAMPLES, suppress_health_check=[HealthCheck.too_slow])
@given(text_st, st.integers(min_value=32, max_value=256))
def test_prop_fragment_rejects_corruption(txt, frag_size):
    f = make_frame(txt)
    frags = fragment_frame(f, max_fragment_size=frag_size)
    if not frags:
        return
    # corrupt one fragment checksum to simulate tamper
    bad = frags[0]
    bad.payload.checksum = "deadbeef"
    r = Reassembler()
    errored = False
    for frag in frags:
        try:
            r.push(frag)
        except ValueError:
            errored = True
            break
    assert errored, "Expected corruption to be detected"
