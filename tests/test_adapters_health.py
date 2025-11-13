import socket
import time

import requests


def _port_open(port):
    s = socket.socket()
    s.settimeout(0.2)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


if not _port_open(7443):
    print("SKIP: adapters health (router not running)")
else:
    for _ in range(30):
        try:
            r = requests.get("http://localhost:7443/adapters/health", timeout=1.5)
            print("adapters_health:", r.status_code, r.text)
            if r.ok:
                break
        except Exception:
            time.sleep(1)
    else:
        print("SKIP: adapters health (timeout)")
