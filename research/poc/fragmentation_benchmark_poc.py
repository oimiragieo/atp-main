"""POC: Fragmentation performance micro-benchmark (GAP-002).

Measures time to fragment a large text payload and reports fragment count and
elapsed milliseconds. Designed to be fast and deterministic without external
deps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Try to import router_service modules, fallback to mock if not available
try:
    from router_service.fragmentation import fragment_frame
    from router_service.frame import Frame, Meta, Payload, Window
    ROUTER_AVAILABLE = True
except ImportError:
    ROUTER_AVAILABLE = False

    @dataclass
    class Frame:
        v: int
        session_id: str
        stream_id: str
        msg_seq: int
        frag_seq: int
        flags: list[str]
        qos: str
        ttl: int
        window: Window
        meta: Meta
        payload: Payload

    @dataclass
    class Window:
        max_parallel: int
        max_tokens: int
        max_usd_micros: int

    @dataclass
    class Meta:
        task_type: str

    @dataclass
    class Payload:
        type: str
        content: dict

    def fragment_frame(frame, max_fragment_size: int):
        """Mock fragmentation function."""
        text = frame.payload.content.get("text", "")
        if not text:
            return [frame]

        # Simple mock fragmentation
        fragments = []
        for i in range(0, len(text), max_fragment_size):
            chunk = text[i:i + max_fragment_size]
            frag = Frame(
                v=frame.v,
                session_id=frame.session_id,
                stream_id=frame.stream_id,
                msg_seq=frame.msg_seq,
                frag_seq=len(fragments),
                flags=frame.flags,
                qos=frame.qos,
                ttl=frame.ttl,
                window=frame.window,
                meta=frame.meta,
                payload=Payload(type=frame.payload.type, content={"text": chunk})
            )
            fragments.append(frag)
        return fragments


@dataclass
class BenchResult:
    fragments: int
    elapsed_ms: float


def _make_frame(text: str) -> Frame:
    return Frame(
        v=1,
        session_id="bench",
        stream_id="frag",
        msg_seq=1,
        frag_seq=0,
        flags=["SYN"],
        qos="gold",
        ttl=5,
        window=Window(max_parallel=4, max_tokens=1_000_000, max_usd_micros=10_000_000),
        meta=Meta(task_type="bench"),
        payload=Payload(type="agent.result.partial", content={"text": text}),
    )


def run_benchmark(size_bytes: int = 256 * 1024, frag_size: int = 4096) -> BenchResult:
    text = "A" * size_bytes
    frame = _make_frame(text)
    t0 = time.perf_counter()
    frags = fragment_frame(frame, max_fragment_size=frag_size)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return BenchResult(fragments=len(frags), elapsed_ms=elapsed_ms)


if __name__ == "__main__":
    result = run_benchmark()
    print(f"Router service available: {ROUTER_AVAILABLE}")
    print(f"Benchmark result: {result.fragments} fragments in {result.elapsed_ms:.3f}ms")
