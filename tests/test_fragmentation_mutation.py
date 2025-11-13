import random

import pytest

from router_service.fragmentation import Reassembler, _compute_checksum, fragment_frame
from router_service.frame import Frame, Meta, Payload, Window

# Helper to build base frame


def make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="s",
        stream_id="st",
        msg_seq=0,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


MUTATIONS = ["drop_one", "shuffle", "dup_one", "corrupt_checksum", "truncate_payload"]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_fragment_mutations_detect_or_reassemble(mutation):
    text = "X" * 600  # ensure multiple fragments
    base = make_frame(text)
    frags = fragment_frame(base, max_fragment_size=100)
    assert len(frags) > 1

    if mutation == "drop_one":
        # remove a middle fragment
        frags = [f for f in frags if f.frag_seq != 1]
    elif mutation == "shuffle":
        random.shuffle(frags)
    elif mutation == "dup_one":
        frags.insert(0, frags[0])
    elif mutation == "corrupt_checksum":
        frags[0].payload.checksum = "deadbeef"
    elif mutation == "truncate_payload":
        # shorten one fragment text
        if isinstance(frags[0].payload.content, dict):
            frags[0].payload.content["text"] = frags[0].payload.content["text"][:1]
            frags[0].payload.checksum = _compute_checksum(frags[0].payload.content["text"])

    r = Reassembler()
    assembled = None
    corruption_detected = False
    for f in frags:
        try:
            out = r.push(f)
        except ValueError:
            corruption_detected = True
            break
        if out:
            assembled = out
    if mutation in ("drop_one", "corrupt_checksum", "truncate_payload"):
        assert corruption_detected or assembled is None
    else:
        assert assembled is not None
        if isinstance(assembled.payload.content, dict):
            assert len(assembled.payload.content["text"]) == len(text)
