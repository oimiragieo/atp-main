def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def disagreement(spans: list[set[str]]) -> float:
    """1 - average pairwise Jaccard similarity over sets of tokens/spans."""
    if len(spans) < 2:
        return 0.0
    n = 0
    total = 0.0
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            total += jaccard(spans[i], spans[j])
            n += 1
    sim = total / max(1, n)
    return 1.0 - sim


def calibrate_confidences(confs: list[float], correct: list[bool]) -> float:
    """Return temperature T > 0 such that softmax-like scaling c' = c**(1/T) roughly matches observed accuracy.

    Simple grid search over T in [0.5, 2.0] minimizing squared error between mean(c') and empirical accuracy.
    """
    assert len(confs) == len(correct)
    acc = sum(1.0 if x else 0.0 for x in correct) / max(1, len(correct))
    best_temp = 1.0
    best_err = 1e9
    for temp in [0.5 + 0.05 * i for i in range(31)]:
        adj = [c ** (1.0 / temp) for c in confs]
        mean_adj = sum(adj) / max(1, len(adj))
        err = (mean_adj - acc) ** 2
        if err < best_err:
            best_err = err
            best_temp = temp
    return best_temp
