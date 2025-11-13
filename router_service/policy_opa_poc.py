"""POC: Simple OPA-like policy evaluator (local rules).

Loads a JSON policy from env or file and enforces basic allow/deny on ask
requests. This is a stopgap for integrating a real OPA client.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class RequestContext:
    tenant: str
    data_scope: str | None
    headers: dict[str, str]


def load_policy() -> dict[str, Any] | None:
    text = os.getenv("POLICY_JSON")
    if text:
        try:
            return json.loads(text)
        except Exception:
            return None
    path = os.getenv("POLICY_PATH")
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None
    return None


def evaluate(ctx: RequestContext, policy: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Return (allowed, reason). Policy schema (POC):
    {
      "deny_tenants": ["foo"],
      "allow_tenants": ["bar"],
      "deny_scopes": ["secret"],
      "require_headers": ["x-policy-ok"]
    }
    """
    pol = policy or load_policy() or {}
    deny_t = set(pol.get("deny_tenants", []) or [])
    if ctx.tenant in deny_t:
        return False, "tenant_denied"
    allow_t = pol.get("allow_tenants")
    if allow_t is not None and len(allow_t) > 0 and ctx.tenant not in set(allow_t):
        return False, "tenant_not_allowed"
    deny_scopes = set(pol.get("deny_scopes", []) or [])
    if ctx.data_scope and ctx.data_scope in deny_scopes:
        return False, "scope_denied"
    req_headers = pol.get("require_headers") or []
    for h in req_headers:
        if h not in ctx.headers:
            return False, "missing_header"
    return True, None
