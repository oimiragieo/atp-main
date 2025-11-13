# Repository Guidelines

## Project Structure & Module Organization
- `atp-router/`: Rust workspace with crates `atp-router` (bin at `crates/atp-router/src/main.rs`), `atp-schema`, `atp-adapter-proto`.
- `adapters/python/`: gRPC adapters (`persona_adapter`, `ollama_adapter`) exposing `AdapterService` on `:7070` (Docker uses `7071/7072`).
- `memory-gateway/`: Python HTTP service on `:8080`.
- `client/`: Local scripts for WS, health, and memory exercises.
- `tests/`: Integration tests targeting router `localhost:7443` and memory-gateway `:8080`.
- `docker-compose.yml`, `deploy/`, `observability/`, `grafana/`, `prometheus/`: Local stack and monitoring.

## Build, Test, and Development Commands
- Router build: `cd atp-router && cargo build` — compile Rust workspace.
- Router run: `cargo run -p atp-router` — start the router locally.
- Adapters: `cd adapters/python/<adapter> && pip install -r requirements.txt && python server.py` — run an adapter on `:7070`.
- Memory gateway: `cd memory-gateway && pip install -r requirements.txt && python app.py` — start HTTP on `:8080`.
- Full stack: `docker-compose up --build` — brings up router (`7443`), memory (`8080`), adapters (`7071/7072`), Prometheus (`9090`), Grafana (`3000`).
- Tests: `make test` or a single file, e.g., `python tests/test_ws_end_to_end.py`.

## Coding Style & Naming Conventions
- Rust: format with `cargo fmt`; lint via `cargo clippy --all-targets -- -D warnings`.
- Python: PEP 8, 4-space indent, type hints where useful.
- Naming: files/modules `snake_case`; types/traits `PascalCase`; functions/vars `snake_case`.
- Config: Keep ports/endpoints aligned with `docker-compose.yml`.

## Testing Guidelines
- Scope: Integration tests live in `tests/` and assume services running.
- Naming: `test_*.py`; keep deterministic and finish ≤10s.
- Running: `make test` or `python tests/<file>.py` for focused checks.

## Tools & POCs
- Location: `tools/` with paired tests in `tests/` (e.g., `tools/secret_vault_poc.py` ↔ `tests/test_secret_vault_poc.py`).
- Run: `python tools/<name>_poc.py`; test: `python tests/test_<name>_poc.py`.

## Commit & Pull Request Guidelines
- Commits: Imperative mood with scope, e.g., `router: add fair-queue metrics`.
- PRs: Include summary, linked issues, run instructions (commands), expected endpoints/ports, and evidence (logs/test output). Add Grafana screenshots when applicable.

## Security & Configuration Tips
- Env vars: `ADAPTER_ENDPOINTS`, `MEMORY_GATEWAY_URL`, `OPA_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Do not commit secrets; use local `.env`.
- Validate policy changes under `atp-router/opa/`.

