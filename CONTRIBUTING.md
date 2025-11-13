# Contributing

Welcome! This project enforces a high bar for code quality, typing, security, and test discipline. Follow the guidelines below to keep the main branch green and predictable.

## Quick Start
1. Create a virtualenv (Python 3.11+).
2. Install deps: `pip install -r memory-gateway/requirements.txt` (and any local extras as needed).
3. Run lint + types + tests before pushing:
   - `make lint`
   - `make type`
   - `pytest -q` (or targeted tests)

## Tooling Gates
| Check | Command | Policy |
|-------|---------|--------|
| Ruff lint | `make lint` | Zero new violations. Justify rare `# noqa` inline with short reason. |
| Typing (mypy) | `make type` | Zero errors for production code. Tests/tools may be excluded by config—prefer adding types when easy. |
| Formatting | `ruff format .` | Keep diffs minimal. CI will fail if formatting drift occurs. |
| Security (selected rules) | Part of Ruff S*** & Bandit subset | No suppressed critical findings without explicit issue link. |

## Type Guidelines
- New Python code must be fully typed (functions, public attrs). Use `from __future__ import annotations` if needed (not yet required globally).
- Avoid `Any` in new code. If unavoidable (dynamic plugin, 3rd‑party gap), contain it at the boundary and document with a comment.
- Prefer `Protocol` for structural interfaces over inheritance when only behavior matters.
- Use `TypedDict` for JSON-like structures crossing trust/runtime boundaries.
- Keep `# type: ignore` extremely rare; always specify code location and justification (e.g. `# type: ignore[attr-defined]  # opentelemetry optional`), then follow up with a TODO if resolvable.

## Lint / Style
- Ruff covers style + import sorting; do not run isort / black separately—`ruff format` suffices.
- Limit line length to configured default (respect existing config).
- Use meaningful variable names (avoid one-letter except i, j in small loops or math contexts).
- Log exceptions with context; avoid bare `except:` blocks.

## Testing
- Add tests for all non-trivial logic (branching, error handling, protocol transforms).
- Use property/fuzz tests for codec / frame parsing changes.
- Keep test runtime lean; long‑running scenarios belong in separate soak / load scripts invoked explicitly.
- When adding a new adapter or backend: include a health/readiness + conformance test.

## Observability & Metrics
- Add counters/gauges/histograms for new subsystems with clear naming (prefix with feature area if ambiguous).
- Set span attributes (tokens, usd, qos, model) when crossing major pipeline stages.

## Security
- Never commit secrets. Use env var placeholders or test-only deterministic keys clearly labeled.
- Validate and sanitize external input early (PII masking, allowlists, quotas).
- Document any new external network call and ensure timeouts.

## Adding Dependencies
- Keep dependencies minimal. Justify large or security‑sensitive additions in the PR description.
- Pin indirect tooling versions in lock files where applicable.

## Commit & PR Process
1. Small, focused commits; descriptive messages.
2. Reference TODO IDs or GAP IDs when closing roadmap items.
3. PR must pass: lint, type, tests. Add/update docs for externally visible behaviour.
4. Include a short “Risk & Rollback” note in the PR if change impacts runtime paths.

## Release Hygiene
- Update CHANGELOG (if present) for user-visible changes.
- Regenerate SBOM / signatures when dependency graph changes.

## Handling `noqa` / Ignores
- Allowed only with justification. Periodically we prune them—expect questions if unclear.

## FAQ
Q: A third‑party module lacks type hints and mypy fails.
A: Add `ignore_missing_imports` for that module in `mypy.ini` OR create a minimal stub in `typings/` and document.

Q: My new async background thread accessor races in tests.
A: Provide a hook for injection / awaitable startup or gate with an event.

Thank you for contributing! Keep it clean, observable, and predictable.
