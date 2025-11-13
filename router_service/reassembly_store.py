"""POC: External reassembly buffer store (GAP-081).

Provides a simple in-memory external store API to persist fragment parts across
Reassembler instances. This simulates an external backend interface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from metrics.registry import REGISTRY

Key = tuple[str, str, int]  # (session_id, stream_id, msg_seq)
_CTR_STORE_OPS = REGISTRY.counter("buffer_store_ops")


@dataclass
class _Entry:
    parts: dict[int, str] = field(default_factory=dict)
    last_seq: int | None = None
    updated: float = field(default_factory=time.time)
    is_binary: bool = False


class ExternalReassemblyStore:
    """In-memory external buffer store with TTL pruning."""

    def __init__(self, ttl_s: float = 600.0) -> None:
        self._m: dict[Key, _Entry] = {}
        self._ttl = float(ttl_s)

    def push_part(
        self,
        session_id: str,
        stream_id: str,
        msg_seq: int,
        frag_seq: int,
        data: str,
        is_last: bool,
        is_binary: bool = False,
    ) -> tuple[bool, str | None]:
        """Store a fragment. Return (complete, full_data_if_complete)."""
        _CTR_STORE_OPS.inc(1)
        key: Key = (session_id, stream_id, msg_seq)
        ent = self._m.setdefault(key, _Entry())
        ent.parts[frag_seq] = data
        if is_binary:
            ent.is_binary = True
        if is_last:
            ent.last_seq = max(ent.last_seq or 0, frag_seq)
        ent.updated = time.time()
        self._prune()
        if ent.last_seq is None:
            return False, None
        last = ent.last_seq
        for i in range(last + 1):
            if i not in ent.parts:
                return False, None
        # Complete
        full = "".join(ent.parts[i] for i in range(last + 1))
        self._m.pop(key, None)
        return True, full

    def clear(self, session_id: str, stream_id: str, msg_seq: int) -> None:
        key: Key = (session_id, stream_id, msg_seq)
        self._m.pop(key, None)
        _CTR_STORE_OPS.inc(1)

    def _prune(self) -> None:
        now = time.time()
        rm = [k for k, e in self._m.items() if now - e.updated > self._ttl]
        for k in rm:
            self._m.pop(k, None)
