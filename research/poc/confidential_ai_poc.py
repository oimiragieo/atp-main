"""Confidential AI / TEE POC
Simulates attestation of an enclave (hash measurement) and gating execution on attestation policy.
"""

import hashlib
import os


def measure(binary: bytes):
    return hashlib.sha256(binary).hexdigest()


def attest(measurement: str, allowed: str):
    return measurement == allowed


if __name__ == "__main__":
    fake_bin = os.urandom(32)
    m = measure(fake_bin)
    allowed = m  # allow this run
    if attest(m, allowed):
        print("OK: confidential AI TEE POC passed")
    else:
        print("FAIL: confidential AI TEE POC")
