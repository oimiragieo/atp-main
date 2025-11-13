class CardinalityGuard:
    def __init__(self, max_labels: int = 1000):
        self.max = max_labels
        self.seen: dict[tuple[str, str], int] = {}  # (metric, label_value) -> count

    def allow(self, metric: str, label_value: str) -> bool:
        key = (metric, label_value)
        if key in self.seen:
            self.seen[key] += 1
            return True
        # Enforce cardinality per metric by unique label values
        uniq = len([1 for (m, _v) in self.seen.keys() if m == metric])
        if uniq >= self.max:
            return False
        self.seen[key] = 1
        return True
