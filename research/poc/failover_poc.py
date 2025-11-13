from dataclasses import dataclass
from typing import Optional


@dataclass
class RegionState:
    name: str
    healthy: bool = True
    latency_ms: int = 50


class RegionRouter:
    def __init__(self, regions: list[str], prefer_primary: bool = True):
        if not regions:
            raise ValueError("need at least one region")
        self.regions: dict[str, RegionState] = {r: RegionState(r) for r in regions}
        self.primary = regions[0]
        self.prefer_primary = prefer_primary
        self._sticky: dict[str, str] = {}  # session_id -> region
        self.replica_log: list[tuple[str, str, dict]] = []  # (src_region, dst_region, op)

    def set_health(self, region: str, healthy: bool, latency_ms: Optional[int] = None):
        s = self.regions[region]
        s.healthy = healthy
        if latency_ms is not None:
            s.latency_ms = latency_ms

    def choose_region(self, session_id: str) -> str:
        # sticky session if region still healthy
        cur = self._sticky.get(session_id)
        if cur and self.regions[cur].healthy:
            return cur
        # prefer primary if healthy
        if self.regions[self.primary].healthy:
            self._sticky[session_id] = self.primary
            return self.primary
        # else pick first healthy by lowest latency
        candidates = [s for s in self.regions.values() if s.healthy]
        if not candidates:
            raise RuntimeError("no healthy regions")
        pick = sorted(candidates, key=lambda s: s.latency_ms)[0].name
        self._sticky[session_id] = pick
        return pick

    def replicate(self, src: str, dst: str, op: dict):
        # append to replica log; in real system this would stream via CDC
        self.replica_log.append((src, dst, op))
