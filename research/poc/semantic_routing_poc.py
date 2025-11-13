"""Semantic/Capability-Based Routing POC
Builds lightweight embeddings (character histogram vectors) and selects adapter by cosine similarity plus capability tag match.
"""

import math
from collections import Counter


def embed(text):
    c = Counter(text.lower())
    keys = sorted(k for k in c if k.isalpha())
    return [c[k] for k in keys], keys


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na * nb == 0:
        return 0.0
    return dot / (na * nb)


def select_adapter(query, adapters):
    qv, qk = embed(query)
    best = None
    best_score = -1.0
    for name, meta in adapters.items():
        av, ak = embed(" ".join(meta["keywords"]))
        # pad vectors to common key set
        all_keys = sorted(set(qk + ak))

        def vec(keys, kset, v):
            mapping = dict(zip(kset, v))
            return [mapping.get(k, 0) for k in keys]

        qvec = vec(all_keys, qk, qv)
        avec = vec(all_keys, ak, av)
        sim = cosine(qvec, avec)
        if meta.get("capability") in query and sim > best_score:
            best = name
            best_score = sim
    return best, round(best_score, 3)


if __name__ == "__main__":
    adapters = {
        "math-adapter": {"keywords": ["calculate", "numbers", "math"], "capability": "math"},
        "qa-adapter": {"keywords": ["question", "answer", "knowledge"], "capability": "qa"},
    }
    choice, score = select_adapter("please math solve 2+2", adapters)
    if choice == "math-adapter" and score > 0:
        print(f"OK: semantic routing POC passed choice={choice} score={score}")
    else:
        print("FAIL: semantic routing POC", choice, score)
