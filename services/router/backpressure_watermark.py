"""POC: Queue watermark backpressure signals (GAP-084A).

Tracks recent queue waits and emits a BACKPRESSURE trigger when high watermark
exceeded, clearing when a low watermark is observed.
"""

from __future__ import annotations

from dataclasses import dataclass

from metrics.registry import REGISTRY

_CTR_WM = REGISTRY.counter("queue_high_watermark_events_total")


@dataclass
class QueueWatermark:
    high_ms: float = 250.0
    low_ms: float = 50.0
    require_n: int = 3
    _consec_high: int = 0
    _under_high: bool = False

    def observe_wait_ms(self, wait_ms: float) -> tuple[bool, int]:
        """Observe a wait. Return (trigger, suggested_wait_ms).

        - When `require_n` consecutive waits exceed `high_ms`, trigger once and
          mark under_high. Emits metric increment.
        - While under_high, if a wait <= low_ms is seen, clear under_high.
        """
        if wait_ms > self.high_ms:
            self._consec_high += 1
            if not self._under_high and self._consec_high >= self.require_n:
                self._under_high = True
                _CTR_WM.inc(1)
                return True, int(min(1000, wait_ms))
            return False, 0
        # low path: clear
        if wait_ms <= self.low_ms and self._under_high:
            self._under_high = False
        self._consec_high = 0
        return False, 0
