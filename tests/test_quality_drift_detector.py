"""Basic tests for Quality Drift Detector (GAP-202)"""

from router_service.quality_drift_detector import QualityDriftDetector


def test_quality_drift_detector_basic():
    """Test basic QualityDriftDetector functionality."""
    detector = QualityDriftDetector(window_size=10)

    # Test initialization
    assert detector.window_size == 10
    assert detector.drift_threshold_sigma == 2.0
    assert len(detector.model_windows) == 0

    # Test adding observations
    detector.add_quality_observation("model1", 0.8)
    assert "model1" in detector.model_windows

    # Test checking drift (should be None with minimal implementation)
    assert detector.check_drift("model1") is None
    assert detector.check_all_models() == []

    # Test getting stats
    assert detector.get_model_stats("model1") is None
    assert detector.get_all_stats() == {}

    # Test reset baseline
    assert not detector.reset_baseline("model1")

    print("Basic tests passed!")


if __name__ == "__main__":
    test_quality_drift_detector_basic()
