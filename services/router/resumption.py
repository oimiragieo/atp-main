"""POC: Resumption tokens & idempotency (GAP-083).

Issues short-lived resumption tokens that allow a client to resume a stream
once, enabling idempotent recovery after transient failures.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

from metrics.registry import REGISTRY

_CTR_RESUMES = REGISTRY.counter("resumes_total")


@dataclass
class _TokenRec:
    session: str
    stream: str
    created: float
    ttl_s: float
    used: bool = False


class ResumptionTokenManager:
    def __init__(self) -> None:
        self._tokens: dict[str, _TokenRec] = {}
        # default TTL from env or 5 minutes
        try:
            self._default_ttl = float(os.getenv("RESUME_TOKEN_TTL_S", "300"))
        except Exception:
            self._default_ttl = 300.0

    def issue(self, session: str, stream: str, ttl_s: float | None = None) -> str:
        token = secrets.token_urlsafe(24)
        rec = _TokenRec(session=session, stream=stream, created=time.time(), ttl_s=float(ttl_s or self._default_ttl))
        self._tokens[token] = rec
        return token

    def resume(self, token: str, session: str, stream: str) -> bool:
        rec = self._tokens.get(token)
        if not rec:
            return False
        now = time.time()
        if rec.used or (now - rec.created) > rec.ttl_s:
            # expire
            self._tokens.pop(token, None)
            return False
        if rec.session != session or rec.stream != stream:
            return False
        rec.used = True
        _CTR_RESUMES.inc(1)
        # best-effort cleanup
        self._tokens.pop(token, None)
        return True

    def purge_expired(self) -> None:
        now = time.time()
        dead = [t for t, rec in self._tokens.items() if (now - rec.created) > rec.ttl_s or rec.used]
        for t in dead:
            self._tokens.pop(t, None)
