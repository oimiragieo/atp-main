import hashlib
import hmac
import json
from typing import Any


def _encode(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def append_event(path: str, event: dict[str, Any], secret: bytes, prev_hash_hex: str | None = None) -> str:
    """Append an event with HMAC chain. Returns new hash hex.

    Format per line: {"event":{...},"prev":"<hex>","hmac":"<hex>","hash":"<hex>"}
    'hash' is SHA256(prev||event_json). 'hmac' is HMAC(secret, hash).
    """
    prev = bytes.fromhex(prev_hash_hex) if prev_hash_hex else b""
    payload = _encode(event)
    link = hashlib.sha256(prev + payload).digest()
    tag = hmac.new(secret, link, hashlib.sha256).hexdigest()
    rec = {"event": event, "prev": prev_hash_hex, "hmac": tag, "hash": link.hex()}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return link.hex()


def verify_log(path: str, secret: bytes) -> bool:
    """Verify the entire log file; returns True if intact."""
    prev = b""
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            event = rec.get("event")
            prev_hex = rec.get("prev")
            expect_hash = rec.get("hash")
            expect_hmac = rec.get("hmac")
            # check prev link matches
            if (prev_hex or None) != (prev.hex() or None):
                return False
            payload = _encode(event)
            link = hashlib.sha256(prev + payload).hexdigest()
            if link != expect_hash:
                return False
            tag = hmac.new(secret, bytes.fromhex(link), hashlib.sha256).hexdigest()
            if tag != expect_hmac:
                return False
            prev = bytes.fromhex(link)
    return True
