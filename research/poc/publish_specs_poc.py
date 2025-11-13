"""Spec publishing POC.
Validates presence of OpenAPI, AsyncAPI, and gRPC proto spec and prints a manifest index.
"""

from __future__ import annotations

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OPENAPI = os.path.join(os.path.dirname(__file__), "openapi_poc.yaml")
ASYNCAPI = os.path.join(os.path.dirname(__file__), "asyncapi_poc.yaml")
GRPC = os.path.join(os.path.dirname(__file__), "grpc_spec_poc.proto")

REQUIRED = [OPENAPI, ASYNCAPI, GRPC]


def validate():
    missing = [p for p in REQUIRED if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"Missing specs: {missing}")
    proto_txt = open(GRPC, encoding="utf-8").read()
    assert "service Memory" in proto_txt
    manifest: dict[str, str] = {
        "openapi": os.path.relpath(OPENAPI, ROOT),
        "asyncapi": os.path.relpath(ASYNCAPI, ROOT),
        "grpc": os.path.relpath(GRPC, ROOT),
    }
    print("OK: spec publishing POC passed", json.dumps(manifest))


if __name__ == "__main__":
    validate()
