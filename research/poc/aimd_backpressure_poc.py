from dataclasses import dataclass


@dataclass
class AIMDController:
    cwnd: int = 10
    min_cwnd: int = 1
    max_cwnd: int = 1000
    ai_step: int = 1
    md_factor: float = 0.5

    def __post_init__(self):
        self.in_flight = 0

    def admit(self, n: int = 1) -> bool:
        if self.in_flight + n <= self.cwnd:
            self.in_flight += n
            return True
        return False

    def ack(self, n: int = 1) -> None:
        self.in_flight = max(0, self.in_flight - n)
        # additive increase per RTT (simulate per-ack increase for the POC)
        self.cwnd = min(self.max_cwnd, self.cwnd + self.ai_step)

    def loss(self) -> None:
        # multiplicative decrease on loss/congestion
        self.cwnd = max(self.min_cwnd, int(self.cwnd * self.md_factor))
        # ensure inflight does not exceed cwnd
        if self.in_flight > self.cwnd:
            self.in_flight = self.cwnd
