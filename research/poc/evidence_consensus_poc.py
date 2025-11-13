"""Evidence-Weighted Consensus POC
Aggregates multiple model answers with confidence + evidence citations; computes weighted vote and verifier check.
"""


def aggregate(responses):
    total = sum(r["confidence"] for r in responses)
    weights = [r["confidence"] / total for r in responses]
    score = {}
    for w, r in zip(weights, responses):
        score[r["answer"]] = score.get(r["answer"], 0) + w
    best = max(score.items(), key=lambda x: x[1])
    # simple verifier: hash diversity of evidence
    evidence_concat = "|".join(sorted(e for r in responses for e in r["evidence"]))
    diversity = len(set(evidence_concat.split("|")))
    verifier_pass = diversity >= len(responses)
    return {"answer": best[0], "confidence": round(best[1], 3), "verifier": verifier_pass}


if __name__ == "__main__":
    responses = [
        {"answer": "Paris", "confidence": 0.9, "evidence": ["w1", "w2"]},
        {"answer": "Paris", "confidence": 0.7, "evidence": ["w2", "w3"]},
        {"answer": "Lyon", "confidence": 0.2, "evidence": ["w4"]},
    ]
    res = aggregate(responses)
    if res["answer"] == "Paris" and res["verifier"]:
        print(f"OK: evidence consensus POC passed conf={res['confidence']}")
    else:
        print("FAIL: evidence consensus POC", res)
