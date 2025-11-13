import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any


def sign(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class RouteUpdate:
    origin: str
    ts: float
    payload: dict[str, Any]
    sig: str


def make_update(origin: str, payload: dict[str, Any], key: bytes) -> RouteUpdate:
    ts = time.time()
    body = f"{origin}|{int(ts)}|{payload}"
    return RouteUpdate(origin, ts, payload, sign(body, key))


def verify_update(update: RouteUpdate, key: bytes, max_age_s: int = 60) -> bool:
    body = f"{update.origin}|{int(update.ts)}|{update.payload}"
    if not hmac.compare_digest(update.sig, sign(body, key)):
        return False
    if (time.time() - update.ts) > max_age_s:
        return False
    return True
