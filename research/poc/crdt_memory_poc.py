"""CRDT Memory POC
Implements a simple Grow-Only Set (G-Set) and Last-Writer-Wins Register (LWW-Register) with causal (vector clock) tags.
Merge operations are commutative and idempotent.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorClock:
    clock: dict[str, int]

    def increment(self, node):
        new = dict(self.clock)
        new[node] = new.get(node, 0) + 1
        return VectorClock(new)

    def dominates(self, other: "VectorClock"):
        ge_all = True
        greater = False
        for k in set(self.clock) | set(other.clock):
            a = self.clock.get(k, 0)
            b = other.clock.get(k, 0)
            if a < b:
                ge_all = False
            if a > b:
                greater = True
        return ge_all and greater


class GSet:
    def __init__(self):
        self.items: set[str] = set()

    def add(self, item):
        self.items.add(item)

    def merge(self, other: "GSet"):
        self.items |= other.items


class LWWRegister:
    def __init__(self):
        self.value = None
        self.vc: VectorClock | None = None

    def set(self, value, vc: VectorClock):
        if self.vc is None or vc.dominates(self.vc):
            self.value = value
            self.vc = vc

    def merge(self, other: "LWWRegister"):
        if other.vc and (self.vc is None or other.vc.dominates(self.vc)):
            self.value = other.value
            self.vc = other.vc


if __name__ == "__main__":
    a = GSet()
    b = GSet()
    a.add("x")
    b.add("y")
    a.merge(b)
    b.merge(a)
    vc0 = VectorClock({"a": 1})
    vc1 = vc0.increment("b")
    r1 = LWWRegister()
    r2 = LWWRegister()
    r1.set("v1", vc0)
    r2.set("v2", vc1)
    r1.merge(r2)
    r2.merge(r1)
    if a.items == {"x", "y"} and r1.value == r2.value == "v2":
        print("OK: crdt memory POC passed")
    else:
        print("FAIL: crdt memory POC", a.items, r1.value, r2.value)
