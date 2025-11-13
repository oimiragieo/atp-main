import time


class Sampler:
    def should_sample(self, trace_id: str | None = None, parent_sampled: bool | None = None) -> bool:
        raise NotImplementedError


class AlwaysOn(Sampler):
    def should_sample(self, trace_id=None, parent_sampled=None) -> bool:
        return True


class ParentBased(Sampler):
    def __init__(self, root: Sampler):
        self.root = root

    def should_sample(self, trace_id=None, parent_sampled=None) -> bool:
        if parent_sampled is None:
            return self.root.should_sample(trace_id, None)
        return bool(parent_sampled)


class RateLimiting(Sampler):
    def __init__(self, traces_per_sec: float):
        self.rate = traces_per_sec
        self.allowance = traces_per_sec
        self.last = time.time()

    def should_sample(self, trace_id=None, parent_sampled=None) -> bool:
        now = time.time()
        elapsed = max(0.0, now - self.last)
        self.last = now
        self.allowance = min(self.rate, self.allowance + elapsed * self.rate)
        if self.allowance >= 1.0:
            self.allowance -= 1.0
            return True
        return False


def exemplar(trace_id: str, value: float, labels: dict | None = None) -> dict:
    """Return a minimal exemplar record linking a measurement to a trace id."""
    out = {
        "trace_id": trace_id,
        "value": value,
    }
    if labels:
        out["labels"] = labels
    return out
