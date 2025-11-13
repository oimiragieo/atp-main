"""POC: Anti-replay nonce store (GAP-041).

Provides an in-memory nonce store with TTL to reject duplicate messages.
Metrics: replay_reject_total increments on duplicate.
"""

from __future__ import annotations

import time
from collections import deque

from metrics.registry import REGISTRY
from router_service.event_emitter import RejectionReason, emit_rejection_event

_CTR_REPLAY = REGISTRY.counter("replay_reject_total")


class NonceStore:
    def __init__(self, ttl_s: float = 60.0, cap: int = 10000) -> None:
        self.ttl_s = float(ttl_s)
        self.cap = int(cap)
        self._slots: dict[str, float] = {}
        self._queue: deque[str] = deque()

    def _prune(self, now: float) -> None:
        # Drop expired or over-cap oldest entries
        while self._queue and (now - self._slots.get(self._queue[0], now)) > self.ttl_s:
            k = self._queue.popleft()
            self._slots.pop(k, None)
        while len(self._queue) > self.cap:
            k = self._queue.popleft()
            self._slots.pop(k, None)

    def check_and_store(self, nonce: str, now: float | None = None, request_id: str | None = None) -> bool:
        t = float(now or time.time())
        self._prune(t)
        if nonce in self._slots:
            _CTR_REPLAY.inc(1)
            emit_rejection_event(
                RejectionReason.REPLAY_DETECTED,
                "replay_guard",
                request_id,
                {"nonce": nonce, "detected_at": t}
            )
            return False
        self._slots[nonce] = t
        self._queue.append(nonce)
        self._prune(t)
        return True
