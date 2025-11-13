import re
from collections.abc import Iterable
from typing import Any, Optional

try:
    from metrics.registry import REGISTRY  # type: ignore

    _CTR_REDACTIONS = REGISTRY.counter("redactions_total")
except Exception:  # pragma: no cover - metrics optional in memory-gateway context
    _CTR_REDACTIONS = None

TextLike = str | int | float | bool | None
JsonLike = dict[str, Any] | list[Any] | TextLike

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

RE_DEFAULTS: dict[str, re.Pattern[str]] = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "ssn": _SSN_RE,
    "credit_card": _CC_RE,
}


def detect_pii(text: str, patterns: dict[str, re.Pattern[str]] = RE_DEFAULTS) -> list[tuple[str, tuple[int, int], str]]:
    """Return list of (kind, (start,end), match_text) for PII found in text."""
    hits: list[tuple[str, tuple[int, int], str]] = []
    for kind, regex in patterns.items():
        for m in regex.finditer(text):
            hits.append((kind, (m.start(), m.end()), m.group(0)))
    # de-duplicate overlapping by earliest start then longest span
    hits.sort(key=lambda x: (x[1][0], -(x[1][1] - x[1][0])))
    pruned: list[tuple[str, tuple[int, int], str]] = []
    cur_end = -1
    for h in hits:
        if h[1][0] >= cur_end:
            pruned.append(h)
            cur_end = h[1][1]
    return pruned


def _mask(s: str, visible: int = 4, fill: str = "*") -> str:
    if len(s) <= visible:
        return fill * len(s)
    return fill * (len(s) - visible) + s[-visible:]


def redact_text(text: str, mask_map: Optional[dict[str, Optional[str]]] = None) -> str:
    """Redact known PII patterns from text using masking rules per kind."""
    mask_map = mask_map or {
        "email": "[redacted-email]",
        "phone": "[redacted-phone]",
        "ssn": "[redacted-ssn]",
        "credit_card": None,
    }
    spans = detect_pii(text)
    if _CTR_REDACTIONS is not None and spans:
        _CTR_REDACTIONS.inc(len(spans))
    # Replace from end to start to preserve offsets
    out = text
    for kind, (start, end), match in reversed(spans):
        replacement = mask_map.get(kind)
        if replacement is None and kind == "credit_card":
            replacement = _mask(re.sub(r"[^0-9]", "", match))
        if replacement is None:
            replacement = "[redacted]"
        out = out[:start] + replacement + out[end:]
    return out


def redact_object(obj: JsonLike, redact_keys: Optional[Iterable[str]] = None) -> JsonLike:
    """Redact PII from JSON-like objects. Keys matching redact_keys are fully redacted."""
    base = list(redact_keys) if redact_keys else []
    redact_keys_set = set(base + ["password", "secret", "token", "ssn", "credit_card", "api_key"])  # common
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in redact_keys_set:
                out[k] = "[redacted]"
                if _CTR_REDACTIONS is not None:
                    _CTR_REDACTIONS.inc(1)
            else:
                out[k] = redact_object(v, redact_keys_set)
        return out
    elif isinstance(obj, list):
        return [redact_object(v, redact_keys_set) for v in obj]
    elif isinstance(obj, str):
        return redact_text(obj)
    else:
        return obj
