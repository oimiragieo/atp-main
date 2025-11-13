"""AIMD WINDOW_UPDATE engine (Task 2.x / 5.1 precursor)
Simplified adaptive window with additive increase / multiplicative decrease,
watermarks, jitter dampening, and idle pruning.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Protocol

from metrics.registry import REGISTRY


@dataclass
class WindowState:
    current: int
    max_cap: int
    last_update: float


class _BackendProto(Protocol):  # minimal protocol for optional backend
    def get(self, session: str) -> int: ...
    def update(self, session: str, current: int) -> None: ...


class AIMDController:
    def __init__(
        self,
        base: int = 4,
        max_cap: int = 64,
        add: int = 1,
        mult: float = 0.5,
        target_ms: float = 1500,
        low_water_pct: float = 0.3,
        high_water_pct: float = 0.85,
        jitter_pct: float = 0.05,
        idle_ttl_s: int = 300,
        backend: _BackendProto | None = None,
    ) -> None:
        self._states: dict[str, WindowState] = {}
        self._backend = backend  # optional pluggable state backend (MemoryAIMDBackend / RedisAIMDBackend interface)
        self.base = base
        self.max_cap = max_cap
        self.add = add
        self.mult = mult
        self.target_ms = target_ms
        self.low_water_pct = low_water_pct
        self.high_water_pct = high_water_pct
        self.jitter_pct = jitter_pct
        self.idle_ttl_s = idle_ttl_s
        # metrics
        self._g_cur = REGISTRY.gauge("flow_window_current")
        self._g_cap = REGISTRY.gauge("flow_window_cap")
        self._g_adj = REGISTRY.counter("flow_window_adjustments_total")
        self._g_pruned = REGISTRY.counter("flow_window_pruned_total")
        self._c_ecn = REGISTRY.counter("ecn_reactions_total")
        # Observe distribution of window sizes (powers of two up to max + overflow)
        buckets: list[float] = []
        b = 1
        while b < max_cap:
            buckets.append(b)
            b *= 2
        buckets.append(max_cap)
        self._h_size = REGISTRY.histogram("flow_window_size", buckets)

    def _ensure(self, session: str) -> WindowState:
        st = self._states.get(session)
        if not st:
            if self._backend:
                cur = self._backend.get(session)
                st = WindowState(current=cur, max_cap=self.max_cap, last_update=time.time())
            else:
                st = WindowState(current=self.base, max_cap=self.max_cap, last_update=time.time())
            self._states[session] = st
        return st

    def get(self, session: str) -> int:
        return self._ensure(session).current

    def feedback(self, session: str, latency_ms: float, ok: bool = True) -> None:
        from .tracing import get_tracer  # local import to avoid mandatory otel dependency

        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("aimd.feedback") if tracer else None
        if span_cm:
            span_cm.__enter__()
        st = self._ensure(session)
        jitter = 1.0 + random.uniform(-self.jitter_pct, self.jitter_pct)
        target = self.target_ms * jitter
        before = st.current
        if ok and latency_ms <= target:
            if st.current < int(self.max_cap * self.high_water_pct):
                st.current = min(st.current + self.add, st.max_cap)
        else:
            # Calculate proposed decreased size
            decreased = math.floor(max(st.current, 1) * self.mult)
            if ok:
                # Latency-triggered decrease floor policy: enforce low watermark only for explicitly low pct (<=0.25)
                low_floor = self.base
                if self.low_water_pct <= 0.25:
                    low_floor = max(self.base, math.ceil(self.max_cap * self.low_water_pct))
                st.current = max(low_floor, decreased)
            else:
                # Error-triggered decrease can go to 1
                st.current = max(1, decreased)
        st.last_update = time.time()
        if st.current != before:
            self._g_adj.inc()
        self._g_cur.set(st.current)
        self._g_cap.set(self.max_cap)
        try:
            self._h_size.observe(st.current)
        except Exception as err:  # noqa: S110 -- metrics observation is best-effort
            _ = err
        if self._backend:
            try:
                self._backend.update(session, st.current)
            except Exception as err:  # noqa: S110
                _ = err
        if span_cm:
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                span.set_attribute("aimd.session", session)
                span.set_attribute("aimd.before", before)
                span.set_attribute("aimd.after", st.current)
                span.set_attribute("aimd.latency_ms", round(latency_ms, 2))
                span.set_attribute("aimd.ok", ok)
            except Exception as err:  # noqa: S110
                _ = err
            span_cm.__exit__(None, None, None)

    def snapshot(self) -> dict[str, int]:
        return {k: v.current for k, v in self._states.items()}

    def prune_idle(self, now: float | None = None) -> int:
        now = now or time.time()
        if self._backend:
            # backend manages TTL separately; we still prune local cache
            to_del = [k for k, v in self._states.items() if (now - v.last_update) > self.idle_ttl_s]
            for k in to_del:
                del self._states[k]
            if to_del:
                self._g_pruned.inc(len(to_del))
            return len(to_del)
        else:
            to_del = [k for k, v in self._states.items() if (now - v.last_update) > self.idle_ttl_s]
            for k in to_del:
                del self._states[k]
            if to_del:
                self._g_pruned.inc(len(to_del))
            return len(to_del)

    def ecn_reaction(self, session: str) -> int:
        """Apply ECN reaction by multiplicative decrease.

        Returns the new window size.
        """
        st = self._ensure(session)
        before = st.current
        decreased = math.floor(max(st.current, 1) * self.mult)
        st.current = max(1, decreased)
        st.last_update = time.time()
        if st.current != before:
            self._g_adj.inc()
        self._g_cur.set(st.current)
        self._c_ecn.inc()  # Increment ECN reactions counter
        return st.current


class PIDController:
    """PID controller for adaptive AIMD parameter tuning.

    Uses Proportional-Integral-Derivative control to adjust AIMD additive
    and multiplicative factors based on system performance metrics.
    """

    def __init__(
        self,
        aimd_controller: AIMDController,
        kp: float = 0.1,  # Proportional gain
        ki: float = 0.01,  # Integral gain
        kd: float = 0.05,  # Derivative gain
        target_latency_ms: float = 1500.0,
        target_throughput: float = 100.0,
        target_error_rate: float = 0.01,
        update_interval_s: float = 60.0,  # How often to update parameters
        max_integral: float = 10.0,  # Anti-windup for integral term
    ):
        self.aimd = aimd_controller
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target_latency_ms = target_latency_ms
        self.target_throughput = target_throughput
        self.target_error_rate = target_error_rate
        self.update_interval_s = update_interval_s
        self.max_integral = max_integral

        # PID state for each parameter
        self._integral_add = 0.0
        self._integral_mult = 0.0
        self._prev_error_latency = 0.0
        self._prev_error_throughput = 0.0
        self._prev_error_error_rate = 0.0
        self._last_update_time = time.time()

        # Metrics
        self._g_add_factor = REGISTRY.gauge("aimd_add_factor")
        self._g_mult_factor = REGISTRY.gauge("aimd_mult_factor")
        self._c_pid_updates = REGISTRY.counter("pid_parameter_updates_total")
        self._h_pid_error = REGISTRY.histogram("pid_error_magnitude", [0.1, 0.5, 1.0, 2.0, 5.0, 10.0])

        # Initialize metrics
        self._g_add_factor.set(self.aimd.add)
        self._g_mult_factor.set(self.aimd.mult)

    def _calculate_pid_output(self, error: float, integral: float, prev_error: float, dt: float) -> tuple[float, float]:
        """Calculate PID output for a single error signal."""
        # Proportional term
        proportional = self.kp * error

        # Integral term with anti-windup
        integral += self.ki * error * dt
        integral = max(-self.max_integral, min(self.max_integral, integral))

        # Derivative term
        derivative = 0.0
        if dt > 0:
            derivative = self.kd * (error - prev_error) / dt

        output = proportional + integral + derivative
        return output, integral

    def update_parameters(
        self, current_latency_ms: float, current_throughput: float, current_error_rate: float
    ) -> None:
        """Update AIMD parameters based on current system performance."""
        now = time.time()
        dt = now - self._last_update_time

        # Only update if enough time has passed
        if dt < self.update_interval_s:
            return

        # Calculate errors (negative because we want to reduce latency/error, increase throughput)
        latency_error = self.target_latency_ms - current_latency_ms
        throughput_error = current_throughput - self.target_throughput
        error_rate_error = self.target_error_rate - current_error_rate

        # Calculate PID outputs for each parameter
        # Add factor primarily affected by throughput and error rate
        throughput_output, self._integral_add = self._calculate_pid_output(
            throughput_error, self._integral_add, self._prev_error_throughput, dt
        )
        error_output, _ = self._calculate_pid_output(
            error_rate_error,
            0.0,
            self._prev_error_error_rate,
            dt,  # No integral for error rate
        )

        # Mult factor primarily affected by latency
        latency_output, self._integral_mult = self._calculate_pid_output(
            latency_error, self._integral_mult, self._prev_error_latency, dt
        )

        # Update AIMD parameters with bounds checking
        old_add = self.aimd.add
        old_mult = self.aimd.mult

        # Add factor: increase when throughput is good and error rate is low
        # Decrease when throughput is bad or error rate is high
        add_adjustment = (throughput_output * 0.1) + (error_output * 0.5)  # Both positive when good
        self.aimd.add = max(1, min(10, self.aimd.add + add_adjustment))

        # Mult factor: increase when latency is low (error positive), decrease when latency is high
        mult_adjustment = latency_output * 0.01
        self.aimd.mult = max(0.1, min(0.9, self.aimd.mult + mult_adjustment))

        # Update metrics
        self._g_add_factor.set(self.aimd.add)
        self._g_mult_factor.set(self.aimd.mult)

        # Track parameter changes
        if self.aimd.add != old_add or self.aimd.mult != old_mult:
            self._c_pid_updates.inc()

        # Track error magnitudes for monitoring
        self._h_pid_error.observe(abs(latency_error))
        self._h_pid_error.observe(abs(throughput_error))
        self._h_pid_error.observe(abs(error_rate_error))

        # Store previous errors for derivative calculation
        self._prev_error_latency = latency_error
        self._prev_error_throughput = throughput_error
        self._prev_error_error_rate = error_rate_error
        self._last_update_time = now

    def get_parameters(self) -> dict[str, float]:
        """Get current PID controller parameters and state."""
        return {
            "kp": self.kp,
            "ki": self.ki,
            "kd": self.kd,
            "target_latency_ms": self.target_latency_ms,
            "target_throughput": self.target_throughput,
            "target_error_rate": self.target_error_rate,
            "current_add_factor": self.aimd.add,
            "current_mult_factor": self.aimd.mult,
            "integral_add": self._integral_add,
            "integral_mult": self._integral_mult,
            "last_update_time": self._last_update_time,
        }

    def reset(self) -> None:
        """Reset PID controller state."""
        self._integral_add = 0.0
        self._integral_mult = 0.0
        self._prev_error_latency = 0.0
        self._prev_error_throughput = 0.0
        self._prev_error_error_rate = 0.0
        self._last_update_time = time.time()


GLOBAL_AIMD = AIMDController()
