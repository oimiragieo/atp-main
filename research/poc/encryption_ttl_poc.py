"""Encryption at rest + TTL/retention POC.
Implements simple envelope encryption (XOR placeholder) with per-namespace key and TTL enforcement.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Record:
    ciphertext: bytes
    expires_at: float


class KeyManager:
    def __init__(self):
        self.keys: dict[str, bytes] = {}

    def key_for(self, ns: str) -> bytes:
        self.keys.setdefault(ns, os.urandom(16))
        return self.keys[ns]


def xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class EncryptedStore:
    def __init__(self, key_mgr: KeyManager):
        self.key_mgr = key_mgr
        self.store: dict[str, dict[str, Record]] = {}

    def put(self, ns: str, key: str, value: Any, ttl_s: int):
        raw = repr(value).encode()
        k = self.key_mgr.key_for(ns)
        ct = xor(raw, k)
        self.store.setdefault(ns, {})[key] = Record(ct, time.time() + ttl_s)

    def get(self, ns: str, key: str):
        rec = self.store.get(ns, {}).get(key)
        if not rec:
            return None
        if rec.expires_at < time.time():
            # expired, purge
            del self.store[ns][key]
            return None
        k = self.key_mgr.key_for(ns)
        pt = xor(rec.ciphertext, k)
        from ast import literal_eval  # local import for POC

        try:
            return literal_eval(pt.decode())
        except Exception:
            return None

    def sweep(self):
        now = time.time()
        for _ns, bucket in list(self.store.items()):
            for k, rec in list(bucket.items()):
                if rec.expires_at < now:
                    del bucket[k]


if __name__ == "__main__":
    km = KeyManager()
    es = EncryptedStore(km)
    es.put("ns", "a", {"x": 1}, ttl_s=1)
    assert es.get("ns", "a")["x"] == 1
    time.sleep(1.1)
    assert es.get("ns", "a") is None
    es.put("ns", "b", {"y": 2}, ttl_s=5)
    v = es.get("ns", "b")
    assert v == {"y": 2}
    print("OK: encryption+ttl POC passed")
