import asyncio
import json
import os
import time

import websockets

C = int(os.environ.get("WS_LOAD_CONCURRENCY", "20"))
D = int(os.environ.get("WS_LOAD_DURATION_SEC", "30"))


async def run_conn(i):
    try:
        async with websockets.connect("ws://localhost:7443/ws", max_size=1 << 22) as ws:
            q = "bronze" if i % 3 == 0 else ("silver" if i % 3 == 1 else "gold")
            frame = {
                "v": 1,
                "session_id": f"s{i}",
                "stream_id": f"st{i}",
                "msg_seq": 1,
                "frag_seq": 0,
                "flags": ["SYN"],
                "qos": q,
                "ttl": 5,
                "window": {"max_parallel": 4, "max_tokens": 5000, "max_usd_micros": 1000000},
                "meta": {"task_type": "qa", "tool_permissions": []},
                "payload": {"type": "agent.result.partial", "content": {"prompt": "hello load"}},
            }
            await ws.send(json.dumps(frame))
            t0 = time.time()
            while time.time() - t0 < 3:
                await ws.recv()
    except Exception as err:  # noqa: S110 -- load test tolerates individual connection errors
        # Intentionally ignore individual connection errors during load generation
        _ = err


async def main():
    end = time.time() + D
    i = 0
    while time.time() < end:
        await asyncio.gather(*[run_conn(i + j) for j in range(C)], return_exceptions=True)
        i += C


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
