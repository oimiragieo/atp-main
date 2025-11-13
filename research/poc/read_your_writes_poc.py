"""Read-your-writes consistency POC.
Simulates a primary + async replica lag. A session stickiness token forces reads
for a namespace+session to be served from the primary until replica catches up.
"""

from __future__ import annotations

import time
from typing import Any


class PrimaryReplicaCluster:
    def __init__(self, lag_seconds: float = 0.2):
        self.primary: dict[str, dict[str, Any]] = {}
        self.replica: dict[str, dict[str, Any]] = {}
        self.lag = lag_seconds
        self.last_replay: float = time.time()

    def write(self, ns: str, key: str, value: Any):
        self.primary.setdefault(ns, {})[key] = (value, time.time())

    def tick(self):
        now = time.time()
        # apply replication for entries older than lag
        for ns, bucket in self.primary.items():
            rb = self.replica.setdefault(ns, {})
            for k, (v, ts) in bucket.items():
                if now - ts >= self.lag:
                    rb[k] = v

    def read(self, ns: str, key: str, session: str | None = None, force_primary=False):
        if force_primary or session:
            return self.primary.get(ns, {}).get(key, (None,))[0]
        # otherwise serve replica
        return self.replica.get(ns, {}).get(key)


class ReadYourWritesSessionManager:
    def __init__(self, cluster: PrimaryReplicaCluster, session_ttl=1.0):
        self.cluster = cluster
        self.sessions: dict[str, float] = {}
        self.ttl = session_ttl

    def start_session(self) -> str:
        token = f"sess-{time.time()}"
        self.sessions[token] = time.time()
        return token

    def read(self, ns: str, key: str, session: str | None):
        now = time.time()
        if session and (now - self.sessions.get(session, 0)) < self.ttl:
            return self.cluster.read(ns, key, force_primary=True)
        return self.cluster.read(ns, key)


if __name__ == "__main__":
    cl = PrimaryReplicaCluster(lag_seconds=0.3)
    mgr = ReadYourWritesSessionManager(cl)
    sess = mgr.start_session()
    cl.write("n", "a", {"v": 1})
    # immediate read via session must see write (primary)
    assert mgr.read("n", "a", sess)["v"] == 1
    # replica shouldn't yet have it
    assert cl.read("n", "a") is None
    time.sleep(0.35)
    cl.tick()
    # replica now catches up
    assert cl.read("n", "a")["v"] == 1
    # after session ttl expires, non-session read returns replica still
    time.sleep(1.05)
    assert mgr.read("n", "a", sess)["v"] == 1
    print("OK: read-your-writes POC passed")
