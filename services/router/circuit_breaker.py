"""POC: Unified circuit breakers (GAP-082).

Implements a simple circuit breaker with trip/reset conditions and a manager.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from metrics.registry import REGISTRY

_G_OPEN = REGISTRY.gauge("circuits_open")


class State:
    CLOSED = "closed"
    OPEN = "open"
    HALF = "half_open"


def _now() -> float:
    return time.time()


@dataclass
class CircuitBreaker:
    fail_threshold: int = 5
    reset_timeout_s: float = 30.0
    half_open_successes: int = 2
    _state: str = State.CLOSED
    _failures: int = 0
    _opened_at: float = 0.0
    _half_success: int = 0
    _clock: Callable[[], float] = _now

    def allow_request(self) -> bool:
        if self._state == State.CLOSED:
            return True
        now = self._clock()
        if self._state == State.OPEN and (now - self._opened_at) >= self.reset_timeout_s:
            # probe
            self._state = State.HALF
            self._half_success = 0
            return True
        return self._state == State.HALF

    def record_failure(self) -> None:
        if self._state == State.CLOSED:
            self._failures += 1
            if self._failures >= self.fail_threshold:
                self._trip()
        elif self._state == State.HALF:
            # back to open on any failure
            self._trip()

    def record_success(self) -> None:
        if self._state == State.CLOSED:
            self._failures = max(0, self._failures - 1)
            return
        if self._state == State.HALF:
            self._half_success += 1
            if self._half_success >= self.half_open_successes:
                self._reset()

    def _trip(self) -> None:
        if self._state != State.OPEN:
            self._state = State.OPEN
            self._opened_at = self._clock()
            _G_OPEN.inc(1)

    def _reset(self) -> None:
        if self._state != State.CLOSED:
            self._state = State.CLOSED
            self._failures = 0
            self._half_success = 0
            _G_OPEN.dec(1)
