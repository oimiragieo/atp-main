from router_service.frame import Frame, Meta, Payload, Window


def test_frame_round_trip_basic():
    frame = Frame(
        v=1,
        session_id="s1",
        stream_id="st1",
        msg_seq=1,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=8,
        window=Window(max_parallel=4, max_tokens=5000, max_usd_micros=2_000_000),
        meta=Meta(task_type="qa", tool_permissions=[], data_scope=["public"]),
        payload=Payload(type="agent.result.partial", content={"text": "hi"}),
    )
    d = frame.to_public_dict()
    f2 = Frame(**d)
    assert f2.to_public_dict() == d


def test_frame_invalid_qos():
    import pytest

    with pytest.raises(ValueError):  # expecting ValueError for invalid qos
        Frame(
            v=1,
            session_id="s",
            stream_id="x",
            msg_seq=0,
            frag_seq=0,
            flags=["SYN"],
            qos="diamond",
            ttl=1,
            window=Window(max_parallel=1, max_tokens=10, max_usd_micros=10),
            meta=Meta(),
            payload=Payload(type="x", content={}),
        )
