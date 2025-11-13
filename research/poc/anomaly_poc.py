"""GAP-212: Seasonal anomaly detection using Holt-Winters exponential smoothing."""

import math
from dataclasses import dataclass


@dataclass
class EWMA:
    alpha: float
    mean: float = 0.0
    var: float = 0.0  # ew variance
    initialized: bool = False

    def update(self, x: float) -> None:
        if not self.initialized:
            self.mean = x
            self.var = 0.0
            self.initialized = True
            return
        prev_mean = self.mean
        self.mean = self.alpha * x + (1 - self.alpha) * self.mean
        # exponential moving variance (approx.)
        self.var = self.alpha * (x - prev_mean) ** 2 + (1 - self.alpha) * self.var

    def sigma(self) -> float:
        return self.var**0.5


@dataclass
class HoltWintersModel:
    """Holt-Winters exponential smoothing model for seasonal time series."""

    alpha: float  # level smoothing parameter
    beta: float  # trend smoothing parameter
    gamma: float  # seasonal smoothing parameter
    season_length: int

    # Model components
    level: float | None = None
    trend: float | None = None
    seasonal: list[float] = None

    def __post_init__(self):
        if self.seasonal is None:
            self.seasonal = [0.0] * self.season_length

    def initialize(self, data: list[float]) -> None:
        """Initialize model parameters from initial data."""
        if len(data) < 2 * self.season_length:
            raise ValueError(f"Need at least {2 * self.season_length} data points for initialization")

        # Simple initialization
        self.level = sum(data[: self.season_length]) / self.season_length
        self.trend = (sum(data[self.season_length : 2 * self.season_length]) - sum(data[: self.season_length])) / (
            self.season_length**2
        )

        # Initialize seasonal components
        for i in range(self.season_length):
            seasonal_sum = 0.0
            for j in range(len(data) // self.season_length):
                if i + j * self.season_length < len(data):
                    seasonal_sum += data[i + j * self.season_length]
            self.seasonal[i] = seasonal_sum / (len(data) // self.season_length + 1) - self.level

    def forecast(self, steps_ahead: int = 1) -> float:
        """Generate forecast for the next time step."""
        if self.level is None or self.trend is None:
            raise ValueError("Model not initialized")

        # Holt-Winters forecast: level + trend * h + seasonal component
        seasonal_idx = (len(self.seasonal) - steps_ahead) % len(self.seasonal)
        return self.level + self.trend * steps_ahead + self.seasonal[seasonal_idx]

    def update(self, observation: float, time_index: int) -> None:
        """Update model with new observation."""
        if self.level is None or self.trend is None:
            return

        seasonal_idx = time_index % self.season_length

        # Store previous values
        prev_level = self.level
        prev_trend = self.trend
        prev_seasonal = self.seasonal[seasonal_idx]

        # Update level
        self.level = self.alpha * (observation - prev_seasonal) + (1 - self.alpha) * (prev_level + prev_trend)

        # Update trend
        self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * prev_trend

        # Update seasonal
        self.seasonal[seasonal_idx] = self.gamma * (observation - self.level) + (1 - self.gamma) * prev_seasonal


class SeasonalAnomalyDetector:
    """Seasonal anomaly detection using Holt-Winters exponential smoothing."""

    def __init__(
        self,
        season_length: int = 24,  # e.g., hourly seasonality for daily patterns
        alpha: float = 0.3,  # level smoothing
        beta: float = 0.1,  # trend smoothing
        gamma: float = 0.3,  # seasonal smoothing
        k_sigma: float = 3.0,
    ):  # anomaly threshold in standard deviations
        self.model = HoltWintersModel(alpha, beta, gamma, season_length)
        self.k_sigma = k_sigma
        self.errors: list[float] = []
        self.initialized = False
        self.time_index = 0

    def initialize(self, historical_data: list[float]) -> None:
        """Initialize the model with historical data."""
        if len(historical_data) < 2 * self.model.season_length:
            raise ValueError(f"Need at least {2 * self.model.season_length} historical points")

        self.model.initialize(historical_data)
        self.initialized = True

        # Calculate initial errors for threshold estimation
        for i, value in enumerate(historical_data):
            forecast = self.model.forecast()
            error = abs(value - forecast)
            self.errors.append(error)
            self.model.update(value, i)

        self.time_index = len(historical_data)

    def detect_anomaly(self, observation: float) -> tuple[bool, float, float]:
        """
        Detect if observation is anomalous.

        Returns:
            (is_anomaly, forecast, error)
        """
        if not self.initialized:
            raise ValueError("Detector not initialized with historical data")

        # Generate forecast
        forecast = self.model.forecast()

        # Calculate error
        error = abs(observation - forecast)

        # Calculate threshold BEFORE adding current error to the list
        if len(self.errors) > 10:
            mean_error = sum(self.errors) / len(self.errors)
            std_error = math.sqrt(sum((e - mean_error) ** 2 for e in self.errors) / len(self.errors))
            threshold = mean_error + self.k_sigma * std_error
        else:
            # Fallback to simple threshold - add some margin to max historical error
            max_error = max(self.errors) if self.errors else 1.0
            threshold = max_error * 1.5  # 50% margin above max historical error

        # Update error history (keep last 1000 errors for threshold calculation)
        self.errors.append(error)
        if len(self.errors) > 1000:
            self.errors.pop(0)

        # Check for anomaly
        is_anomaly = error > threshold

        # Update model with new observation
        self.model.update(observation, self.time_index)
        self.time_index += 1

        return is_anomaly, forecast, error


class AnomalyDetector:
    """Legacy simple anomaly detector for backward compatibility."""

    def __init__(self, alpha: float = 0.2, k_sigma: float = 4.0, ratio: float = 3.0):
        self.ewma = EWMA(alpha=alpha)
        self.k = k_sigma
        self.ratio = ratio

    def ingest(self, value: float) -> bool:
        # returns True if anomaly detected
        if not self.ewma.initialized:
            self.ewma.update(value)
            return False
        mu = self.ewma.mean
        sig = self.ewma.sigma()
        # ratio guard (large jump) and k-sigma guard
        is_ratio = (mu > 0) and (value / max(mu, 1e-9) >= self.ratio)
        is_sigma = (sig > 0) and (value >= mu + self.k * sig)
        self.ewma.update(value)
        return bool(is_ratio or is_sigma)
