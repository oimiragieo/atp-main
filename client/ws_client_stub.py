import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect("ws://localhost:7443/ws") as ws:
        frame = {
            "v": 1,
            "session_id": "s1",
            "stream_id": "st1",
            "msg_seq": 1,
            "frag_seq": 0,
            "flags": ["SYN"],
            "qos": "gold",
            "ttl": 8,
            "window": {"max_parallel": 4, "max_tokens": 50000, "max_usd_micros": 1000000},
            "meta": {"task_type": "qa", "tool_permissions": []},
            "payload": {"type": "agent.result.partial", "content": {"prompt": "hello"}},
        }
        await ws.send(json.dumps(frame))
        while True:
            msg = await ws.recv()
            print(msg)


asyncio.run(main())
