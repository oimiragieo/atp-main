"""Abstract state backend for AIMD + FairScheduler to enable multi-instance scaling.

Initial implementation: in-memory (existing) and a Redis backend (optional runtime dependency).
Redis usage kept simple: hash maps and sorted sets avoided; stick to basic key ops for portability.
"""

from __future__ import annotations

import time
from typing import Any, Protocol


class SchedulerStateBackend(Protocol):
    # Fair served counts and weights
    def get_weight(self, session: str) -> float: ...
    def set_weight(self, session: str, weight: float) -> None: ...
    def inc_served(self, session: str) -> int: ...
    def snapshot_weights(self) -> dict[str, float]: ...
    def snapshot_served(self) -> dict[str, int]: ...


class AIMDStateBackend(Protocol):
    def get(self, session: str) -> int: ...
    def update(self, session: str, current: int) -> None: ...
    def prune_idle(self, ttl: int) -> int: ...


class MemorySchedulerBackend:
    def __init__(self) -> None:
        self.weights: dict[str, float] = {}
        self.served: dict[str, int] = {}

    def get_weight(self, session: str) -> float:
        return self.weights.get(session, 1.0)

    def set_weight(self, session: str, weight: float) -> None:
        self.weights[session] = weight

    def inc_served(self, session: str) -> int:
        v = self.served.get(session, 0) + 1
        self.served[session] = v
        return v

    def snapshot_weights(self) -> dict[str, float]:
        return dict(self.weights)

    def snapshot_served(self) -> dict[str, int]:
        return dict(self.served)


class MemoryAIMDBackend:
    def __init__(self) -> None:
        self.state: dict[str, tuple[int, float]] = {}

    def get(self, session: str) -> int:
        return self.state.get(session, (4, time.time()))[0]

    def update(self, session: str, current: int) -> None:
        self.state[session] = (current, time.time())

    def prune_idle(self, ttl: int) -> int:
        now = time.time()
        keys = [k for k, (_v, t) in self.state.items() if now - t > ttl]
        for k in keys:
            del self.state[k]
        return len(keys)


try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class RedisSchedulerBackend:
    def __init__(self, url: str) -> None:
        if not redis:  # pragma: no cover - guarded import
            raise RuntimeError("redis package not installed")
        # Initialize Redis connection and key namespaces
        self.r = redis.from_url(url, decode_responses=True)
        self.key_weights = "fair:weights"
        self.key_served = "fair:served"

    def get_weight(self, session: str) -> float:
        v = self.r.hget(self.key_weights, session)
        return float(v) if v else 1.0

    def set_weight(self, session: str, weight: float) -> None:
        self.r.hset(self.key_weights, session, weight)

    def inc_served(self, session: str) -> int:
        return int(self.r.hincrby(self.key_served, session, 1))

    def snapshot_weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.r.hgetall(self.key_weights).items()}

    def snapshot_served(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.r.hgetall(self.key_served).items()}


class RedisAIMDBackend:
    def __init__(self, url: str) -> None:
        if not redis:  # pragma: no cover
            raise RuntimeError("redis package not installed")
        # Initialize Redis connection and key prefix
        self.r = redis.from_url(url, decode_responses=True)
        self.key_prefix = "aimd:"

    def get(self, session: str) -> int:
        v = self.r.get(self.key_prefix + session)
        return int(v) if v else 4

    def update(self, session: str, current: int) -> None:
        self.r.set(self.key_prefix + session, current, ex=3600)

    def prune_idle(self, ttl: int) -> int:  # noqa: ARG002 (ttl reserved for future)
        return 0


def build_backends(settings: Any) -> tuple[SchedulerStateBackend, AIMDStateBackend]:
    if getattr(settings, "state_backend", None) == "redis":
        return RedisSchedulerBackend(settings.redis_url), RedisAIMDBackend(settings.redis_url)
    return MemorySchedulerBackend(), MemoryAIMDBackend()
