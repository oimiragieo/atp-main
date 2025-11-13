"""Pluggable KV & Vector backend contracts POC.
Defines abstract interfaces and two in-memory implementations plus a simple orchestrator.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any


class KVBackend(ABC):
    @abstractmethod
    def put(self, ns: str, key: str, value: Any) -> None: ...
    @abstractmethod
    def get(self, ns: str, key: str) -> Any: ...


class InMemoryKV(KVBackend):
    def __init__(self):
        self.store: dict[str, dict[str, Any]] = {}

    def put(self, ns: str, key: str, value: Any) -> None:
        self.store.setdefault(ns, {})[key] = value

    def get(self, ns: str, key: str) -> Any:
        return self.store.get(ns, {}).get(key)


Vector = tuple[list[float], dict[str, Any]]  # (embedding, metadata)


class VectorBackend(ABC):
    @abstractmethod
    def upsert(self, ns: str, key: str, embedding: list[float], metadata: dict[str, Any]): ...
    @abstractmethod
    def query(self, ns: str, embedding: list[float], k: int = 3) -> list[tuple[str, float, dict[str, Any]]]: ...


class InMemoryVector(VectorBackend):
    def __init__(self):
        self.vectors: dict[str, dict[str, Vector]] = {}

    def upsert(self, ns: str, key: str, embedding: list[float], metadata: dict[str, Any]):
        self.vectors.setdefault(ns, {})[key] = (embedding, metadata)

    def query(self, ns: str, embedding: list[float], k: int = 3):
        space = self.vectors.get(ns, {})
        scored = []
        for key, (emb, meta) in space.items():
            # cosine similarity
            dot = sum(a * b for a, b in zip(embedding, emb))
            na = math.sqrt(sum(a * a for a in embedding)) or 1
            nb = math.sqrt(sum(b * b for b in emb)) or 1
            sim = dot / (na * nb)
            scored.append((key, sim, meta))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


class StorageOrchestrator:
    def __init__(self, kv: KVBackend, vec: VectorBackend):
        self.kv = kv
        self.vec = vec

    def put_text(self, ns: str, key: str, text: str, embedding: list[float]):
        self.kv.put(ns, key, {"text": text})
        self.vec.upsert(ns, key, embedding, {"len": len(text)})

    def semantic_lookup(self, ns: str, embedding: list[float], k: int = 3):
        return self.vec.query(ns, embedding, k)

    def fetch(self, ns: str, key: str):
        return self.kv.get(ns, key)


if __name__ == "__main__":
    kv, vec = InMemoryKV(), InMemoryVector()
    orch = StorageOrchestrator(kv, vec)
    orch.put_text("default", "a", "hello world", [0.1, 0.2, 0.3])
    orch.put_text("default", "b", "hola mundo", [0.1, 0.2, 0.31])
    results = orch.semantic_lookup("default", [0.1, 0.2, 0.29])
    assert results and results[0][0] in {"a", "b"}
    print("OK: kv/vector backends POC passed")
