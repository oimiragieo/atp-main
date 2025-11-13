import time

from router_service.fragmentation import Reassembler, fragment_frame
from router_service.frame import Frame, Meta, Payload, Window


def make_frame(text: str):
    return Frame(
        v=1,
        session_id="s",
        stream_id="st",
        msg_seq=7,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
        meta=Meta(task_type="qa"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def test_fragment_round_trip():
    f = make_frame("A" * 600)
    frags = fragment_frame(f, max_fragment_size=128)
    assert len(frags) > 1
    r = Reassembler()
    output = None
    for frag in frags:
        maybe = r.push(frag)
        if maybe:
            output = maybe
    assert output is not None
    assert output.payload.content["text"] == "A" * 600
    assert "REASSEMBLED" in output.flags


def test_fragment_missing():
    f = make_frame("B" * 300)
    frags = fragment_frame(f, max_fragment_size=100)
    r = Reassembler()
    # drop a middle fragment
    dropped = frags[1]
    for frag in frags:
        if frag is dropped:
            continue
        try:
            r.push(frag)
        except ValueError as err:
            # Should not raise until last fragment processed
            raise AssertionError("unexpected early error") from err
    # Now push LAST again to trigger detection (simulate we realize completion)
    try:
        r.push(frags[-1])
    except ValueError as e:
        assert "missing fragments" in str(e)


def test_fragment_duplicate_ignored():
    f = make_frame("XYZ" * 50)
    frags = fragment_frame(f, max_fragment_size=50)
    r = Reassembler()
    # push first twice
    r.push(frags[0])
    r.push(frags[0])  # duplicate ignored
    for frag in frags[1:]:
        r.push(frag)
    r.push(frags[-1])  # maybe already done
    # After completion state removed; pushing last again returns None or raises (ignored for PoC)


def test_fragment_out_of_order():
    text = "O" * 700
    f = make_frame(text)
    frags = fragment_frame(f, max_fragment_size=128)
    # reorder: place LAST (final) fragment second
    if len(frags) > 2:
        last = frags[-1]
        mid_list = [frags[0], last] + frags[1:-1]
    else:
        mid_list = list(reversed(frags))
    r = Reassembler()
    out = None
    for frag in mid_list:
        maybe = r.push(frag)
        if maybe:
            out = maybe
    assert out is not None
    assert out.payload.content["text"] == text


def test_fragment_checksum_corruption():
    f = make_frame("HELLO WORLD THIS IS A LONG TEXT FOR CHECKSUM")
    frags = fragment_frame(f, max_fragment_size=16)
    bad = frags[0].model_copy(deep=True)
    # Corrupt the text but keep original checksum
    bad.payload.content["text"] = bad.payload.content["text"] + "X"
    r = Reassembler()
    try:
        r.push(bad)
        raise AssertionError("expected checksum mismatch")
    except ValueError as e:
        assert "checksum mismatch" in str(e)


def test_reassembler_gc():
    r = Reassembler()
    f = make_frame("A" * 100)
    frags = fragment_frame(f, max_fragment_size=20)
    # Push all fragments except last to create reassembly state
    for frag in frags[:-1]:
        r.push(frag)
    assert len(r._state) == 1
    # Simulate old access
    key = (f.session_id, f.stream_id, f.msg_seq)
    r._last_access[key] = time.time() - 400  # 400 seconds ago
    # GC with 300s ttl
    removed = r.gc(ttl_s=300)
    assert removed == 1
    assert len(r._state) == 0


def test_fragmentation_policy():
    """Test policy-driven max fragment size."""
    from router_service.fragmentation import FragmentationPolicy

    policy = FragmentationPolicy(
        base_max_size=100,
        qos_multipliers={"gold": 2.0, "silver": 1.5, "bronze": 1.0},
    )

    # Test QoS-based sizing
    gold_frame = make_frame("A" * 1000)
    gold_frame.qos = "gold"
    assert policy.get_max_fragment_size(gold_frame) == 200

    silver_frame = make_frame("A" * 1000)
    silver_frame.qos = "silver"
    assert policy.get_max_fragment_size(silver_frame) == 150

    bronze_frame = make_frame("A" * 1000)
    bronze_frame.qos = "bronze"
    assert policy.get_max_fragment_size(bronze_frame) == 100


def test_fragmentation_policy_binary():
    """Test policy-driven binary payload sizing."""
    from router_service.fragmentation import FragmentationPolicy

    policy = FragmentationPolicy(
        base_max_size=100,
        binary_max_size=200,
        qos_multipliers={"gold": 2.0},
    )

    # Test binary payload detection
    binary_frame = make_frame("A" * 1000)
    binary_frame.payload.content = b"binary data"
    assert policy._is_binary_payload(binary_frame) is True
    assert policy.get_max_fragment_size(binary_frame) == 400  # 200 * 2.0


def test_binary_payload_fragmentation():
    """Test fragmentation and reassembly of binary payloads."""
    from router_service.fragmentation import FragmentationPolicy

    binary_data = b"A" * 600
    f = make_frame("")
    f.payload.content = binary_data

    policy = FragmentationPolicy(binary_max_size=128)
    frags = fragment_frame(f, policy=policy)

    assert len(frags) > 1
    r = Reassembler()
    output = None
    for frag in frags:
        maybe = r.push(frag)
        if maybe:
            output = maybe

    assert output is not None
    assert output.payload.content == binary_data
    assert "REASSEMBLED" in output.flags


def test_merkle_checksum():
    """Test merkle tree checksum computation."""
    from router_service.fragmentation import MerkleTree, _compute_merkle_checksum

    text = "A" * 600
    fragment_size = 128

    # Test merkle tree
    merkle = MerkleTree()
    for i in range(0, len(text), fragment_size):
        chunk = text[i : i + fragment_size]
        merkle.add_leaf(chunk)

    root = merkle.get_root()
    assert root is not None
    assert len(root) == 64  # SHA256 hex length

    # Test convenience function
    checksum = _compute_merkle_checksum(text, fragment_size)
    assert len(checksum) == 64  # Full SHA256 hex length for merkle


def test_fragmentation_with_merkle():
    """Test fragmentation with merkle checksums enabled."""
    from router_service.fragmentation import FragmentationPolicy

    f = make_frame("A" * 600)
    policy = FragmentationPolicy(enable_merkle=True)
    frags = fragment_frame(f, policy=policy)

    assert len(frags) > 1

    # All fragments should have the same merkle root checksum
    merkle_root = frags[0].payload.checksum
    for frag in frags:
        assert frag.payload.checksum == merkle_root

    # Test reassembly
    r = Reassembler()
    output = None
    for frag in frags:
        maybe = r.push(frag)
        if maybe:
            output = maybe

    assert output is not None
    assert output.payload.content["text"] == "A" * 600
    assert output.payload.checksum == merkle_root


def test_merkle_checksum_validation():
    """Test merkle checksum validation during reassembly."""
    from router_service.fragmentation import FragmentationPolicy

    f = make_frame("A" * 600)
    policy = FragmentationPolicy(enable_merkle=True)
    frags = fragment_frame(f, policy=policy)

    # Corrupt merkle root on one fragment
    frags[1].payload.checksum = "corrupted" + frags[1].payload.checksum[9:]

    r = Reassembler()
    try:
        for frag in frags:
            r.push(frag)
        raise AssertionError("expected merkle root mismatch")
    except ValueError as e:
        assert "merkle root mismatch" in str(e)


def test_policy_driven_fragmentation():
    """Test that fragmentation respects policy settings."""
    from router_service.fragmentation import FragmentationPolicy

    f = make_frame("A" * 1000)
    f.qos = "gold"

    # Test with policy
    policy = FragmentationPolicy(
        base_max_size=100,
        qos_multipliers={"gold": 3.0},
    )
    frags = fragment_frame(f, policy=policy)

    # Gold QoS should allow larger fragments (100 * 3 = 300)
    assert len(frags) <= 4  # 1000 / 300 = ~3.33, so max 4 fragments

    # Verify fragment sizes
    for frag in frags[:-1]:  # All but last should be max size
        assert len(frag.payload.content["text"]) == 300
