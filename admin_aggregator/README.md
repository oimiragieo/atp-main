# Admin Aggregator Service

A small FastAPI service that aggregates read-only admin data from multiple ATP router instances. Intended to back a monitoring UI and centralize status summaries without modifying the routers.

## Features

- List configured routers
- Summary across routers (version, state health)
- Aggregate cluster stats and model status
- CORS enabled (configurable)

## Configuration (env vars)

- `ROUTERS`: Comma-separated base URLs for routers, e.g. `http://router-0:8000,http://router-1:8000`
- `ADMIN_API_KEY`: Admin API key forwarded to routers in `X-Admin-API-Key`
- `REQUEST_TIMEOUT`: Per-request timeout seconds (default `3.0`)
- `AGGREGATOR_PORT`: Optional port for uvicorn (or pass via CLI)
- `CORS_ORIGINS`: Comma-separated list of allowed origins (default `*`)

## Run (dev)

Use your Windows PowerShell shell to run:

```powershell
$env:ROUTERS = "http://localhost:8000"
$env:ADMIN_API_KEY = "<your-admin-key>"
python -m uvicorn admin_aggregator.app:app --reload --port 8081
```

## Endpoints

- `GET /health` — aggregator health
- `GET /routers` — list configured router base URLs
- `GET /summary` — version + state health per router
- `GET /cluster_stats` — aggregate of `/admin/cluster_stats` across routers
- `GET /model_status` — aggregate of `/admin/model_status` across routers

## Notes

- This service is read-only. For config push/edit flows, add specific endpoints later to write to router config and call the hot-reloader. That’s intentionally deferred.
- Uses `httpx` with async concurrency and small timeouts to avoid head-of-line blocking.
