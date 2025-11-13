"""POC: HMAC frame signatures (GAP-040).

Provides HMAC-SHA256 signing and verification for Frame payloads using the
existing `sig` field in router_service.frame.Frame. Uses canonical JSON of the
frame dict (excluding `sig`) with sorted keys.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import Any

from metrics.registry import REGISTRY

from .key_manager import KeyManager

_CTR_SIG_FAIL = REGISTRY.counter("frame_signature_fail_total")


def _canonical_bytes(d: dict[str, Any]) -> bytes:
    # Exclude signature and produce sorted, compact JSON
    if "sig" in d:
        d = dict(d)
        d.pop("sig", None)
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_frame_dict(frame_dict: dict[str, Any], key: bytes) -> str:
    data = _canonical_bytes(frame_dict)
    mac = hmac.new(key, data, sha256).hexdigest()
    return mac


def verify_frame_dict(frame_dict: dict[str, Any], key: bytes) -> bool:
    sig = frame_dict.get("sig")
    expected = sign_frame_dict(frame_dict, key)
    ok = isinstance(sig, str) and hmac.compare_digest(sig, expected)
    if not ok:
        _CTR_SIG_FAIL.inc(1)
    return ok


def sign_frame_with_kid(frame_dict: dict[str, Any], km: KeyManager, kid: str | None = None) -> str:
    """Sign frame dict using a KeyManager and set `kid` in dict.

    Returns signature string; does not mutate input dict beyond setting `kid` if provided.
    """
    if kid is None:
        kid = km.current_kid()
    # Ensure kid is present for canonical bytes computation
    frame_dict = dict(frame_dict)
    frame_dict["kid"] = kid
    key = km.get_key(kid)
    return sign_frame_dict(frame_dict, key)


def verify_frame_with_km(frame_dict: dict[str, Any], km: KeyManager) -> bool:
    kid_val = frame_dict.get("kid")
    if not isinstance(kid_val, str) or not kid_val:
        return False
    try:
        key = km.get_key(kid_val)
    except KeyError:
        _CTR_SIG_FAIL.inc(1)
        return False
    return verify_frame_dict(frame_dict, key)
