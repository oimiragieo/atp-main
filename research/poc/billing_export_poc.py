import csv


def export_to_csv(report: dict[str, dict[str, dict[str, int]]], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["type", "name", "in_tokens", "out_tokens", "usd_micros"])
        for name, d in report.get("tenants", {}).items():
            w.writerow(["tenant", name, d["in_tokens"], d["out_tokens"], d["usd_micros"]])
        for name, d in report.get("adapters", {}).items():
            w.writerow(["adapter", name, d["in_tokens"], d["out_tokens"], d["usd_micros"]])
