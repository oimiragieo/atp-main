import fnmatch
from typing import Any

import yaml


def load_policy(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def matches(rule_match: dict[str, Any], ctx: dict[str, Any]) -> bool:
    tenant_pat = rule_match.get("tenant", "*")
    task_type_pat = rule_match.get("task_type", "*")
    if not fnmatch.fnmatch(ctx.get("tenant", ""), tenant_pat):
        return False
    if not fnmatch.fnmatch(ctx.get("task_type", ""), task_type_pat):
        return False
    # Forbidden data scopes
    forbidden: list[str] = rule_match.get("data_scope_forbidden", [])
    ds = set(ctx.get("data_scope", []))
    if any(item in ds for item in forbidden):
        return False
    return True


def evaluate(policy: dict[str, Any], ctx: dict[str, Any]) -> str:
    for rule in policy.get("rules", []):
        if matches(rule.get("match", {}), ctx):
            return rule.get("effect", "deny")
    return "deny"
