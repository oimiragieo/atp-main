from metrics.registry import REGISTRY

from router_service.consensus import jaccard_agreement


def test_agreement_histogram_increments():
    pre = REGISTRY.export()["histograms"].get("agreement_pct")
    # Two similar strings should yield non-zero score and record an observation
    s1 = "the quick brown fox"
    s2 = "the quick red fox"
    score = jaccard_agreement([s1, s2])
    assert 0.0 < score <= 1.0
    post = REGISTRY.export()["histograms"].get("agreement_pct")
    assert post is not None
    if pre is None:
        assert sum(post["counts"]) >= 1
    else:
        assert sum(post["counts"]) >= sum(pre["counts"]) + 1
