"""Budget window tracking & preflight (GAP-007 POC).

Provides a minimal estimator interface and a governor that tracks per-session
budgets (tokens and USD micros), supports preflight checks, and records metrics
and tracing attributes. Label-free metrics are simplified for the POC.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from metrics.registry import REGISTRY

from .tracing import get_tracer


@dataclass
class Usage:
    tokens: int = 0
    usd_micros: int = 0


class Estimator(Protocol):
    def estimate(self, payload: dict) -> Usage: ...


@dataclass
class Budget:
    tokens_limit: int
    usd_micros_limit: int
    tokens_used: int = 0
    usd_micros_used: int = 0

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.tokens_limit - self.tokens_used)

    @property
    def usd_micros_remaining(self) -> int:
        return max(0, self.usd_micros_limit - self.usd_micros_used)


class BudgetGovernor:
    def __init__(self, default_tokens: int = 100_000, default_usd_micros: int = 10_000_000) -> None:
        self._budgets: dict[str, Budget] = {}
        # Simplified gauges (last session only for POC)
        self._g_tokens = REGISTRY.gauge("budget_remaining_tokens")
        self._g_usd = REGISTRY.gauge("budget_remaining_usd_micros")
        self._default_tokens = default_tokens
        self._default_usd = default_usd_micros
        # Burn tracking: per-session deque of (ts, usd_micros)
        self._burn: dict[str, deque[tuple[float, int]]] = {}
        self._g_burn = REGISTRY.gauge("budget_burn_rate_usd_per_min")

        # Anomaly detection
        self._anomaly_guard = BudgetAnomalyGuard()

    def _ensure(self, session: str) -> Budget:
        b = self._budgets.get(session)
        if not b:
            b = Budget(tokens_limit=self._default_tokens, usd_micros_limit=self._default_usd)
            self._budgets[session] = b
        return b

    def preflight(self, session: str, usage: Usage) -> bool:
        """Return True if usage fits within remaining budget."""
        b = self._ensure(session)
        ok = usage.tokens <= b.tokens_remaining and usage.usd_micros <= b.usd_micros_remaining
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("budget.check") if tracer else None
        if span_cm:
            span_cm.__enter__()
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("budget.session", session)
                span.set_attribute("budget.tokens_remaining", b.tokens_remaining)
                span.set_attribute("budget.usd_remaining", b.usd_micros_remaining)
                span.set_attribute("budget.tokens_req", usage.tokens)
                span.set_attribute("budget.usd_req", usage.usd_micros)
                span.set_attribute("budget.ok", ok)
            except Exception as _err:  # noqa: S110
                _ = _err
            span_cm.__exit__(None, None, None)
        # Update gauges (last evaluated session)
        self._g_tokens.set(b.tokens_remaining)
        self._g_usd.set(b.usd_micros_remaining)
        return ok

    def consume(self, session: str, usage: Usage) -> None:
        b = self._ensure(session)
        b.tokens_used = min(b.tokens_limit, b.tokens_used + max(0, usage.tokens))
        b.usd_micros_used = min(b.usd_micros_limit, b.usd_micros_used + max(0, usage.usd_micros))
        self._g_tokens.set(b.tokens_remaining)
        self._g_usd.set(b.usd_micros_remaining)
        # record burn event
        if usage.usd_micros > 0:
            dq = self._burn.setdefault(session, deque())
            now = time.time()
            dq.append((now, usage.usd_micros))
            # prune events older than 10 minutes to keep memory bounded
            cutoff = now - 600.0
            while dq and dq[0][0] < cutoff:
                dq.popleft()
            # update last-session gauge for visibility (5-minute window)
            br = self.burn_rate_usd_per_min(session, window_s=300)
            self._g_burn.set(br)

            # Check for budget burn rate spikes
            spike_detected = self._anomaly_guard.check_for_spike(session, br)
            if spike_detected:
                tracer = get_tracer()
                span_cm = tracer.start_as_current_span("budget.spike_detected") if tracer else None
                if span_cm:
                    span_cm.__enter__()
                    try:
                        import opentelemetry.trace as ottrace

                        span = ottrace.get_current_span()
                        span.set_attribute("budget.session", session)
                        span.set_attribute("budget.burn_rate", br)
                        span.set_attribute("budget.spike_detected", True)
                    except Exception as _err:  # noqa: S110
                        _ = _err
                    span_cm.__exit__(None, None, None)

    def snapshot(self) -> dict[str, dict[str, int]]:
        return {
            s: {
                "tokens_used": b.tokens_used,
                "usd_used": b.usd_micros_used,
                "tokens_remaining": b.tokens_remaining,
                "usd_remaining": b.usd_micros_remaining,
            }
            for s, b in self._budgets.items()
        }

    def remaining(self, session: str) -> Usage:
        b = self._ensure(session)
        return Usage(tokens=b.tokens_remaining, usd_micros=b.usd_micros_remaining)

    def burn_rate_usd_per_min(self, session: str, window_s: int = 300) -> float:
        """Return USD per minute burn-rate over the last window_s seconds.

        Computes from recorded consume() calls. Returns 0.0 if no data.
        """
        dq = self._burn.get(session)
        if not dq or not dq:
            return 0.0
        now = time.time()
        cutoff = now - float(window_s)
        # sum usd_micros within window
        total_usd_micros = 0
        # also prune while scanning
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        for ts, usd in dq:
            if ts >= cutoff:
                total_usd_micros += usd
        usd = total_usd_micros / 1_000_000.0
        minutes = max(1e-6, window_s / 60.0)
        return usd / minutes


class BudgetAnomalyGuard:
    """Budget anomaly detection using EWMA + z-score spike detection.

    Monitors budget burn rates and detects anomalous spikes that may indicate
    budget exhaustion or unusual usage patterns.
    """

    def __init__(
        self,
        ewma_alpha: float = 0.1,  # EWMA smoothing factor
        z_threshold: float = 3.0,  # Z-score threshold for spike detection
        min_samples: int = 10,     # Minimum samples before detection starts
        max_samples: int = 100,    # Maximum samples to keep in history
        spike_cooldown_s: float = 300.0,  # Cooldown between spike alerts
    ):
        self.ewma_alpha = ewma_alpha
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self.max_samples = max_samples
        self.spike_cooldown_s = spike_cooldown_s

        # Per-session state
        self._ewma: dict[str, float] = {}  # Current EWMA value
        self._variance: dict[str, float] = {}  # Running variance estimate
        self._samples: dict[str, list[float]] = {}  # Recent samples for std calculation
        self._last_spike: dict[str, float] = {}  # Timestamp of last spike detection

        # Metrics
        self._c_spike_events = REGISTRY.counter("budget_spike_events_total")
        self._g_ewma_value = REGISTRY.gauge("budget_ewma_value")
        self._g_z_score = REGISTRY.gauge("budget_z_score")
        self._g_spike_threshold = REGISTRY.gauge("budget_spike_threshold")

        # Initialize threshold gauge
        self._g_spike_threshold.set(z_threshold)

    def _update_ewma(self, session: str, value: float) -> float:
        """Update and return EWMA for a session."""
        if session not in self._ewma:
            self._ewma[session] = value
            return value

        # EWMA = alpha * current + (1 - alpha) * previous
        ewma = self.ewma_alpha * value + (1 - self.ewma_alpha) * self._ewma[session]
        self._ewma[session] = ewma
        return ewma

    def _update_samples(self, session: str, value: float) -> None:
        """Update sample history for a session."""
        if session not in self._samples:
            self._samples[session] = []

        samples = self._samples[session]
        samples.append(value)

        # Keep only recent samples
        if len(samples) > self.max_samples:
            samples.pop(0)

    def _calculate_z_score(self, session: str, value: float) -> float:
        """Calculate z-score for a value relative to session history."""
        samples = self._samples.get(session, [])
        if len(samples) < self.min_samples:
            return 0.0  # Not enough data

        # Calculate mean and std from samples (excluding current value if it's in samples)
        # Use all samples for calculation
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = variance ** 0.5 if variance > 0 else 1.0

        if std == 0:
            return 0.0

        z_score = (value - mean) / std
        return z_score

    def check_for_spike(self, session: str, burn_rate: float) -> bool:
        """Check if current burn rate represents a spike for the session.

        Returns True if a spike is detected, False otherwise.
        """
        # Update EWMA and samples
        ewma = self._update_ewma(session, burn_rate)
        self._update_samples(session, burn_rate)

        # Update metrics
        self._g_ewma_value.set(ewma)

        # Check if we have enough samples for detection
        samples = self._samples.get(session, [])
        if len(samples) < self.min_samples:
            return False

        # Check cooldown period
        now = time.time()
        last_spike = self._last_spike.get(session, 0)
        if now - last_spike < self.spike_cooldown_s:
            return False

        # Calculate z-score
        z_score = self._calculate_z_score(session, burn_rate)
        self._g_z_score.set(z_score)

        # Check if z-score exceeds threshold
        if z_score > self.z_threshold:
            # Spike detected!
            self._last_spike[session] = now
            self._c_spike_events.inc()
            return True

        return False

    def get_session_stats(self, session: str) -> dict[str, float]:
        """Get anomaly detection statistics for a session."""
        return {
            'ewma': self._ewma.get(session, 0.0),
            'sample_count': len(self._samples.get(session, [])),
            'last_spike_time': self._last_spike.get(session, 0.0),
            'z_threshold': self.z_threshold,
        }

    def reset_session(self, session: str) -> None:
        """Reset anomaly detection state for a session."""
        if session in self._ewma:
            del self._ewma[session]
        if session in self._variance:
            del self._variance[session]
        if session in self._samples:
            del self._samples[session]
        if session in self._last_spike:
            del self._last_spike[session]
