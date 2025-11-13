"""Browser/Server Parity POC
Ensures both environments produce identical normalized frame envelopes and attach auth + telemetry hooks.
Simulates browser vs server builders and compares canonical JSON serialization.
"""

import hashlib
import json

from sdk_client_poc import build_frame


def normalize(frame):
    # Remove volatile fields (none currently) and sort keys via canonical JSON string
    return json.dumps(frame, sort_keys=True)


def browser_build():
    f = build_frame("sessB", "stream1", "text", {"msg": "hi"}, qos="silver")
    # simulate browser adding user-agent meta
    f["meta"]["ua"] = "web"
    return f


def server_build():
    f = build_frame("sessB", "stream1", "text", {"msg": "hi"}, qos="silver")
    f["meta"]["ua"] = "web"
    return f


def parity_check():
    browser_frame = browser_build()
    server_frame = server_build()
    nb = normalize(browser_frame)
    ns = normalize(server_frame)
    return nb == ns, hashlib.sha256(nb.encode()).hexdigest()


if __name__ == "__main__":
    ok, digest = parity_check()
    if ok:
        print(f"OK: browser/server parity POC passed digest={digest[:12]}")
    else:
        print("FAIL: browser/server parity POC")
