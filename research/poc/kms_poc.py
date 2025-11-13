import hashlib
import hmac
import secrets
from typing import Any


def hkdf(key: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(salt, key, hashlib.sha256).digest()
    t = b""
    okm = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]


def keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


class KMS:
    def __init__(self, master_key: bytes):
        self.master_key = master_key

    def rotate_master(self, new_master_key: bytes):
        self.master_key = new_master_key

    def generate_data_key(self) -> tuple[bytes, bytes]:
        data_key = secrets.token_bytes(32)
        wrap_key = hkdf(self.master_key, salt=b"wrap", info=b"dk")
        wrapped = xor_bytes(data_key, wrap_key)
        return data_key, wrapped

    def unwrap_data_key(self, wrapped: bytes) -> bytes:
        wrap_key = hkdf(self.master_key, salt=b"wrap", info=b"dk")
        return xor_bytes(wrapped, wrap_key)

    def encrypt(self, wrapped_key: bytes, plaintext: bytes, aad: bytes = b"") -> dict[str, Any]:
        dk = self.unwrap_data_key(wrapped_key)
        nonce = secrets.token_bytes(12)
        ks = keystream(hkdf(dk, b"enc", aad), nonce, len(plaintext))
        ct = xor_bytes(plaintext, ks)
        tag = hmac.new(hkdf(dk, b"mac", aad), nonce + ct + aad, hashlib.sha256).digest()
        return {"nonce": nonce.hex(), "ct": ct.hex(), "tag": tag.hex()}

    def decrypt(self, wrapped_key: bytes, blob: dict[str, Any], aad: bytes = b"") -> bytes:
        dk = self.unwrap_data_key(wrapped_key)
        nonce = bytes.fromhex(blob["nonce"])
        ct = bytes.fromhex(blob["ct"])
        tag = bytes.fromhex(blob["tag"])
        expect = hmac.new(hkdf(dk, b"mac", aad), nonce + ct + aad, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, tag):
            raise ValueError("tag mismatch")
        ks = keystream(hkdf(dk, b"enc", aad), nonce, len(ct))
        return xor_bytes(ct, ks)
