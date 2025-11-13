import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entry:
    key: str
    size: int
    ttl_s: Optional[int]
    ts: float = field(default_factory=lambda: time.time())

    def expired(self, now: float) -> bool:
        return self.ttl_s is not None and (self.ts + self.ttl_s) <= now


@dataclass
class SlidingWindowBucket:
    """Sliding window for tracking requests over time."""
    window_size_s: float
    max_requests: int
    requests: deque = field(default_factory=deque)

    def allow(self, now: float = None) -> bool:
        now = now or time.time()
        # Remove expired requests
        while self.requests and (now - self.requests[0]) > self.window_size_s:
            self.requests.popleft()
        # Check if under limit
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False


@dataclass
class TokenBucket:
    """Token bucket for burst allowance."""
    rate_per_s: float
    burst: int
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.burst
        self.last_refill = time.time()

    def allow(self, cost: int = 1, now: float = None) -> bool:
        now = now or time.time()
        elapsed = max(0.0, now - self.last_refill)
        self.last_refill = now
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate_per_s)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class HybridQuotaManager:
    """Hybrid quota manager combining sliding window and token bucket."""

    def __init__(self, max_items: int, max_bytes: int,
                 window_size_s: float = 60.0, sustained_rps: float = 10.0,
                 burst_rps: float = 50.0):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.window_size_s = window_size_s
        self.sustained_rps = sustained_rps
        self.burst_rps = burst_rps

        # Storage
        self.ns: dict[str, dict[str, Entry]] = {}

        # Rate limiting per namespace
        self.sliding_windows: dict[str, SlidingWindowBucket] = {}
        self.token_buckets: dict[str, TokenBucket] = {}

    def _get_window(self, ns: str) -> SlidingWindowBucket:
        if ns not in self.sliding_windows:
            self.sliding_windows[ns] = SlidingWindowBucket(
                window_size_s=self.window_size_s,
                max_requests=int(self.sustained_rps * self.window_size_s)
            )
        return self.sliding_windows[ns]

    def _get_bucket(self, ns: str) -> TokenBucket:
        if ns not in self.token_buckets:
            self.token_buckets[ns] = TokenBucket(
                rate_per_s=self.sustained_rps,
                burst=int(self.burst_rps * 5)  # 5 second burst allowance
            )
        return self.token_buckets[ns]

    def _stats(self, ns: str) -> tuple[int, int]:
        d = self.ns.get(ns, {})
        return len(d), sum(e.size for e in d.values())

    def _evict(self, ns: str, now: float) -> int:
        d = self.ns.get(ns, {})
        evicted = 0
        # remove expired first
        for k in list(d.keys()):
            if d[k].expired(now):
                del d[k]
                evicted += 1
        # if still over, evict oldest
        while True:
            nitems, nbytes = self._stats(ns)
            if nitems <= self.max_items and nbytes <= self.max_bytes:
                break
            if not d:
                break
            oldest_k = min(d.values(), key=lambda e: e.ts).key
            del d[oldest_k]
            evicted += 1
        return evicted

    def put(self, ns: str, key: str, size: int, ttl_s: Optional[int],
            now: Optional[float] = None) -> tuple[bool, int, str]:
        """
        Put an item with hybrid rate limiting.

        Returns: (success, evicted_count, reason)
        """
        now = now or time.time()

        # Check sliding window (sustained rate)
        window = self._get_window(ns)
        if not window.allow(now):
            return False, 0, "rate_limit_sustained"

        # Check token bucket (burst allowance)
        bucket = self._get_bucket(ns)
        if not bucket.allow(1, now):
            return False, 0, "rate_limit_burst"

        # Put the item
        d = self.ns.setdefault(ns, {})
        d[key] = Entry(key=key, size=size, ttl_s=ttl_s, ts=now)
        ev = self._evict(ns, now)
        nitems, nbytes = self._stats(ns)
        ok = nitems <= self.max_items and nbytes <= self.max_bytes

        if not ok:
            return False, ev, "quota_exceeded"
        return True, ev, "ok"


class QuotaManager:
    """Legacy quota manager for backward compatibility."""

    def __init__(self, max_items: int, max_bytes: int):
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.ns: dict[str, dict[str, Entry]] = {}

    def _stats(self, ns: str) -> tuple[int, int]:
        d = self.ns.get(ns, {})
        return len(d), sum(e.size for e in d.values())

    def _evict(self, ns: str, now: float) -> int:
        d = self.ns.get(ns, {})
        evicted = 0
        # remove expired first
        for k in list(d.keys()):
            if d[k].expired(now):
                del d[k]
                evicted += 1
        # if still over, evict oldest
        while True:
            nitems, nbytes = self._stats(ns)
            if nitems <= self.max_items and nbytes <= self.max_bytes:
                break
            if not d:
                break
            oldest_k = min(d.values(), key=lambda e: e.ts).key
            del d[oldest_k]
            evicted += 1
        return evicted

    def put(self, ns: str, key: str, size: int, ttl_s: Optional[int],
            now: Optional[float] = None) -> tuple[bool, int]:
        now = now or time.time()
        d = self.ns.setdefault(ns, {})
        d[key] = Entry(key=key, size=size, ttl_s=ttl_s, ts=now)
        ev = self._evict(ns, now)
        nitems, nbytes = self._stats(ns)
        ok = nitems <= self.max_items and nbytes <= self.max_bytes
        return ok, ev
