"""Property/Fuzz Test POC for frame codec.
Generates many random frames and ensures encode/decode round trip invariants hold.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.frame_codec_poc import decode_frame, encode_frame, random_frame


def fuzz_round_trips(n: int = 500):
    for _ in range(n):
        f = random_frame()
        enc = encode_frame(f)
        dec = decode_frame(enc)
        # Invariant: all original fields preserved
        for k, v in f.items():
            assert dec[k] == v
    return True


if __name__ == "__main__":
    assert fuzz_round_trips(300)
    print("OK: property/fuzz frame codec POC passed")
