import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_jwt(claims: dict[str, Any], secret: str, header: dict[str, Any] | None = None) -> str:
    header = header or {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


class JWTError(Exception):
    pass


def verify_jwt(token: str, secret: str, issuer: str | None = None, audience: str | None = None) -> dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as err:
        raise JWTError("invalid token format") from err  # B904
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    got = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, got):
        raise JWTError("signature mismatch")  # from None not needed (not masking another exception)
    payload = json.loads(_b64url_decode(payload_b64))
    now = int(time.time())
    if "exp" in payload and int(payload["exp"]) < now:
        raise JWTError("token expired")
    if issuer is not None and payload.get("iss") != issuer:
        raise JWTError("issuer mismatch")
    if audience is not None:
        aud = payload.get("aud")
        if isinstance(aud, list):
            if audience not in aud:
                raise JWTError("audience mismatch")
        elif aud != audience:
            raise JWTError("audience mismatch")
    return payload
