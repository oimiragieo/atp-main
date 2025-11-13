"""Error-budget aware tail sampler (GAP-365).

Monitors error budget consumption and adjusts trace sampling rates dynamically.
When error budgets are being consumed rapidly, increases sampling to capture
more traces for debugging and root cause analysis.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class ErrorBudgetSample:
    """Represents an error budget measurement sample."""

    timestamp: float
    budget_consumed_percent: float  # 0-100
    error_rate_percent: float  # 0-100


class ErrorBudgetAwareTailSampler:
    """Tail sampler that adjusts sampling rates based on error budget consumption.

    Monitors error budget burn rates and increases sampling when:
    - Error budget consumption is high (>50%)
    - Error rates are elevated
    - Recent trends show increasing error budget consumption

    This helps ensure that when systems are experiencing issues, more traces
    are captured for debugging and root cause analysis.
    """

    def __init__(
        self,
        base_sampling_rate: float = 0.1,  # 10% base sampling
        max_sampling_rate: float = 1.0,   # 100% when critical
        window_size_minutes: int = 10,    # Look back window
        high_consumption_threshold: float = 50.0,  # % budget consumed
        high_error_rate_threshold: float = 5.0,    # % error rate
        adjustment_factor: float = 2.0,  # How much to increase sampling
    ):
        self.base_sampling_rate = base_sampling_rate
        self.max_sampling_rate = max_sampling_rate
        self.window_size_minutes = window_size_minutes
        self.high_consumption_threshold = high_consumption_threshold
        self.high_error_rate_threshold = high_error_rate_threshold
        self.adjustment_factor = adjustment_factor

        # Rolling window of error budget samples
        self.samples: deque[ErrorBudgetSample] = deque()
        self.max_samples = 100  # Keep last 100 samples

        # Metrics
        self._c_sampling_adjustments = REGISTRY.counter("tail_sampler_adjustments_total")
        self._g_current_sampling_rate = REGISTRY.gauge("tail_sampler_current_rate")
        self._g_error_budget_consumption = REGISTRY.gauge("tail_sampler_error_budget_consumption_pct")
        self._g_error_rate = REGISTRY.gauge("tail_sampler_error_rate_pct")
        self._g_trend_indicator = REGISTRY.gauge("tail_sampler_trend_indicator")

        # Initialize metrics
        self._g_current_sampling_rate.set(base_sampling_rate)

    def record_error_budget_measurement(
        self,
        budget_consumed_percent: float,
        error_rate_percent: float
    ) -> None:
        """Record an error budget measurement for sampling rate calculation."""
        now = time.time()
        sample = ErrorBudgetSample(
            timestamp=now,
            budget_consumed_percent=min(100.0, max(0.0, budget_consumed_percent)),
            error_rate_percent=min(100.0, max(0.0, error_rate_percent))
        )

        self.samples.append(sample)

        # Maintain rolling window
        cutoff_time = now - (self.window_size_minutes * 60)
        while self.samples and self.samples[0].timestamp < cutoff_time:
            self.samples.popleft()

        # Limit total samples
        while len(self.samples) > self.max_samples:
            self.samples.popleft()

        # Update metrics
        self._g_error_budget_consumption.set(budget_consumed_percent)
        self._g_error_rate.set(error_rate_percent)

        # Calculate and update sampling rate
        new_rate = self._calculate_sampling_rate()
        self._g_current_sampling_rate.set(new_rate)

        logger.debug(
            f"Error budget sample recorded: consumption={budget_consumed_percent:.1f}%, "
            f"error_rate={error_rate_percent:.1f}%, new_sampling_rate={new_rate:.3f}"
        )

    def get_current_sampling_rate(self) -> float:
        """Get the current sampling rate based on recent error budget trends."""
        return self._calculate_sampling_rate()

    def should_sample(self) -> bool:
        """Determine if the current request/span should be sampled."""
        import random
        rate = self.get_current_sampling_rate()
        return random.random() < rate

    def _calculate_sampling_rate(self) -> float:
        """Calculate sampling rate based on error budget consumption patterns."""
        if not self.samples:
            return self.base_sampling_rate

        # Get recent samples (last 5 minutes for trend analysis)
        recent_cutoff = time.time() - (5 * 60)
        recent_samples = [s for s in self.samples if s.timestamp >= recent_cutoff]

        if not recent_samples:
            recent_samples = list(self.samples)

        # Calculate average consumption and error rate
        avg_consumption = sum(s.budget_consumed_percent for s in recent_samples) / len(recent_samples)
        avg_error_rate = sum(s.error_rate_percent for s in recent_samples) / len(recent_samples)

        # Calculate trend (is consumption increasing?)
        trend_indicator = self._calculate_trend_indicator(recent_samples)
        self._g_trend_indicator.set(trend_indicator)

        # Determine sampling rate adjustment
        rate = self.base_sampling_rate

        # Increase sampling if consumption is high
        if avg_consumption > self.high_consumption_threshold:
            consumption_factor = avg_consumption / 100.0  # 0-1 scale
            rate = min(self.max_sampling_rate, rate * (1 + consumption_factor * self.adjustment_factor))

        # Increase sampling if error rate is high
        if avg_error_rate > self.high_error_rate_threshold:
            error_factor = avg_error_rate / 100.0  # 0-1 scale
            rate = min(self.max_sampling_rate, rate * (1 + error_factor * self.adjustment_factor))

        # Increase sampling if trend is worsening
        if trend_indicator > 0.1:  # Consumption increasing
            trend_factor = min(1.0, trend_indicator)  # Cap at 1.0
            rate = min(self.max_sampling_rate, rate * (1 + trend_factor))

        # Track adjustments
        if rate > self.base_sampling_rate:
            self._c_sampling_adjustments.inc()

        return rate

    def _calculate_trend_indicator(self, samples: list[ErrorBudgetSample]) -> float:
        """Calculate trend indicator (positive = consumption increasing)."""
        if len(samples) < 2:
            return 0.0

        # Simple linear trend calculation
        n = len(samples)
        if n < 2:
            return 0.0

        # Calculate slope of consumption over time
        times = [s.timestamp for s in samples]
        consumptions = [s.budget_consumed_percent for s in samples]

        # Normalize timestamps to start from 0
        t0 = times[0]
        times_norm = [t - t0 for t in times]

        # Calculate slope using simple linear regression
        sum_t = sum(times_norm)
        sum_c = sum(consumptions)
        sum_tc = sum(t * c for t, c in zip(times_norm, consumptions))
        sum_tt = sum(t * t for t in times_norm)

        if sum_tt == 0:
            return 0.0

        slope = (n * sum_tc - sum_t * sum_c) / (n * sum_tt - sum_t * sum_t)

        # Normalize slope by time span and consumption range
        time_span = times_norm[-1] - times_norm[0] if times_norm else 1.0
        if time_span > 0:
            slope = slope / time_span  # Change per second

        # Return positive value for increasing trend
        return max(0.0, slope)

    def get_stats(self) -> dict:
        """Get current sampler statistics."""
        if not self.samples:
            return {
                "samples_count": 0,
                "current_rate": self.base_sampling_rate,
                "avg_consumption": 0.0,
                "avg_error_rate": 0.0,
                "trend_indicator": 0.0,
            }

        recent_samples = list(self.samples)[-10:]  # Last 10 samples
        avg_consumption = sum(s.budget_consumed_percent for s in recent_samples) / len(recent_samples)
        avg_error_rate = sum(s.error_rate_percent for s in recent_samples) / len(recent_samples)
        trend = self._calculate_trend_indicator(recent_samples)

        return {
            "samples_count": len(self.samples),
            "current_rate": self.get_current_sampling_rate(),
            "avg_consumption": avg_consumption,
            "avg_error_rate": avg_error_rate,
            "trend_indicator": trend,
        }


# Global instance for easy access
_tail_sampler: ErrorBudgetAwareTailSampler | None = None


def get_tail_sampler() -> ErrorBudgetAwareTailSampler:
    """Get the global tail sampler instance."""
    global _tail_sampler
    if _tail_sampler is None:
        _tail_sampler = ErrorBudgetAwareTailSampler()
    return _tail_sampler


def init_error_budget_tail_sampler(
    base_sampling_rate: float = 0.1,
    max_sampling_rate: float = 1.0,
    window_size_minutes: int = 10,
) -> ErrorBudgetAwareTailSampler:
    """Initialize the global error-budget aware tail sampler."""
    global _tail_sampler
    _tail_sampler = ErrorBudgetAwareTailSampler(
        base_sampling_rate=base_sampling_rate,
        max_sampling_rate=max_sampling_rate,
        window_size_minutes=window_size_minutes,
    )
    return _tail_sampler


def record_error_budget_for_sampling(
    budget_consumed_percent: float,
    error_rate_percent: float
) -> None:
    """Record error budget measurement for sampling rate adjustment."""
    sampler = get_tail_sampler()
    sampler.record_error_budget_measurement(budget_consumed_percent, error_rate_percent)


def should_sample_trace() -> bool:
    """Determine if current trace should be sampled based on error budget."""
    sampler = get_tail_sampler()
    return sampler.should_sample()
