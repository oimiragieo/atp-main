"""Adapter marketplace registry POC.
Supports register, list, filter by capability, and simple rating aggregation.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field


@dataclass
class Adapter:
    name: str
    capabilities: list[str]
    ratings: list[int] = field(default_factory=list)


class Marketplace:
    def __init__(self):
        self.adapters: dict[str, Adapter] = {}

    def register(self, name: str, capabilities: builtins.list[str]):
        if name in self.adapters:
            raise ValueError("exists")
        self.adapters[name] = Adapter(name, capabilities)

    def rate(self, name: str, score: int):
        self.adapters[name].ratings.append(score)

    def list(self, capability: str | None = None):
        items = list(self.adapters.values())
        if capability:
            items = [a for a in items if capability in a.capabilities]
        result = []
        for a in items:
            avg = (sum(a.ratings) / len(a.ratings)) if a.ratings else None
            result.append({"name": a.name, "capabilities": a.capabilities, "avg_rating": avg})
        return result


if __name__ == "__main__":
    m = Marketplace()
    m.register("gpt4", ["chat", "reasoning"])
    m.register("image-gen", ["image"])
    m.rate("gpt4", 5)
    m.rate("gpt4", 4)
    lst = m.list("chat")
    assert lst[0]["avg_rating"] and lst[0]["avg_rating"] > 4.4 - 1e-6
    print("OK: adapter marketplace POC passed; entries=", lst)
