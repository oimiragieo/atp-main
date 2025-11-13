"""CCR (Claude Code Router) config importer.

Converts a Claude Code Router style config.json Providers + Router mapping
into ATP model registry records.

Usage (rough sketch):
    from router_service.ccr_importer import import_ccr_config
    import_ccr_config(path_or_dict)

Notes:
 - We map provider+model into a flat model name "provider:model" if collision risk.
 - Safety grade default 'B'; cost/latency placeholders until empirical stats gathered.
 - Router roles (background/think/longContext) map to clusters via tags for future policy.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .model_manifest import load_registry, save_registry

ROLE_TO_TAG = {
    "background": "background",
    "think": "reasoning",
    "longContext": "long",
}


def import_ccr_config(cfg: str | dict[str, Any]) -> dict[str, dict[str, Any]]:
    if isinstance(cfg, str):
        with open(cfg, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = cfg
    providers = data.get("Providers") or []
    router = data.get("Router") or {}
    reg = load_registry()
    router_sets: dict[str, set[str]] = {}
    for role, models in router.items():
        if not isinstance(models, str):
            continue
        parts = [m.strip() for m in models.split(",") if m.strip()]
        router_sets[role] = set(parts)
    for prov in providers:
        name = prov.get("name")
        models = prov.get("models") or []
        for m in models:
            fq = f"{name}:{m}" if ":" not in m else m
            rec = reg.get(fq)
            if not rec:
                rec = {
                    "model": fq,
                    "provider": name,
                    "status": "active",
                    "safety_grade": "B",
                    "est_latency_ms": 1200,
                    "est_cost_per_1k_tokens_usd": 0.002,
                    "tags": [],
                }
            tags = set(rec.get("tags") or [])
            for role, tag in ROLE_TO_TAG.items():
                if m in router_sets.get(role, set()) or fq in router_sets.get(role, set()):
                    tags.add(tag)
            rec["tags"] = sorted(tags)
            reg[fq] = rec
    save_registry(reg)
    return reg


def import_from_env() -> None:  # convenience: path via CCR_CONFIG_PATH
    path = os.getenv("CCR_CONFIG_PATH")
    if path and os.path.exists(path):
        import_ccr_config(path)


__all__ = ["import_ccr_config", "import_from_env"]
