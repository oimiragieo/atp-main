"""POC: Redis-backed anti-replay nonce store.

Uses Redis SETNX + EXPIRE to atomically store nonces with TTL and reject
duplicates across processes.
"""

from __future__ import annotations

from typing import Protocol

from metrics.registry import REGISTRY

_CTR_REPLAY = REGISTRY.counter("replay_reject_total")


class _RedisLike(Protocol):
    def setnx(self, key: str, value: str) -> int: ...
    def expire(self, key: str, ttl_s: int) -> int: ...


class RedisNonceStore:
    def __init__(self, client: _RedisLike, ttl_s: int = 60) -> None:
        self.client = client
        self.ttl_s = int(ttl_s)

    def check_and_store(self, nonce: str) -> bool:
        key = f"nonce:{nonce}"
        created = int(self.client.setnx(key, "1"))
        if created == 1:
            self.client.expire(key, self.ttl_s)
            return True
        _CTR_REPLAY.inc(1)
        return False
