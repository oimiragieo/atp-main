"""POC: ECN-style advisory flags in frames (GAP-085).

Adds ECN flag to frame and increments a metric when marked.
"""

from __future__ import annotations

from metrics.registry import REGISTRY

from .frame import Frame

_CTR_ECN = REGISTRY.counter("ecn_mark_total")


def mark_ecn(frame: Frame) -> Frame:
    if "ECN" not in frame.flags:
        frame.flags.append("ECN")
        _CTR_ECN.inc(1)
    return frame
