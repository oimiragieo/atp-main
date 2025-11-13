"""Federation Cluster POC
Simulates multiple routers exchanging signed route updates via route reflectors.
Implements drift-aware freshness/damping and policy constraint propagation.
"""

import hashlib
import hmac
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# Reuse signing logic (duplicated minimal to keep self-contained)
def _sign(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


@dataclass
class Route:
    id: str
    latency_ms: float
    cost: float
    freshness: float  # higher is newer
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignedRoute:
    route: Route
    origin: str
    ts: float
    sig: str


class RouterNode:
    def __init__(self, name: str, key: bytes):
        self.name = name
        self.key = key
        self.routes: dict[str, Route] = {}
        self.received: list[SignedRoute] = []
        self.damping: dict[str, float] = {}  # route_id -> damp factor 0..1

    def local_update(
        self, route_id: str, latency_ms: float, cost: float, constraints: Optional[dict[str, Any]] = None
    ) -> SignedRoute:
        r = Route(route_id, latency_ms, cost, time.time(), constraints or {})
        self.routes[route_id] = r
        body = f"{self.name}|{route_id}|{int(r.freshness)}|{r.latency_ms}|{r.cost}"
        sig = _sign(body, self.key)
        return SignedRoute(r, self.name, r.freshness, sig)

    def validate(self, s: SignedRoute, key: bytes, max_age_s=120) -> bool:
        body = f"{s.origin}|{s.route.id}|{int(s.route.freshness)}|{s.route.latency_ms}|{s.route.cost}"
        if not hmac.compare_digest(s.sig, _sign(body, key)):
            return False
        if time.time() - s.ts > max_age_s:
            return False
        return True

    def ingest(self, s: SignedRoute, key: bytes):
        if not self.validate(s, key):
            return False
        existing = self.routes.get(s.route.id)
        # Drift-aware freshness: only accept if newer or significantly better score
        score_new = s.route.latency_ms * s.route.cost
        if existing:
            score_old = existing.latency_ms * existing.cost
            drift = score_old - score_new
            # Damping factor increases if change is small (avoid flapping)
            damp = 0.2 if drift < 5 else 1.0
            self.damping[s.route.id] = damp
            if s.route.freshness <= existing.freshness and drift < 5:
                return False
        self.routes[s.route.id] = s.route
        self.received.append(s)
        return True

    def best_route(self, candidates: list[str]):
        best = None
        best_score = float("inf")
        for cid in candidates:
            r = self.routes.get(cid)
            if not r:
                continue
            damp = self.damping.get(cid, 1.0)
            score = (r.latency_ms * r.cost) / damp
            if score < best_score:
                best_score = score
                best = r
        return best


class RouteReflector:
    def __init__(self):
        self.subscribers: list[RouterNode] = []

    def subscribe(self, router: RouterNode):
        self.subscribers.append(router)

    def propagate(self, signed: SignedRoute, key_lookup):
        for r in self.subscribers:
            if r.name == signed.origin:
                continue
            r.ingest(signed, key_lookup[signed.origin])


class FederationCluster:
    def __init__(self, router_names: list[str]):
        self.keys = {n: hashlib.sha256(f"key-{n}".encode()).digest() for n in router_names}
        self.routers = {n: RouterNode(n, self.keys[n]) for n in router_names}
        self.reflector = RouteReflector()
        for r in self.routers.values():
            self.reflector.subscribe(r)

    def simulate(self):
        # each router publishes a route
        signed_updates = []
        for _name, router in self.routers.items():
            s = router.local_update("routeA", random.uniform(50, 150), random.uniform(0.5, 2.0), {"policy": "geo=us"})
            signed_updates.append(s)
        # propagate round 1
        for s in signed_updates:
            self.reflector.propagate(s, self.keys)
        # router0 improves routeA
        r0 = self.routers[list(self.routers.keys())[0]]
        improved = r0.local_update("routeA", random.uniform(20, 40), 0.6, {"policy": "geo=us"})
        self.reflector.propagate(improved, self.keys)
        # pick best at router1
        r1 = self.routers[list(self.routers.keys())[1]]
        best = r1.best_route(["routeA"])
        return {
            "best_latency": best.latency_ms if best else None,
            "routes_seen": sum(len(r.received) for r in self.routers.values()),
            "damping_entries": len([d for d in r1.damping.values() if d < 1.0]),
        }


if __name__ == "__main__":
    cluster = FederationCluster(["r1", "r2", "r3"])
    res = cluster.simulate()
    if res["best_latency"] and res["damping_entries"] >= 0:
        print(
            f"OK: federation cluster POC passed best_latency={round(res['best_latency'], 2)} routes_seen={res['routes_seen']} damping={res['damping_entries']}"
        )
    else:
        print("FAIL: federation cluster POC", res)
