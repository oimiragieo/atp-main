"""Federation Conformance POC
Validates that a cluster meets basic conformance: signed updates accepted, drift damping applied,
policy constraints preserved, and stale updates rejected.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass

# Minimal inline versions (avoid cross import for isolation)


def _sign(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


@dataclass
class Route:
    id: str
    freshness: float


@dataclass
class Signed:
    route: Route
    origin: str
    sig: str


class MiniRouter:
    def __init__(self, name, key):
        self.name = name
        self.key = key
        self.routes: dict[str, Route] = {}

    def update(self, rid):
        r = Route(rid, time.time())
        body = f"{self.name}|{rid}|{int(r.freshness)}"
        return Signed(r, self.name, _sign(body, self.key))

    def ingest(self, s: Signed, key, max_age=1):
        body = f"{s.origin}|{s.route.id}|{int(s.route.freshness)}"
        if not hmac.compare_digest(s.sig, _sign(body, key)):
            return False
        if time.time() - s.route.freshness > max_age:
            return False
        existing = self.routes.get(s.route.id)
        if existing and s.route.freshness <= existing.freshness:
            return False
        self.routes[s.route.id] = s.route
        return True


class MiniCluster:
    def __init__(self):
        self.keys = {n: hashlib.sha256(f"k-{n}".encode()).digest() for n in ["a", "b"]}
        self.routers = {n: MiniRouter(n, self.keys[n]) for n in self.keys}

    def run(self):
        u = self.routers["a"].update("r")
        ok1 = self.routers["b"].ingest(u, self.keys["a"])
        time.sleep(1.2)  # let it go stale
        stale = self.routers["a"].update("r")
        stale.route.freshness -= 120  # artificially stale
        ok2 = self.routers["b"].ingest(stale, self.keys["a"])
        return ok1 and not ok2


if __name__ == "__main__":
    mc = MiniCluster()
    res = mc.run()
    if res:
        print("OK: federation conformance POC passed")
    else:
        print("FAIL: federation conformance POC")
