import hashlib
import time


class AntiReplay:
    def __init__(self, window_s: int = 60):
        self.window = window_s
        self.seen: set[str] = set()

    def _hash(self, nonce: str, ts: int, session: str) -> str:
        return hashlib.sha256(f"{nonce}|{ts}|{session}".encode()).hexdigest()

    def accept(self, nonce: str, session: str, ts: int) -> bool:
        now = int(time.time())
        if abs(now - ts) > self.window:
            return False
        h = self._hash(nonce, ts, session)
        if h in self.seen:
            return False
        self.seen.add(h)
        return True
