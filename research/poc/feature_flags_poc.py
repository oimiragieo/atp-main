from typing import Any


def intersect_flags(client: dict[str, Any], server: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Negotiate feature flags and versions.

    Inputs like: {"version":"1.0", "features":{"consensus":true, "bandit":false}}
    Returns (ok, {"version":"1.0","features":{...}})
    ok is False if versions incompatible (major mismatch).
    """
    cv = str(client.get("version", "1.0"))
    sv = str(server.get("version", "1.0"))
    # major version compatibility check
    cmaj = cv.split(".")[0]
    smaj = sv.split(".")[0]
    if cmaj != smaj:
        return False, {}
    cf = client.get("features", {})
    sf = server.get("features", {})
    agreed = {}
    for k, v in cf.items():
        if k in sf:
            agreed[k] = bool(v and sf[k])
    return True, {"version": sv, "features": agreed}
