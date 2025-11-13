import asyncio
import json
import socket
import time

import websockets


def _port_open(port):
    s = socket.socket()
    s.settimeout(0.2)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


if not _port_open(7443):
    print("SKIP: ws end-to-end (service not running)")
else:

    async def run():
        async with websockets.connect("ws://localhost:7443/ws", max_size=1 << 22) as ws:
            frame = {
                "v": 1,
                "session_id": "s1",
                "stream_id": "st1",
                "msg_seq": 1,
                "frag_seq": 0,
                "flags": ["SYN"],
                "qos": "gold",
                "ttl": 5,
                "window": {"max_parallel": 4, "max_tokens": 5000, "max_usd_micros": 1000000},
                "meta": {"task_type": "qa", "tool_permissions": []},
                "payload": {"type": "agent.result.partial", "content": {"prompt": "hello"}},
            }
            await ws.send(json.dumps(frame))
            got_final = False
            t0 = time.time()
            while time.time() - t0 < 10:
                data = json.loads(await ws.recv())
                payload_type = data.get("payload", {}).get("type", "")
                if payload_type.endswith("final"):
                    got_final = True
                    break
            assert got_final
            print("OK final")

    asyncio.run(run())
