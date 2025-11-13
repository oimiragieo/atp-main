"""POC: In-memory HMAC Key Manager (for signatures).

Maintains a mapping from key IDs (kid) to secret bytes with simple rotation
semantics for use by frame_sign helpers and verification endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeyRecord:
    kid: str
    secret: bytes


class KeyManager:
    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}
        self._current: str | None = None

    def add_key(self, kid: str, secret: bytes, make_current: bool = False) -> None:
        self._keys[kid] = secret
        if make_current or self._current is None:
            self._current = kid

    def get_key(self, kid: str) -> bytes:
        if kid not in self._keys:
            raise KeyError(f"unknown kid: {kid}")
        return self._keys[kid]

    def current_kid(self) -> str:
        if not self._current:
            raise KeyError("no current kid")
        return self._current

    def rotate(self, kid: str) -> None:
        if kid not in self._keys:
            raise KeyError(f"unknown kid: {kid}")
        self._current = kid

    def list_kids(self) -> list[str]:
        return list(self._keys.keys())
