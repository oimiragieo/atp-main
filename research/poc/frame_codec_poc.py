import json
import random
from typing import Any

FIELDS = ["v", "session_id", "stream_id", "msg_seq", "frag_seq", "flags", "qos", "ttl", "window", "meta", "payload"]


def encode_frame(frame: dict[str, Any]) -> str:
    # minimal validator
    for f in FIELDS:
        if f not in frame:
            raise ValueError(f"missing {f}")
    return json.dumps(frame, separators=(",", ":"), sort_keys=True)


def decode_frame(s: str) -> dict[str, Any]:
    obj = json.loads(s)
    for f in FIELDS:
        if f not in obj:
            raise ValueError(f"missing {f}")
    return obj


def random_frame() -> dict[str, Any]:
    return {
        "v": 1,
        "session_id": f"s{random.randint(1, 100)}",
        "stream_id": f"st{random.randint(1, 100)}",
        "msg_seq": random.randint(1, 1000),
        "frag_seq": random.randint(0, 3),
        "flags": ["SYN"] if random.random() < 0.5 else ["MORE"],
        "qos": random.choice(["gold", "silver", "bronze"]),
        "ttl": random.randint(1, 10),
        "window": {"max_parallel": 4, "max_tokens": 50000, "max_usd_micros": 1000000},
        "meta": {"task_type": "qa", "tool_permissions": []},
        "payload": {"type": "agent.result.partial", "content": {"x": random.randint(0, 10)}},
    }
