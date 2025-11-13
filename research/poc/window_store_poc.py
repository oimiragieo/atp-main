import json
import threading
from dataclasses import asdict, dataclass


@dataclass
class Window:
    max_parallel: int
    max_tokens: int
    max_usd_micros: int


@dataclass
class Entry:
    inflight: int = 0
    tokens: int = 0
    usd: int = 0


class WindowStore:
    def admit(self, key: str, w: Window, est_tokens: int, est_usd: int) -> bool:
        raise NotImplementedError

    def ack(self, key: str, est_tokens: int, est_usd: int) -> None:
        raise NotImplementedError

    def get(self, key: str) -> Entry:
        raise NotImplementedError


class InMemoryStore(WindowStore):
    def __init__(self):
        self._lock = threading.Lock()
        self._map: dict[str, Entry] = {}

    def admit(self, key: str, w: Window, est_tokens: int, est_usd: int) -> bool:
        with self._lock:
            e = self._map.setdefault(key, Entry())
            if e.inflight >= w.max_parallel:
                return False
            if e.tokens + est_tokens > w.max_tokens:
                return False
            if e.usd + est_usd > w.max_usd_micros:
                return False
            e.inflight += 1
            e.tokens += est_tokens
            e.usd += est_usd
            return True

    def ack(self, key: str, est_tokens: int, est_usd: int) -> None:
        with self._lock:
            e = self._map.setdefault(key, Entry())
            e.inflight = max(0, e.inflight - 1)
            e.tokens = max(0, e.tokens - est_tokens)
            e.usd = max(0, e.usd - est_usd)

    def get(self, key: str) -> Entry:
        with self._lock:
            return self._map.get(key, Entry())


class FileStore(WindowStore):
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._ensure()

    def _ensure(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                json.load(f)
        except Exception:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _load(self) -> dict[str, Entry]:
        with open(self.path, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: Entry(**v) for k, v in raw.items()}

    def _save(self, m: dict[str, Entry]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in m.items()}, f)

    def admit(self, key: str, w: Window, est_tokens: int, est_usd: int) -> bool:
        with self._lock:
            m = self._load()
            e = m.get(key, Entry())
            if e.inflight >= w.max_parallel:
                return False
            if e.tokens + est_tokens > w.max_tokens:
                return False
            if e.usd + est_usd > w.max_usd_micros:
                return False
            e.inflight += 1
            e.tokens += est_tokens
            e.usd += est_usd
            m[key] = e
            self._save(m)
            return True

    def ack(self, key: str, est_tokens: int, est_usd: int) -> None:
        with self._lock:
            m = self._load()
            e = m.get(key, Entry())
            e.inflight = max(0, e.inflight - 1)
            e.tokens = max(0, e.tokens - est_tokens)
            e.usd = max(0, e.usd - est_usd)
            m[key] = e
            self._save(m)

    def get(self, key: str) -> Entry:
        with self._lock:
            m = self._load()
            return m.get(key, Entry())
