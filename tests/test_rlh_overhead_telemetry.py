"""Tests for RLH overhead telemetry (GAP-109C)."""

from router_service.rlh import OverheadMeasurement, QoS, RLHProcessor


def test_overhead_measurement_creation():
    """Test OverheadMeasurement dataclass."""
    measurement = OverheadMeasurement(
        timestamp=1234567890.0,
        predicted_tokens=20,
        actual_tokens=18,
        predicted_usd=200,
        actual_usd=220,
    )

    assert measurement.timestamp == 1234567890.0
    assert measurement.predicted_tokens == 20
    assert measurement.actual_tokens == 18
    assert measurement.predicted_usd == 200
    assert measurement.actual_usd == 220


def test_rlh_processor_telemetry_initialization():
    """Test RLH processor initializes telemetry correctly."""
    processor = RLHProcessor(router_id="router1")

    assert hasattr(processor, "overhead_measurements")
    assert hasattr(processor, "overhead_mape_7d")
    assert hasattr(processor, "overhead_p95_factor")
    assert len(processor.overhead_measurements) == 0


def test_record_overhead_measurement():
    """Test recording overhead measurements."""
    processor = RLHProcessor(router_id="router1")

    # Record a measurement
    processor.record_overhead_measurement(
        predicted_tokens=20,
        actual_tokens=18,
        predicted_usd=200,
        actual_usd=220,
    )

    assert len(processor.overhead_measurements) == 1
    measurement = processor.overhead_measurements[0]
    assert measurement.predicted_tokens == 20
    assert measurement.actual_tokens == 18
    assert measurement.predicted_usd == 200
    assert measurement.actual_usd == 220


def test_telemetry_metrics_calculation():
    """Test MAPE and p95 factor calculation."""
    processor = RLHProcessor(router_id="router1")

    # Add multiple measurements
    for i in range(25):
        processor.record_overhead_measurement(
            predicted_tokens=20,
            actual_tokens=18 + i,  # Varying actual values
            predicted_usd=200,
            actual_usd=220 + i * 10,
        )

    # Check that metrics are calculated
    assert processor.overhead_mape_7d.value > 0
    assert processor.overhead_p95_factor.value > 0


def test_get_overhead_telemetry():
    """Test getting overhead telemetry for AGP messages."""
    processor = RLHProcessor(router_id="router1")

    # Add some measurements
    for _ in range(10):
        processor.record_overhead_measurement(
            predicted_tokens=20,
            actual_tokens=20,
            predicted_usd=200,
            actual_usd=200,
        )

    telemetry = processor.get_overhead_telemetry()

    assert "overhead_mape_7d" in telemetry
    assert "overhead_p95_factor" in telemetry
    assert isinstance(telemetry["overhead_mape_7d"], float)
    assert isinstance(telemetry["overhead_p95_factor"], float)


def test_forward_frame_records_measurement():
    """Test that forward_frame records overhead measurements."""
    processor = RLHProcessor(router_id="router1")

    # Create a test frame
    frame = processor.encapsulate_frame(
        atp_frame={"type": "request", "content": "test"},
        dst_router_id="87654321-4321-8765-2109-876543210987",
        egress_agent_id=12345,
        qos=QoS.GOLD,
        initial_budget_tokens=1000,
        initial_budget_usd_micros=10000,
    )

    initial_measurements = len(processor.overhead_measurements)

    # Forward the frame
    result = processor.forward_frame(
        frame,
        next_hop_router_id="abcdef12-3456-7890-abcd-ef1234567890",
        payload_tokens=100,
        payload_usd_micros=1000,
    )

    # Check that a measurement was recorded
    assert len(processor.overhead_measurements) == initial_measurements + 1
    assert result is not None


def test_insufficient_measurements_no_metrics():
    """Test that metrics aren't calculated with insufficient measurements."""
    processor = RLHProcessor(router_id="router1")

    # Record initial metric values
    initial_mape = processor.overhead_mape_7d.value
    initial_p95 = processor.overhead_p95_factor.value

    # Add only a few measurements (less than 10 needed for MAPE)
    for _ in range(5):
        processor.record_overhead_measurement(
            predicted_tokens=20,
            actual_tokens=20,
            predicted_usd=200,
            actual_usd=200,
        )

    # Metrics should not have changed since we don't have enough samples
    assert processor.overhead_mape_7d.value == initial_mape
    assert processor.overhead_p95_factor.value == initial_p95
