from contextlib import contextmanager
from typing import Any, Optional


class Span:
    def __init__(self, name: str):
        self.name = name
        self.attributes: dict[str, Any] = {}

    def set_attr(self, key: str, value: Any) -> None:
        self.attributes[key] = value


@contextmanager
def start_span(name: str, tokens: Optional[int] = None, usd_micros: Optional[int] = None, qos: Optional[str] = None):
    span = Span(name)
    if tokens is not None:
        span.set_attr("atp.tokens", int(tokens))
    if usd_micros is not None:
        span.set_attr("atp.usd_micros", int(usd_micros))
    if qos is not None:
        span.set_attr("atp.qos", str(qos))
    try:
        yield span
    finally:
        # finalize hook placeholder
        pass
