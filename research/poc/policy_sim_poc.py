import fnmatch
from typing import Any

import yaml


def explain_rule(rule: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    m = rule.get("match", {})
    for k, v in m.items():
        if k == "data_scope_forbidden":
            ds = set(ctx.get("data_scope", []))
            bad = [x for x in v if x in ds]
            if bad:
                reasons.append(f"data_scope_forbidden matched: {bad}")
            else:
                reasons.append("data_scope_forbidden OK")
        else:
            pat = str(v)
            val = str(ctx.get(k, ""))
            if fnmatch.fnmatch(val, pat):
                reasons.append(f"{k} matched {pat}")
            else:
                reasons.append(f"{k} did not match {pat}")
    return {"rule": rule, "reasons": reasons}


def simulate(policy_yaml_path: str, ctx: dict[str, Any]) -> dict[str, Any]:
    with open(policy_yaml_path, encoding="utf-8") as f:
        pol = yaml.safe_load(f)
    trace: list[dict[str, Any]] = []
    decision = "deny"
    for r in pol.get("rules", []):
        exp = explain_rule(r, ctx)
        trace.append(exp)
        # basic match logic mirrors tools/policy_poc
        match = True
        m = r.get("match", {})
        for k, v in m.items():
            if k == "data_scope_forbidden":
                ds = set(ctx.get("data_scope", []))
                if any(x in ds for x in v):
                    match = False
                    break
            else:
                if not fnmatch.fnmatch(str(ctx.get(k, "")), str(v)):
                    match = False
                    break
        if match:
            decision = r.get("effect", "deny")
            break
    return {"decision": decision, "trace": trace}
