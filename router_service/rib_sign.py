"""POC: Signed route updates (RIB diffs).

Signs a RIB diff structure and verifies it using HMAC-SHA256 over canonical JSON.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import Any

from metrics.registry import REGISTRY

_CTR_RIB_SIG_FAIL = REGISTRY.counter("route_sig_fail_total")


def _canonical_bytes(d: dict[str, Any]) -> bytes:
    d = dict(d)
    d.pop("sig", None)
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_rib_diff(diff: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical_bytes(diff), sha256).hexdigest()


def verify_rib_diff(diff: dict[str, Any], key: bytes) -> bool:
    sig = diff.get("sig")
    expected = sign_rib_diff(diff, key)
    ok = isinstance(sig, str) and hmac.compare_digest(sig, expected)
    if not ok:
        _CTR_RIB_SIG_FAIL.inc(1)
    return ok
