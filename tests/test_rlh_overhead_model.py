"""Tests for RLH overhead model (GAP-109B)."""

from router_service.rlh import OverheadModel, QoS, RLHProcessor


def test_overhead_model_default_values():
    """Test default overhead model parameters."""
    model = OverheadModel()

    assert model.version == "1"
    assert model.alpha == 0.01
    assert model.beta == 10
    assert model.gamma == 0.02
    assert model.delta == 0.00001


def test_overhead_model_calculate_overhead():
    """Test overhead calculation."""
    model = OverheadModel(alpha=0.01, beta=10, gamma=0.02, delta=0.00001)

    # Test with sample payload
    payload_tokens = 1000
    payload_usd_micros = 10000

    overhead_tokens, overhead_usd_micros = model.calculate_overhead(payload_tokens, payload_usd_micros)

    # Expected: Δtokens = 0.01 * 1000 + 10 = 20
    # Expected: Δusd = 0.02 * 10000 + 0.00001 = 200.00001 -> 200
    assert overhead_tokens == 20
    assert overhead_usd_micros == 200


def test_overhead_model_serialization():
    """Test overhead model serialization."""
    original = OverheadModel(version="2", alpha=0.02, beta=20, gamma=0.03, delta=0.00002)

    # Serialize to dict
    data = original.to_dict()

    # Deserialize from dict
    reconstructed = OverheadModel.from_dict(data)

    assert reconstructed.version == original.version
    assert reconstructed.alpha == original.alpha
    assert reconstructed.beta == original.beta
    assert reconstructed.gamma == original.gamma
    assert reconstructed.delta == original.delta


def test_rlh_processor_with_overhead_model():
    """Test RLH processor with overhead model integration."""
    model = OverheadModel(alpha=0.01, beta=10, gamma=0.02, delta=0.00001)
    processor = RLHProcessor(router_id="router1", overhead_model=model)

    # Verify overhead model is set
    assert processor.overhead_model.alpha == 0.01
    assert processor.overhead_model.beta == 10

    # Test getting overhead model for OPEN messages
    open_data = processor.get_overhead_model()
    expected = {
        "overhead_model": {
            "version": "1",
            "alpha": 0.01,
            "beta": 10,
            "gamma": 0.02,
            "delta": 0.00001,
        }
    }
    assert open_data == expected


def test_rlh_processor_overhead_model_update():
    """Test updating overhead model in RLH processor."""
    processor = RLHProcessor(router_id="router1")

    # Initial model
    assert processor.overhead_model.version == "1"

    # Update to new model
    new_model = OverheadModel(version="2", alpha=0.02, beta=20)
    processor.update_overhead_model(new_model)

    # Verify update
    assert processor.overhead_model.version == "2"
    assert processor.overhead_model.alpha == 0.02
    assert processor.overhead_model.beta == 20


def test_budget_decrement_with_overhead_model():
    """Test that budget decrement uses overhead model."""
    model = OverheadModel(alpha=0.01, beta=10, gamma=0.02, delta=0.00001)
    processor = RLHProcessor(router_id="router1", overhead_model=model)

    # Create a test frame
    frame = processor.encapsulate_frame(
        atp_frame={"type": "request", "content": "test"},
        dst_router_id="87654321-4321-8765-2109-876543210987",
        egress_agent_id=12345,
        qos=QoS.GOLD,
        initial_budget_tokens=1000,
        initial_budget_usd_micros=10000,
    )

    # Forward with payload that should trigger overhead calculation
    payload_tokens = 1000  # Should result in overhead_tokens = 0.01 * 1000 + 10 = 20
    payload_usd_micros = 10000  # Should result in overhead_usd_micros = 0.02 * 10000 + 0.00001 = 200

    result = processor.forward_frame(
        frame,
        next_hop_router_id="abcdef12-3456-7890-abcd-ef1234567890",
        payload_tokens=payload_tokens,
        payload_usd_micros=payload_usd_micros,
    )  # Frame should be forwarded (not None)
    assert result is not None

    # Check that budget was decremented by overhead amounts
    # Initial: tokens=1000, usd=10000
    # After overhead: tokens=1000-20=980, usd=10000-200=9800
    assert result.rlh_header.budget_tokens == 980
    assert result.rlh_header.budget_usd_micros == 9800


def test_budget_exhaustion_with_overhead():
    """Test budget exhaustion when overhead exceeds remaining budget."""
    model = OverheadModel(alpha=0.01, beta=10, gamma=0.02, delta=0.00001)
    processor = RLHProcessor(router_id="router1", overhead_model=model)

    # Create frame with minimal budget
    frame = processor.encapsulate_frame(
        atp_frame={"type": "request", "content": "test"},
        dst_router_id="87654321-4321-8765-2109-876543210987",
        egress_agent_id=12345,
        qos=QoS.GOLD,
        initial_budget_tokens=15,  # Less than overhead (20)
        initial_budget_usd_micros=150,  # Less than overhead (200)
    )

    # Try to forward - should fail due to insufficient budget
    result = processor.forward_frame(
        frame,
        next_hop_router_id="router3",
        payload_tokens=1000,
        payload_usd_micros=10000,
    )

    # Frame should be dropped (None)
    assert result is None


def test_overhead_model_zero_payload():
    """Test overhead calculation with zero payload."""
    model = OverheadModel(alpha=0.01, beta=10, gamma=0.02, delta=0.00001)

    overhead_tokens, overhead_usd_micros = model.calculate_overhead(0, 0)

    # Should still have the constant overhead
    assert overhead_tokens == 10  # beta
    assert overhead_usd_micros == 0  # delta rounds to 0
