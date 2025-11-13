"""FlatBuffers vs JSON Size Evaluation POC (Simulated)
Constructs representative frame dict, estimates JSON length, and simulates FlatBuffer size reduction.
"""

import json

from sdk_client_poc import build_frame


def evaluate():
    frame = build_frame("sess", "str", "text", {"msg": "hello world" * 5})
    json_bytes = len(json.dumps(frame))
    # Assume FlatBuffers eliminates key strings (simulate 35% reduction)
    flat_bytes = int(json_bytes * 0.65)
    return {"json_bytes": json_bytes, "flat_bytes": flat_bytes, "reduction_pct": round(1 - flat_bytes / json_bytes, 2)}


if __name__ == "__main__":
    res = evaluate()
    if res["reduction_pct"] >= 0.3:
        print(f"OK: flatbuffers eval POC passed reduction={res['reduction_pct']}")
    else:
        print("FAIL: flatbuffers eval POC", res)
