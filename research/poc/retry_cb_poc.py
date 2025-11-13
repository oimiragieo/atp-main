import time
from collections.abc import Callable
from dataclasses import dataclass


class IdempotencyStore:
    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        v = self._store.get(key)
        return v[0] if v else None

    def set(self, key: str, result: str) -> None:
        self._store[key] = (result, time.time())


@dataclass
class RetryPolicy:
    retries: int = 3
    backoff_ms: int = 50
    multiplier: float = 2.0

    def schedule(self):
        delay = self.backoff_ms / 1000.0
        for _ in range(self.retries):
            yield delay
            delay *= self.multiplier


class CircuitBreaker:
    def __init__(self, failures_to_open: int = 3, half_open_after_s: float = 1.0):
        self.fail_to_open = failures_to_open
        self.half_open_after = half_open_after_s
        self.state = "CLOSED"
        self.failures = 0
        self.open_since = 0.0

    def allow(self, now: float = None) -> bool:
        now = now or time.time()
        if self.state == "OPEN":
            if now - self.open_since >= self.half_open_after:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def on_success(self):
        self.state = "CLOSED"
        self.failures = 0

    def on_failure(self):
        self.failures += 1
        if self.failures >= self.fail_to_open:
            self.state = "OPEN"
            self.open_since = time.time()


def call_with_retry_and_cb(
    op: Callable[[], str], idem_key: str, idem: IdempotencyStore, rp: RetryPolicy, cb: CircuitBreaker
) -> tuple[bool, str | None, str]:
    # returns (ok, result, status)
    saved = idem.get(idem_key)
    if saved is not None:
        return True, saved, "idempotent-hit"
    if not cb.allow():
        return False, None, "circuit-open"
    # first try + retries
    try:
        res = op()
        idem.set(idem_key, res)
        cb.on_success()
        return True, res, "ok"
    except Exception:
        cb.on_failure()
        for delay in rp.schedule():
            if not cb.allow():
                return False, None, "circuit-open"
            time.sleep(delay)
            try:
                res = op()
                idem.set(idem_key, res)
                cb.on_success()
                return True, res, "ok"
            except Exception:
                cb.on_failure()
                continue
        return False, None, "exhausted"
