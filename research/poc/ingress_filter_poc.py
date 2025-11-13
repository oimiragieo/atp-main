import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
import pii as PII  # noqa: N812 (external memory-gateway module alias)


def redact_frame(frame: dict[str, Any]) -> dict[str, Any]:
    out = dict(frame)
    # Redact meta fields and payload content
    if "meta" in out and isinstance(out["meta"], dict):
        out["meta"] = PII.redact_object(out["meta"])  # redact keys/strings
    if "payload" in out and isinstance(out["payload"], dict):
        p = dict(out["payload"])
        if "content" in p:
            p["content"] = PII.redact_object(p["content"])
        out["payload"] = p
    return out
