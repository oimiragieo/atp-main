"""
Admin Aggregator Service

Purpose: Provide a small FastAPI service that aggregates read-only admin data
from multiple atp-router instances to back a monitoring UI.

Environment variables:
- ROUTERS: Comma-separated base URLs for router instances (e.g.,
  "http://router-0:8000,http://router-1:8000")
- ADMIN_API_KEY: Admin API key to forward in X-Admin-API-Key header
- REQUEST_TIMEOUT: Per-request timeout in seconds (float, default 3.0)
- AGGREGATOR_PORT: Port to run on when using `python -m uvicorn`
- CORS_ORIGINS: Comma-separated list of allowed origins for CORS

Run (example):
  ROUTERS=http://localhost:8000 \
  ADMIN_API_KEY=... \
  python -m uvicorn admin_aggregator.app:app --reload --port 8081
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


def _parse_env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class AggregatorConfig:
    routers: tuple[str, ...]
    admin_key: str
    request_timeout: float

    @staticmethod
    def from_env() -> AggregatorConfig:
        routers = tuple(_parse_env_list("ROUTERS"))
        if not routers:
            raise ValueError("ROUTERS environment variable must be set (comma-separated base URLs)")
        admin_key = os.getenv("ADMIN_API_KEY", "").strip()
        if not admin_key:
            raise ValueError("ADMIN_API_KEY must be set for aggregator to query admin endpoints")
        try:
            timeout = float(os.getenv("REQUEST_TIMEOUT", "3.0"))
        except ValueError:
            timeout = 3.0
        return AggregatorConfig(routers=routers, admin_key=admin_key, request_timeout=timeout)


def _build_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)


def _headers(admin_key: str) -> dict[str, str]:
    # Router supports X-Admin-API-Key or Bearer token; prefer explicit header
    return {"X-Admin-API-Key": admin_key}


app = FastAPI(title="ATP Admin Aggregator", version="0.1.0")


_origins = _parse_env_list("CORS_ORIGINS") or ["*"]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


def _get_cfg() -> AggregatorConfig:
    # Read each request to allow dynamic reconfigure via env reload
    return AggregatorConfig.from_env()


async def _fetch_json(
    client: httpx.AsyncClient, base: str, path: str, headers: dict[str, str]
) -> tuple[str, Any, str | None]:
    url = base.rstrip("/") + path
    try:
        res = await client.get(url, headers=headers)
        res.raise_for_status()
        return base, res.json(), None
    except Exception as e:  # noqa: S110
        return base, None, str(e)


@app.get("/routers")
async def list_routers() -> dict[str, Any]:
    cfg = _get_cfg()
    return {"routers": list(cfg.routers)}


@app.get("/summary")
async def summary() -> dict[str, Any]:
    cfg = _get_cfg()
    headers = _headers(cfg.admin_key)
    async with _build_client(cfg.request_timeout) as client:
        # parallel fetch version and state health
        tasks: list[asyncio.Task[tuple[str, Any, str | None]]] = []
        for base in cfg.routers:
            tasks.append(asyncio.create_task(_fetch_json(client, base, "/admin/version", headers)))
            tasks.append(asyncio.create_task(_fetch_json(client, base, "/admin/state_health", headers)))
        results = await asyncio.gather(*tasks)

    out: dict[str, dict[str, Any]] = {}
    for base, data, err in results:
        rec = out.setdefault(base, {"errors": []})
        if err:
            rec["errors"].append(err)
            continue
        if isinstance(data, dict) and "service_version" in data:
            rec["version"] = data
        elif isinstance(data, dict) and "status" in data and "backend" in data:
            rec["state_health"] = data
        else:
            rec["unknown"] = data

    return {"routers": out}


@app.get("/cluster_stats")
async def aggregate_cluster_stats() -> dict[str, Any]:
    cfg = _get_cfg()
    headers = _headers(cfg.admin_key)
    async with _build_client(cfg.request_timeout) as client:
        tasks = [
            asyncio.create_task(_fetch_json(client, base, "/admin/cluster_stats", headers)) for base in cfg.routers
        ]
        results = await asyncio.gather(*tasks)

    merged: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for base, data, err in results:
        if err or not isinstance(data, dict):
            errors[base] = err or "invalid_response"
            continue
        items = data.get("stats") or []
        if isinstance(items, list):
            for row in items:
                if isinstance(row, dict):
                    merged.append({"router": base, **row})

    return {"stats": merged, "errors": errors}


@app.get("/model_status")
async def aggregate_model_status() -> dict[str, Any]:
    cfg = _get_cfg()
    headers = _headers(cfg.admin_key)
    async with _build_client(cfg.request_timeout) as client:
        tasks = [asyncio.create_task(_fetch_json(client, base, "/admin/model_status", headers)) for base in cfg.routers]
        results = await asyncio.gather(*tasks)

    merged: list[dict[str, Any]] = []
    promotions = 0
    demotions = 0
    errors: dict[str, str] = {}
    for base, data, err in results:
        if err or not isinstance(data, dict):
            errors[base] = err or "invalid_response"
            continue
        promotions += int(data.get("promotions", 0) or 0)
        demotions += int(data.get("demotions", 0) or 0)
        models = data.get("models") or []
        if isinstance(models, list):
            for row in models:
                if isinstance(row, dict):
                    merged.append({"router": base, **row})

    return {"models": merged, "promotions": promotions, "demotions": demotions, "errors": errors}


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        cfg = _get_cfg()
        return {"status": "ok", "routers_configured": len(cfg.routers)}
    except Exception as e:  # noqa: S110
        raise HTTPException(status_code=500, detail=str(e))
