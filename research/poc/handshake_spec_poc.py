"""Handshake Spec POC
Combines encoding/compression/feature negotiation with anti-replay protection.
"""

import hashlib
import time
from typing import Any


def negotiate(full_client: dict[str, Any], full_server: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Return (ok, agreed) selecting first mutually supported encoding (by client preference),
    first supported compression (server preference), intersected features, and negotiated qos.
    """
    client_encs: list[str] = full_client.get("encodings", [])
    server_encs: list[str] = full_server.get("encodings", [])
    server_cmp: list[str] = full_server.get("compressions", [])
    client_cmp: list[str] = full_client.get("compressions", [])
    feats_c: list[str] = full_client.get("features", [])
    feats_s: list[str] = full_server.get("features", [])
    qos_c: list[str] = full_client.get("qos", [])
    qos_s: list[str] = full_server.get("qos", [])

    encoding = next((e for e in client_encs if e in server_encs), None)
    if not encoding:
        return False, {}
    # server chooses strongest compression it supports that client also listed (server preference order)
    compression = next((c for c in server_cmp if c in client_cmp), None)
    features = [f for f in feats_c if f in feats_s]
    qos = next((q for q in qos_c if q in qos_s), "standard")
    return True, {"encoding": encoding, "compression": compression, "features": features, "qos": qos}


class AntiReplay:
    def __init__(self, window_s: int = 60):
        self.window = window_s
        self.seen = set()

    def accept(self, nonce: str, ts: int, session: str) -> bool:
        now = int(time.time())
        if abs(now - ts) > self.window:
            return False
        h = hashlib.sha256(f"{nonce}|{ts}|{session}".encode()).hexdigest()
        if h in self.seen:
            return False
        self.seen.add(h)
        return True


def handshake(
    client: dict[str, Any], server: dict[str, Any], nonce: str, ts: int, session: str, anti_replay: AntiReplay
):
    if not anti_replay.accept(nonce, ts, session):
        return False, "replay", {}
    ok, agreed = negotiate(client, server)
    if not ok:
        return False, "negotiation_failed", {}
    return True, "ok", agreed


if __name__ == "__main__":
    ar = AntiReplay(window_s=5)
    client = {
        "encodings": ["cbor", "json"],
        "compressions": ["br", "deflate"],
        "features": ["trace", "budget"],
        "qos": ["gold", "silver"],
    }
    server = {
        "encodings": ["json"],
        "compressions": ["deflate", "gzip"],
        "features": ["trace", "latency"],
        "qos": ["silver", "standard"],
    }
    ts = int(time.time())
    ok, reason, agreed = handshake(client, server, "n1", ts, "s1", ar)
    assert (
        ok
        and reason == "ok"
        and agreed["encoding"] == "json"
        and agreed["compression"] == "deflate"
        and agreed["qos"] == "silver"
    )
    # replay
    ok2, reason2, _ = handshake(client, server, "n1", ts, "s1", ar)
    assert not ok2 and reason2 == "replay"
    print("OK: handshake spec POC passed")
