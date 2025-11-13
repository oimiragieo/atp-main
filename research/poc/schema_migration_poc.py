"""Schema/migration tooling & lineage POC.
Implements a tiny migration registry that can apply ordered migrations from a current
version to a target version while recording lineage (audit trail) of transformations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Migration:
    from_version: int
    to_version: int
    apply: Callable[[dict[str, Any]], dict[str, Any]]


class MigrationRegistry:
    def __init__(self):
        self.migrations: dict[int, Migration] = {}
        self.lineage: list[dict[str, Any]] = []

    def register(self, mig: Migration):
        self.migrations[mig.from_version] = mig

    def upgrade(self, data: dict[str, Any], current: int, target: int) -> dict[str, Any]:
        while current < target:
            mig = self.migrations.get(current)
            if not mig or mig.to_version != current + 1:
                raise RuntimeError(f"No migration path from v{current} to v{current + 1}")
            before = data.copy()
            data = mig.apply(data)
            self.lineage.append({"from": current, "to": mig.to_version, "before": before, "after": data.copy()})
            current = mig.to_version
        return data


if __name__ == "__main__":
    registry = MigrationRegistry()
    # v1 -> v2 add field
    registry.register(Migration(1, 2, lambda d: {**d, "status": "active"}))

    # v2 -> v3 rename field user_id -> uid
    def to_v3(d):
        d = d.copy()
        if "user_id" in d:
            d["uid"] = d.pop("user_id")
        return d

    registry.register(Migration(2, 3, to_v3))

    # v3 -> v4 split name
    def to_v4(d):
        d = d.copy()
        if "name" in d and " " in d["name"]:
            first, last = d["name"].split(" ", 1)
            d["first_name"] = first
            d["last_name"] = last
        return d

    registry.register(Migration(3, 4, to_v4))

    original = {"user_id": "u123", "name": "Ada Lovelace"}
    upgraded = registry.upgrade(original, current=1, target=4)
    assert upgraded["status"] == "active"
    assert upgraded["uid"] == "u123"
    assert upgraded["first_name"] == "Ada" and upgraded["last_name"] == "Lovelace"
    assert len(registry.lineage) == 3
    print("OK: schema migration POC passed; lineage entries =", len(registry.lineage))
