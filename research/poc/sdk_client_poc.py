import json
from typing import Any


def build_frame(
    session_id: str,
    stream_id: str,
    payload_type: str,
    content: dict[str, Any],
    qos: str = "gold",
    max_tokens: int = 50000,
    max_usd_micros: int = 1000000,
) -> dict[str, Any]:
    return {
        "v": 1,
        "session_id": session_id,
        "stream_id": stream_id,
        "msg_seq": 1,
        "frag_seq": 0,
        "flags": ["SYN"],
        "qos": qos,
        "ttl": 8,
        "window": {"max_parallel": 4, "max_tokens": max_tokens, "max_usd_micros": max_usd_micros},
        "meta": {"task_type": "qa", "tool_permissions": []},
        "payload": {"type": payload_type, "content": content},
    }


def serialize(frame: dict[str, Any]) -> str:
    # minimal validation
    for f in ["v", "session_id", "stream_id", "msg_seq", "payload"]:
        if f not in frame:
            raise ValueError(f"missing {f}")
    return json.dumps(frame)
