"""POC: WAF core rules + prompt injection signatures.

Provides a lightweight prompt filter returning (allowed: bool, reason: str|None)
and increments a block counter on matches.
"""

from __future__ import annotations

import os
import re

from metrics.registry import REGISTRY

_CTR_WAF_BLOCK = REGISTRY.counter("waf_block_total")

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+all\s+previous\s+instructions", re.I),
    re.compile(r"reveal\s+.*system\s+prompt", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"act\s+as\s+the\s+system\s+prompt", re.I),
    re.compile(r"do\s+anything\s+now", re.I),
]

_CUSTOM_PATTERNS: list[re.Pattern[str]] | None = None


def reload_from_env() -> None:
    """Load custom WAF patterns from env `WAF_PATTERNS` (comma-separated or JSON list)."""
    global _CUSTOM_PATTERNS
    spec = os.getenv("WAF_PATTERNS")
    if not spec:
        _CUSTOM_PATTERNS = []
        return
    pats: list[str] = []
    try:
        import json

        obj = json.loads(spec)
        if isinstance(obj, list):
            pats = [str(x) for x in obj]
    except Exception:
        pats = [p.strip() for p in spec.split(",") if p.strip()]
    _CUSTOM_PATTERNS = [re.compile(p, re.I) for p in pats]


def _iter_patterns() -> list[re.Pattern[str]]:
    global _CUSTOM_PATTERNS
    if _CUSTOM_PATTERNS is None:
        reload_from_env()
    return (_CUSTOM_PATTERNS or []) + _PROMPT_INJECTION_PATTERNS


def check_prompt(text: str) -> tuple[bool, str | None]:
    for pat in _iter_patterns():
        if pat.search(text or ""):
            _CTR_WAF_BLOCK.inc(1)
            return False, "prompt_injection"
    return True, None
