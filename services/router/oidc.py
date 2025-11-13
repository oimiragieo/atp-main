"""POC: OIDC/JWT verification (HS256) without external deps.

Provides minimal JWT sign/verify helpers for HS256 and a verifier that enforces
`iss`, `aud`, and `exp` claims. Intended for opt-in auth on ingress.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Any

from metrics.registry import REGISTRY

_CTR_OIDC_INVALID = REGISTRY.counter("oidc_invalid_total")


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64url_decode(data: str) -> bytes:
    # pad to multiple of 4
    pad = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_jwt_hs256(payload: dict[str, Any], secret: bytes) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    msg = h + b"." + p
    sig = _b64url(hmac.new(secret, msg, sha256).digest())
    return msg.decode("utf-8") + "." + sig.decode("utf-8")


def verify_jwt_hs256(
    token: str,
    secret: bytes,
    expected_iss: str | None = None,
    expected_aud: str | None = None,
    now: float | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            _CTR_OIDC_INVALID.inc()
            return False, None
        h_raw, p_raw, s_raw = parts
        msg = (h_raw + "." + p_raw).encode("utf-8")
        expected_sig = _b64url(hmac.new(secret, msg, sha256).digest()).decode("utf-8")
        if not hmac.compare_digest(expected_sig, s_raw):
            _CTR_OIDC_INVALID.inc()
            return False, None
        payload = json.loads(_b64url_decode(p_raw))
        t = float(now or time.time())
        if "exp" in payload and t >= float(payload["exp"]):
            _CTR_OIDC_INVALID.inc()
            return False, None
        if expected_iss and payload.get("iss") != expected_iss:
            _CTR_OIDC_INVALID.inc()
            return False, None
        if expected_aud and payload.get("aud") != expected_aud:
            _CTR_OIDC_INVALID.inc()
            return False, None
        return True, payload
    except Exception:
        _CTR_OIDC_INVALID.inc()
        return False, None
