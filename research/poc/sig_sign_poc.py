import hashlib
import hmac


def sign_bytes(data: bytes, key: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def verify_bytes(data: bytes, sig: bytes, key: bytes) -> bool:
    return hmac.compare_digest(sign_bytes(data, key), sig)
