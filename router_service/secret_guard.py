"""POC: Secret egress guard (GAP-049).

Scans outbound content for likely secrets and blocks when detected.
"""

from __future__ import annotations

import re

from metrics.registry import REGISTRY

_CTR_SECRET_BLOCK = REGISTRY.counter("secret_block_total")

# Detector patterns (basic repository)
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET = re.compile(r"\b[0-9a-zA-Z/+]{40}\b")
_GCP_KEY_JSON = re.compile(r"\"type\"\s*:\s*\"service_account\"")
_BEARER_TOKEN = re.compile(r"\b(?:eyJ|ya29)\w+\.[\w-]+\.[\w-]+\b")  # rough JWT/OAuth
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9]{20,48}\b")

DETECTORS = {
    "aws_access_key": _AWS_ACCESS_KEY,
    "aws_secret": _AWS_SECRET,
    "gcp_sa_key": _GCP_KEY_JSON,
    "bearer_token": _BEARER_TOKEN,
    "openai_key": _OPENAI_KEY,
}


def scan_text(text: str) -> tuple[bool, str | None]:
    """Return (allowed, reason). Increments secret_block_total on block."""
    for name, rx in DETECTORS.items():
        if rx.search(text or ""):
            _CTR_SECRET_BLOCK.inc(1)
            return False, name
    return True, None
