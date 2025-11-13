"""End-to-end OTEL-style trace simulation POC.
Creates a synthetic request trace with span hierarchy and propagates tokens/usd/qos attributes.
"""

from __future__ import annotations

import random
import time
from typing import Any


class Span:
    def __init__(self, name: str, parent: Span | None = None):
        self.name = name
        self.parent = parent
        self.children: list[Span] = []
        self.start = time.time()
        self.end = None
        self.attributes: dict[str, Any] = {}
        if parent:
            parent.children.append(self)

    def set_attr(self, key, value):
        self.attributes[key] = value

    def finish(self):
        self.end = time.time()


class Tracer:
    def __init__(self):
        self.root_spans: list[Span] = []

    def start_span(self, name: str, parent: Span | None = None):
        sp = Span(name, parent)
        if parent is None:
            self.root_spans.append(sp)
        return sp


def synth_request(tracer: Tracer, tokens_in: int, tokens_out: int, usd_micros: int, qos: str):
    root = tracer.start_span("http.request")
    root.set_attr("atp.tokens.in", tokens_in)
    root.set_attr("atp.tokens.out", tokens_out)
    root.set_attr("atp.usd_micros", usd_micros)
    root.set_attr("atp.qos", qos)
    # routing span
    route = tracer.start_span("router.select", root)
    route.set_attr("candidate.count", 3)
    # adapter calls
    adapters = []
    for i in range(2):
        ad = tracer.start_span(f"adapter.call.{i}", route)
        ad.set_attr("adapter.name", f"A{i}")
        ad.set_attr("latency_ms", random.randint(50, 150))
        adapters.append(ad)
    # finish order: leaves then upwards
    for s in adapters:
        s.finish()
    route.finish()
    root.finish()
    return root


def collect_trace(root: Span):
    spans = []

    def walk(s: Span, depth=0):
        spans.append({"name": s.name, "depth": depth, **s.attributes})
        for c in s.children:
            walk(c, depth + 1)

    walk(root)
    return spans


if __name__ == "__main__":
    tracer = Tracer()
    root = synth_request(tracer, 1200, 400, 55000, "gold")
    spans = collect_trace(root)
    # root attributes present
    assert any(sp["name"] == "http.request" and sp["atp.usd_micros"] == 55000 for sp in spans)
    # adapter spans captured
    assert sum(1 for sp in spans if sp["name"].startswith("adapter.call")) == 2
    print("OK: end-to-end traces POC passed; spans=", len(spans))
