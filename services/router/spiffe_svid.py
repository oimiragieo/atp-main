"""POC: SPIFFE/SPIRE SVID stub (GAP-046).

Provides simple SVID dataclass and a stubbed client to fetch/rotate SVIDs and
validate expiration. Intended as a seam to integrate with real SPIRE agents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from metrics.registry import REGISTRY

_CTR_SVID_ROTATE = REGISTRY.counter("svid_rotation_total")


@dataclass
class SVID:
    spiffe_id: str
    cert_pem: str
    key_pem: str
    expires_at: float  # epoch seconds

    def is_valid(self, now: float | None = None) -> bool:
        t = float(now or time.time())
        return t < self.expires_at


class SpireClientStub:
    def __init__(self, workload_id: str) -> None:
        self.workload_id = workload_id
        self._svid: SVID | None = None

    def fetch_svid(self, ttl_s: int = 300) -> SVID:
        # In a real impl, call SPIRE Workload API to get an SVID; here, synthesize
        now = time.time()
        self._svid = SVID(
            spiffe_id=f"spiffe://example.org/{self.workload_id}",
            cert_pem="-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
            key_pem="-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----",
            expires_at=now + float(ttl_s),
        )
        return self._svid

    def rotate_if_needed(self, min_ttl_s: int = 60) -> SVID:
        now = time.time()
        if not self._svid or (self._svid.expires_at - now) <= float(min_ttl_s):
            _CTR_SVID_ROTATE.inc(1)
            return self.fetch_svid(ttl_s=max(min_ttl_s * 2, 300))
        return self._svid
