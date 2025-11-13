
# 15 — Docker POC Guide

## Prereqs
- Docker + Docker Compose
- (Optional) Rust toolchain if building locally outside compose

## Up
```bash
cd atp_bundle
docker compose build
docker compose up -d
```

## Verify
- Router: http://localhost:7443/healthz
- Persona adapter logs: `docker logs -f atp_bundle-persona_adapter-1` (container name may vary)
- Memory gateway: http://localhost:8080/healthz
- Prometheus: http://localhost:9090/

## Try Memory Gateway
```bash
python client/memory_put_get.py
```

## Down
```bash
docker compose down
```

### Notes
- Router's `/ws` is a stub in this POC; replace with the ATP frame codec as you implement.
- OPA, mTLS, vector/graph tiers are intentionally excluded for minimal friction. See security & SMF docs for production setup.
