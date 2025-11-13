"""GAP-212: Seasonal anomaly detection service for ATP router."""

import threading
import time
from typing import Optional

from metrics.registry import REGISTRY
from tools.anomaly_poc import SeasonalAnomalyDetector


class SeasonalAnomalyDetectionService:
    """Service for detecting seasonal anomalies in ATP router metrics."""

    def __init__(
        self,
        season_length: int = 60,  # 60 minutes for hourly patterns
        alpha: float = 0.3,
        beta: float = 0.1,
        gamma: float = 0.3,
        k_sigma: float = 3.0,
    ):
        self.detector = SeasonalAnomalyDetector(
            season_length=season_length, alpha=alpha, beta=beta, gamma=gamma, k_sigma=k_sigma
        )

        # Metrics
        self.anomalies_detected_total = REGISTRY.counter("anomalies_detected_total")
        self.anomaly_score_gauge = REGISTRY.gauge("anomaly_detection_score")
        self.anomaly_threshold_gauge = REGISTRY.gauge("anomaly_detection_threshold")

        # State
        self.initialized = False
        self.metric_history: list[float] = []
        self.max_history_size = season_length * 24  # Keep 24 seasons of history
        self._lock = threading.Lock()

    def initialize_with_historical_data(self, historical_values: list[float]) -> bool:
        """
        Initialize the detector with historical metric values.

        Args:
            historical_values: List of historical metric values

        Returns:
            True if initialization successful, False otherwise
        """
        with self._lock:
            try:
                if len(historical_values) < 2 * self.detector.model.season_length:
                    return False

                self.detector.initialize(historical_values)
                self.metric_history = historical_values[-self.max_history_size :]
                self.initialized = True
                return True
            except Exception:
                return False

    def check_metric_anomaly(self, metric_value: float, metric_name: str = "unknown") -> dict:
        """
        Check if a metric value is anomalous.

        Args:
            metric_value: Current metric value to check
            metric_name: Name of the metric for logging

        Returns:
            Dictionary with anomaly detection results
        """
        with self._lock:
            if not self.initialized:
                return {"is_anomaly": False, "forecast": None, "error": None, "threshold": None, "initialized": False}

            # Update metric history
            self.metric_history.append(metric_value)
            if len(self.metric_history) > self.max_history_size:
                self.metric_history.pop(0)

            # Detect anomaly
            is_anomaly, forecast, error = self.detector.detect_anomaly(metric_value)

            # Calculate dynamic threshold
            if len(self.detector.errors) > 10:
                mean_error = sum(self.detector.errors) / len(self.detector.errors)
                import math

                std_error = math.sqrt(
                    sum((e - mean_error) ** 2 for e in self.detector.errors) / len(self.detector.errors)
                )
                threshold = mean_error + self.detector.k_sigma * std_error
            else:
                threshold = max(self.detector.errors) if self.detector.errors else 1.0

            # Update metrics
            if is_anomaly:
                self.anomalies_detected_total.inc()

            self.anomaly_score_gauge.set(error)
            self.anomaly_threshold_gauge.set(threshold)

            return {
                "is_anomaly": is_anomaly,
                "forecast": forecast,
                "error": error,
                "threshold": threshold,
                "metric_name": metric_name,
                "timestamp": time.time(),
                "initialized": True,
            }

    def get_status(self) -> dict:
        """Get current status of the anomaly detection service."""
        with self._lock:
            return {
                "initialized": self.initialized,
                "season_length": self.detector.model.season_length,
                "history_size": len(self.metric_history),
                "max_history_size": self.max_history_size,
                "anomalies_detected": self.anomalies_detected_total.value,
                "current_threshold": self.anomaly_threshold_gauge.value,
                "current_score": self.anomaly_score_gauge.value,
            }

    def reset(self) -> None:
        """Reset the anomaly detection service."""
        with self._lock:
            self.initialized = False
            self.metric_history.clear()
            self.detector = SeasonalAnomalyDetector(
                season_length=self.detector.model.season_length,
                alpha=self.detector.model.alpha,
                beta=self.detector.model.beta,
                gamma=self.detector.model.gamma,
                k_sigma=self.detector.k_sigma,
            )


# Global service instance
_seasonal_anomaly_service: Optional[SeasonalAnomalyDetectionService] = None
_service_lock = threading.Lock()


def get_seasonal_anomaly_service() -> SeasonalAnomalyDetectionService:
    """Get or create the global seasonal anomaly detection service."""
    global _seasonal_anomaly_service

    if _seasonal_anomaly_service is None:
        with _service_lock:
            if _seasonal_anomaly_service is None:
                _seasonal_anomaly_service = SeasonalAnomalyDetectionService()

    return _seasonal_anomaly_service


def initialize_seasonal_anomaly_detection(historical_data: list[float]) -> bool:
    """
    Initialize the seasonal anomaly detection service with historical data.

    Args:
        historical_data: List of historical metric values

    Returns:
        True if initialization successful
    """
    service = get_seasonal_anomaly_service()
    return service.initialize_with_historical_data(historical_data)


def check_metric_anomaly(metric_value: float, metric_name: str = "unknown") -> dict:
    """
    Check if a metric value is anomalous using seasonal analysis.

    Args:
        metric_value: Current metric value
        metric_name: Name of the metric

    Returns:
        Anomaly detection results
    """
    service = get_seasonal_anomaly_service()
    return service.check_metric_anomaly(metric_value, metric_name)
