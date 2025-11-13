"""POC: OIDC/JWT verification against JWKS (oct/HS256 only).

Supports verifying HS256 tokens using a JWKS document containing `kty: oct`
entries with base64url-encoded key material in `k`. Intended for simple local
testing without external deps.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

from .oidc import verify_jwt_hs256


def _b64url_decode_to_int(data: str) -> int:
    return int.from_bytes(_b64url_decode_to_bytes(data), "big")


def _emsa_pkcs1_v1_5_encode_sha256(message: bytes, klen: int) -> bytes:
    import hashlib

    h = hashlib.sha256(message).digest()
    # DER prefix for SHA-256 DigestInfo (ASN.1):
    # 0x3031300d060960864801650304020105000420 || H
    der_prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    t = der_prefix + h
    # PS = 0xff repeated, length klen - 3 - len(T)
    ps_len = klen - 3 - len(t)
    if ps_len < 8:
        raise ValueError("intended encoded message length too short")
    return b"\x00\x01" + (b"\xff" * ps_len) + b"\x00" + t


def _verify_rs256(token: str, n_b64: str, e_b64: str) -> bool:
    try:
        # Prefer cryptography if available
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa

            header_b64, payload_b64, sig_b64 = token.split(".")
            sig = _b64url_decode_to_bytes(sig_b64)
            n = _b64url_decode_to_int(n_b64)
            e = _b64url_decode_to_int(e_b64)
            pub = rsa.RSAPublicNumbers(e, n).public_key()
            msg = (header_b64 + "." + payload_b64).encode("utf-8")
            pub.verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            # Fallback minimal verification (PKCS#1 v1.5 encode)
            header_b64, payload_b64, sig_b64 = token.split(".")
            sig = _b64url_decode_to_bytes(sig_b64)
            n = _b64url_decode_to_int(n_b64)
            e = _b64url_decode_to_int(e_b64)
            msg = (header_b64 + "." + payload_b64).encode("utf-8")
            klen = (n.bit_length() + 7) // 8
            em = _emsa_pkcs1_v1_5_encode_sha256(msg, klen)
            m_int = pow(int.from_bytes(sig, "big"), e, n)
            m = m_int.to_bytes(klen, "big")
            return m == em
    except Exception:
        return False


def _b64url_decode_to_bytes(data: str) -> bytes:
    pad = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode(data + pad)


def verify_with_jwks(
    token: str, jwks: dict[str, Any], expected_iss: str | None = None, expected_aud: str | None = None
) -> tuple[bool, dict[str, Any] | None]:
    # Minimal kid lookup for HS256 (oct)
    try:
        header_b64 = token.split(".")[0]
        import json

        header = json.loads(_b64url_decode_to_bytes(header_b64))
        kid = header.get("kid")
        # Find matching key
        for jwk in jwks.get("keys", []):
            if kid is not None and jwk.get("kid") != kid:
                continue
            kty = jwk.get("kty")
            if kty == "oct":
                key = _b64url_decode_to_bytes(jwk["k"])  # shared secret bytes
                return verify_jwt_hs256(token, key, expected_iss=expected_iss, expected_aud=expected_aud)
            if kty == "RSA" and jwk.get("alg", "RS256") == "RS256":
                n = jwk.get("n")
                e = jwk.get("e")
                if isinstance(n, str) and isinstance(e, str) and _verify_rs256(token, n, e):
                    # Claims are still in payload; we need to validate iss/aud/exp
                    header_b64, payload_b64, _ = token.split(".")
                    import json

                    payload = json.loads(_b64url_decode_to_bytes(payload_b64))
                    # Reuse claim checks from HS256 path by re-signing not needed; just manual checks
                    now = time.time()
                    if "exp" in payload and now >= float(payload["exp"]):
                        return False, None
                    if expected_iss and payload.get("iss") != expected_iss:
                        return False, None
                    if expected_aud and payload.get("aud") != expected_aud:
                        return False, None
                    return True, payload
        return False, None
    except Exception:
        return False, None


class JWKSCache:
    def __init__(self, ttl_s: int = 300) -> None:
        self.ttl_s = int(ttl_s)
        self._jwks: dict[str, Any] | None = None
        self._last_load: float = 0.0
        self._src: tuple[str, str] | None = None  # (mode, value) where mode in {'json','path'}
        self._last_mtime: float | None = None

    def _load(self, env: dict[str, str]) -> dict[str, Any] | None:
        import json

        text = env.get("JWKS_JSON")
        if text:
            self._src = ("json", text)
            self._last_mtime = None
            return json.loads(text)
        path = env.get("JWKS_PATH")
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = fh.read()
            self._src = ("path", path)
            try:
                self._last_mtime = os.stat(path).st_mtime
            except Exception:
                self._last_mtime = None
            return json.loads(data)
        return None

    def get(self, env: dict[str, str] | None = None) -> dict[str, Any] | None:
        env = env or os.environ  # type: ignore[assignment]
        now = time.time()
        # Force reload if no cache
        need_reload = self._jwks is None or (now - self._last_load) >= self.ttl_s
        if self._src and self._src[0] == "path" and self._src[1] and os.path.exists(self._src[1]):
            try:
                mt = os.stat(self._src[1]).st_mtime
                if self._last_mtime is not None and mt != self._last_mtime:
                    need_reload = True
            except Exception:  # noqa: S110
                pass
        if need_reload:
            jwks = self._load(env)
            if jwks is not None:
                self._jwks = jwks
                self._last_load = now
        return self._jwks


_JWKS_CACHE = JWKSCache()


def get_cached_jwks() -> dict[str, Any] | None:
    ttl = os.getenv("JWKS_TTL_S")
    if ttl:
        try:
            _JWKS_CACHE.ttl_s = int(ttl)
        except Exception:  # noqa: S110
            pass
    return _JWKS_CACHE.get(os.environ)  # type: ignore[arg-type]
