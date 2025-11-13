"""POC: Persistent session table (GAP-080).

File-backed session table to simulate externalized state (e.g., Redis/SQL).
Tracks active sessions with last-updated timestamp and optional attributes.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from metrics.registry import REGISTRY

_G_SESSIONS = REGISTRY.gauge("sessions_active")


@dataclass
class SessionRecord:
    session: str
    updated: float
    attrs: dict[str, Any]


class SessionTableFile:
    def __init__(self, path: str) -> None:
        self._path = path
        self._m: dict[str, SessionRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._m = {
                k: SessionRecord(session=k, updated=v.get("updated", 0.0), attrs=v.get("attrs", {}))
                for k, v in data.items()
            }
        except FileNotFoundError:
            self._m = {}
        except Exception:
            # Corrupt or unreadable -> start fresh
            self._m = {}
        _G_SESSIONS.set(len(self._m))

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        data = {k: asdict(v) for k, v in self._m.items()}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))

    def upsert(self, session: str, attrs: dict[str, Any] | None = None) -> None:
        now = time.time()
        rec = self._m.get(session)
        if rec is None:
            rec = SessionRecord(session=session, updated=now, attrs=dict(attrs or {}))
        else:
            rec.updated = now
            if attrs:
                rec.attrs.update(attrs)
        self._m[session] = rec
        self._save()
        _G_SESSIONS.set(len(self._m))

    def get(self, session: str) -> SessionRecord | None:
        return self._m.get(session)

    def delete(self, session: str) -> None:
        if session in self._m:
            self._m.pop(session, None)
            self._save()
            _G_SESSIONS.set(len(self._m))

    def count(self) -> int:
        return len(self._m)

    def purge_expired(self, ttl_s: float) -> int:
        now = time.time()
        dead = [k for k, v in self._m.items() if (now - v.updated) > ttl_s]
        for k in dead:
            self._m.pop(k, None)
        if dead:
            self._save()
            _G_SESSIONS.set(len(self._m))
        return len(dead)
