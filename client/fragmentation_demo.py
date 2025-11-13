"""Demo: Send a large fragmented frame over WebSocket to the router.

Usage:
  python client/fragmentation_demo.py

Requires `websockets` package. Skips if router is not running on :7443.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any


def _port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.2)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


async def main() -> None:
    if not _port_open(7443):
        print("Router not running on :7443; skipping demo.")
        return
    try:
        import websockets  # type: ignore
    except Exception:
        print("Please install websockets: pip install websockets")
        return
    uri = "ws://localhost:7443/ws"
    frame: dict[str, Any] = {
        "v": 1,
        "session_id": "demo",
        "stream_id": "fragdemo",
        "msg_seq": 1,
        "frag_seq": 0,
        "flags": ["SYN"],
        "qos": "gold",
        "ttl": 5,
        "window": {"max_parallel": 4, "max_tokens": 100_000, "max_usd_micros": 10_000_000},
        "meta": {"task_type": "qa", "tool_permissions": []},
        "payload": {"type": "agent.result.partial", "content": {"prompt": "X" * (256 * 1024)}},
    }
    async with websockets.connect(uri, max_size=1 << 24) as ws:  # type: ignore
        await ws.send(json.dumps(frame))
        finals = 0
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            typ = data.get("payload", {}).get("type")
            if typ and str(typ).endswith("final"):
                finals += 1
                break
        print("Demo complete with finals:", finals)


if __name__ == "__main__":
    asyncio.run(main())
