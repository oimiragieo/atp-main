import hashlib
import json
import random
import time

"""Backup/DR POC
Simulates taking periodic snapshots of a key-value state, verifying integrity via hash,
restoring, and measuring RTO (restore time objective) and RPO (data loss window).
Outputs OK line with metrics.
"""


class KVStore:
    def __init__(self):
        self.data = {}
        self.last_write_ts = None

    def put(self, k, v):
        self.data[k] = v
        self.last_write_ts = time.time()

    def snapshot(self):
        payload = json.dumps(self.data, sort_keys=True).encode()
        h = hashlib.sha256(payload).hexdigest()
        return {"ts": time.time(), "hash": h, "payload": payload}

    @staticmethod
    def restore(snap):
        restored = KVStore()
        restored.data = json.loads(snap["payload"].decode())
        return restored


def simulate_backup_dr():
    store = KVStore()
    time.time()
    # simulate writes
    for i in range(50):
        store.put(f"k{i}", random.randint(1, 1000))
        time.sleep(0.001)
    snap = store.snapshot()
    # additional writes after snapshot to measure potential loss
    post_writes = 5
    for i in range(50, 50 + post_writes):
        store.put(f"k{i}", random.randint(1, 1000))
        time.sleep(0.001)
    # restore
    rto_start = time.time()
    restored = KVStore.restore(snap)
    rto = time.time() - rto_start
    # RPO approximated by time between snapshot and last write before disaster (here last snapshot time vs last write ts)
    rpo_window = store.last_write_ts - snap["ts"]
    integrity_ok = hashlib.sha256(json.dumps(restored.data, sort_keys=True).encode()).hexdigest() == snap["hash"]
    lost_keys = [k for k in store.data.keys() if k not in restored.data]
    return {
        "rto_ms": round(rto * 1000, 2),
        "rpo_window_ms": round(rpo_window * 1000, 2),
        "integrity_ok": integrity_ok,
        "lost_keys": len(lost_keys),
    }


if __name__ == "__main__":
    res = simulate_backup_dr()
    if res["integrity_ok"] and res["lost_keys"] > 0 and res["rto_ms"] < 50:
        print(
            f"OK: backup/DR POC passed rto_ms={res['rto_ms']} rpo_window_ms={res['rpo_window_ms']} lost_keys={res['lost_keys']}"
        )
    else:
        print("FAIL: backup/DR POC", res)
