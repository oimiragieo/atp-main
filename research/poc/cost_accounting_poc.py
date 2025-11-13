from dataclasses import dataclass


@dataclass
class Event:
    tenant: str
    adapter: str
    in_tokens: int
    out_tokens: int
    usd_micros: int


class Accountant:
    def __init__(self):
        self.by_tenant: dict[str, dict[str, int]] = {}
        self.by_adapter: dict[str, dict[str, int]] = {}

    def record(self, ev: Event) -> None:
        t = self.by_tenant.setdefault(ev.tenant, {"in_tokens": 0, "out_tokens": 0, "usd_micros": 0})
        t["in_tokens"] += ev.in_tokens
        t["out_tokens"] += ev.out_tokens
        t["usd_micros"] += ev.usd_micros
        a = self.by_adapter.setdefault(ev.adapter, {"in_tokens": 0, "out_tokens": 0, "usd_micros": 0})
        a["in_tokens"] += ev.in_tokens
        a["out_tokens"] += ev.out_tokens
        a["usd_micros"] += ev.usd_micros

    def report(self) -> dict[str, dict[str, dict[str, int]]]:
        return {"tenants": self.by_tenant, "adapters": self.by_adapter}
