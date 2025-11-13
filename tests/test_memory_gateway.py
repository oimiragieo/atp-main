import socket

import requests


def _port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.2)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def test_memory_gateway():
    if not _port_open(7443):
        print("SKIP: memory gateway (service not running)")
        return
    r = requests.get("http://localhost:7443/mem/put?ns=tenant/acme&key=test", timeout=1.0)
    print("mem put:", r.status_code, r.text)
    assert r.ok


if __name__ == "__main__":
    test_memory_gateway()
