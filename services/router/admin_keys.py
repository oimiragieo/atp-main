"""Admin API key management and audit logging.

Provides in-memory key store with roles, persistence to a json file, and
helpers for rotation (add/remove). Keys are stored hashed at rest; the
plaintext is only returned at creation time. Hash: sha256 hex truncated.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time

_DATA_DIR = os.getenv("ROUTER_DATA_DIR", "./data")
_KEYS_FILE = os.path.join(_DATA_DIR, "admin_keys.json")
_AUDIT_FILE = os.path.join(_DATA_DIR, "admin_audit.jsonl")
_LOCK = threading.RLock()  # RLock to allow nested acquisition (audit within operations)
_KEYS: dict[str, set[str]] = {}  # hash->roles
_PLAIN_CACHE: dict[str, str] = {}  # plaintext->hash (for role differentiation checks)
_AUDIT_BUFFER: list[dict[str, object]] = []
_AUDIT_MAX = 500


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _persist() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump({h: list(r) for h, r in _KEYS.items()}, f, separators=(",", ":"))
    except Exception as err:  # noqa: S110
        # Non-fatal persistence error (e.g., filesystem race); continue in-memory
        _ = err


def init_from_env(env_value: str, fallback_key: str | None) -> None:
    """Populate key store from ROUTER_ADMIN_KEYS style string.
    Format: key[:role1+role2],key2[:roles] ... roles default to read+write.
    """
    if _KEYS:
        return
    raw = env_value.strip() if env_value else ""
    if not raw and fallback_key:
        add_key(fallback_key, roles={"read", "write"}, persist=False)
        return
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            key, rolespec = token.split(":", 1)
            roles = {r for r in rolespec.replace("+", ",").split(",") if r}
            if "write" in roles:
                roles.add("read")
        else:
            key = token
            roles = {"read", "write"}
        add_key(key, roles=roles, persist=False)
    _persist()


def load_persisted() -> None:
    if _KEYS:
        return
    try:
        if os.path.exists(_KEYS_FILE):
            with open(_KEYS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for h, roles in data.items():
                _KEYS[h] = set(roles)
    except Exception as err:  # noqa: S110
        _ = err


def add_key(plaintext: str, roles: set[str], persist: bool = True) -> tuple[str, str]:
    roles = set(roles)
    if "write" in roles:
        roles.add("read")
    h = _hash_key(plaintext)
    with _LOCK:
        _KEYS[h] = roles
        _PLAIN_CACHE[plaintext] = h
        if persist:
            _persist()
    # audit outside primary lock to avoid nested lock contention
    _audit("key.add", {"hash": h, "roles": sorted(roles)})
    return h, plaintext


def remove_key(hash_prefix: str) -> bool:
    h = None
    with _LOCK:
        matches = [k for k in _KEYS if k.startswith(hash_prefix)]
        if len(matches) != 1:
            return False
        h = matches[0]
        if len(_KEYS) <= 1:
            return False  # retain at least one key
        _KEYS.pop(h, None)
        _persist()
    _audit("key.remove", {"hash": h})
    return True


def list_keys() -> list[dict[str, object]]:
    with _LOCK:
        return [{"hash": h, "roles": sorted(r)} for h, r in _KEYS.items()]


def check_key(provided: str, required_role: str) -> bool:
    h = _hash_key(provided)
    with _LOCK:
        roles = _KEYS.get(h)
        if not roles:
            return False
        return required_role in roles


def key_roles(provided: str) -> set[str] | None:
    h = _hash_key(provided)
    with _LOCK:
        return set(_KEYS[h]) if h in _KEYS else None


def _audit(event: str, detail: dict[str, object]) -> None:
    rec = {"ts": time.time(), "event": event, **detail}
    try:
        with _LOCK:
            _AUDIT_BUFFER.append(rec)
            if len(_AUDIT_BUFFER) > _AUDIT_MAX:
                _AUDIT_BUFFER.pop(0)
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except Exception as err:  # noqa: S110
        _ = err


def audit_recent(limit: int = 50) -> list[dict[str, object]]:
    with _LOCK:
        return list(_AUDIT_BUFFER)[-limit:]


def hash_key(plaintext: str) -> str:
    return _hash_key(plaintext)


def ensure_env_keys_loaded() -> None:
    """Idempotently load any keys defined in current env that are not already present."""
    raw = os.getenv("ROUTER_ADMIN_KEYS", "").strip()
    if not raw:
        return
    existing_plain = set(_PLAIN_CACHE.keys())
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            key, rolespec = token.split(":", 1)
            roles = {r for r in rolespec.replace("+", ",").split(",") if r}
            if "write" in roles:
                roles.add("read")
        else:
            key = token
            roles = {"read", "write"}
        if key in existing_plain:
            continue
        add_key(key, roles, persist=False)


def reset_for_tests() -> None:  # pragma: no cover - test utility
    with _LOCK:
        _KEYS.clear()
        _PLAIN_CACHE.clear()
        _AUDIT_BUFFER.clear()
