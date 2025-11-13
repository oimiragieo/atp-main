from typing import Any


def negotiate(client: dict[str, Any], server: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    # fields: encodings, compressions, features
    def inter(a: list[str], b: list[str]) -> list[str]:
        return [x for x in a if x in b]

    enc = inter(client.get("encodings", []), server.get("encodings", []))
    cmp = inter(client.get("compressions", []), server.get("compressions", []))
    feats = inter(client.get("features", []), server.get("features", []))
    if not enc:
        return False, {}
    agreed = {"encoding": enc[0], "compression": cmp[0] if cmp else None, "features": feats}
    return True, agreed
