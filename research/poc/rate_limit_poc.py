import time
from collections import defaultdict


class TokenBucket:
    def __init__(self, rate_per_s: float, burst: int):
        self.rate = rate_per_s
        self.burst = burst
        self.tokens = burst
        self.ts = time.time()

    def allow(self, cost: int = 1, now: float = None) -> bool:
        now = now or time.time()
        elapsed = max(0.0, now - self.ts)
        self.ts = now
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class RateLimiter:
    def __init__(self, rps: float, burst: int, usd_qps: float, usd_burst: int):
        self.req = defaultdict(lambda: TokenBucket(rps, burst))
        self.usd = defaultdict(lambda: TokenBucket(usd_qps, usd_burst))

    def allow(self, tenant: str, usd_micros: int, now: float = None) -> tuple[bool, str]:
        if not self.req[tenant].allow(1, now):
            return False, "rate_limit"
        # convert usd micros to micro-dollars per second budget
        if not self.usd[tenant].allow(usd_micros, now):
            return False, "cost_limit"
        return True, "ok"
