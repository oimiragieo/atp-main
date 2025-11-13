# ATP Virtual Appliance Implementation Plan (Deep Detail)

This document is an execution playbook for an autonomous AI agent to build ATP virtual appliances (VM image / AMI / OVA / QCOW2) plus a programmable operator CLI (`atpctl`). It encodes: ordering, dependencies, file mapping, acceptance tests, and failure rollback strategies.

---
## Legend

- [ ] Not started  
- [~] In progress / draft  
- [x] Complete  
- (R) Requires decision / clarification  
- (★) High impact / critical path  
- (B) Build artifact produced  
- (V) Verification step  

---
## 0. High-Level Dependency Graph

```text
Phase 0 (scaffold, ADR) --> Phase 1 (layout spec, schema) --> Phase 2 (CLI core) --> Phase 3 (systemd units)
	|                                                   |                          \
	+------------> Phase 4 (packer base) <--------------+---------------------------> Phase 5 (upgrade)
							   |                                  \
							   +--> Phase 6 (observability) --> Phase 7 (hardening)
												    \
												     Phase 8 (advanced)
```

Hard prerequisites:

1. Layout spec (P1-1) before any provisioning scripts.

## 19. Agent-Executable Playbook (Atomic steps)

This section converts the plan into atomic, ordered steps with preconditions, commands, expected artifacts, verification, and failure handling. Each step emits a machine-parseable line to stdout so an orchestration engine can track progress.

Use the following machine token format (presented in human-friendly form):

`APPLIANCE_STEP:` `<step-id>` `:` `<START|OK|FAIL>` `:` `<optional-json>`

Where `<optional-json>` is a small JSON payload with keys such as:

```json
{"artifact":"path","elapsed_s":123,"notes":"..."}
```

All shell commands below are POSIX sh style and must be executed inside a Linux build host (Packer/VM). If your orchestration runs on Windows, use WSL or a Linux runner.

Step preconditions are explicit. Do NOT copy or move production code until the specified precondition is satisfied.

Each numbered step below is atomic and idempotent where feasible. Steps that create artifacts write to `artifacts/` under the appliance folder for CI pickup.

19.1 A0-1: Create skeleton directories (atomic)

- Preconditions: repo root writable.

- Action (commands):

```sh
APPLIANCE_STEP:A0-1:START
mkdir -p atp-main-appliance/{adr,bin,packer,provision,schemas,systemd,cloud-init,upgrade,atpctl,docs,tests,artifacts}
touch atp-main-appliance/adr/.gitkeep
touch atp-main-appliance/bin/.gitkeep
touch atp-main-appliance/provision/.gitkeep
echo '{"created_by":"agent","time":"'"$(date -u)"'"}' > atp-main-appliance/artifacts/skeleton.json
```



```sh
APPLIANCE_STEP:A0-2:START
cat > atp-main-appliance/adr/0001-template.md <<'EOF'
## ADR-0001: [Title]

Context: ...

Decision: ...

Consequences: ...
EOF
git add atp-main-appliance/adr/0001-template.md && git commit -m "appliance: add ADR template" || true
APPLIANCE_STEP:A0-2:OK
```

- Verification: file exists; optional commit hash in artifact.

19.3 P1-1: Author `docs/layout.md` (canonical layout)

- Preconditions: A0-1.

- Action (generate from template; do not move repo code):

```sh
APPLIANCE_STEP:P1-1:START
cat > atp-main-appliance/docs/layout.md <<'EOF'
Paths:
- /opt/atp/releases/<version>/  (immutable release)
- /opt/atp/current -> /opt/atp/releases/<version> (symlink)
- /etc/atp/ (config, env)
- /etc/atp/secrets.d/ (0400 files)
- /var/log/atp/
EOF
APPLIANCE_STEP:P1-1:OK:{"artifact":"atp-main-appliance/docs/layout.md"}
```

- Verification: file present.

19.4 P1-4: Generate minimal `router_config.schema.json` (read-only generation)

- Preconditions: A0-1, ability to run Python. DO NOT change `router_service` yet.

- Action: create a minimal schema capturing env keys the router expects (seed only), then iterate.

```sh
APPLIANCE_STEP:P1-4:START
cat > atp-main-appliance/schemas/router_config.schema.json <<'EOF'
{
	"$schema": "http://json-schema.org/draft-07/schema#",
	"type": "object",
	"properties": {
		"ROUTER_ADMIN_API_KEY": {"type":"string"},
		"ROUTER_MODEL_REGISTRY_WATCH": {"type":"boolean"}
	},
	"required": ["ROUTER_ADMIN_API_KEY"]
EOF
APPLIANCE_STEP:P1-4:OK:{"artifact":"atp-main-appliance/schemas/router_config.schema.json"}
```

- Verification: jsonschema CLI or Python `jsonschema.validate` passes for sample file.

19.5 P2-1: Scaffold `atpctl` Typer project (no runtime wiring)

- Preconditions: Python3 available on build host.

- Action:

```sh
APPLIANCE_STEP:P2-1:START
mkdir -p atp-main-appliance/atpctl/atpctl/commands
cat > atp-main-appliance/atpctl/pyproject.toml <<'EOF'
[project]
name = "atpctl"
version = "0.0.0"
dependencies = ["typer[all]", "httpx", "jsonschema", "PyYAML"]
EOF
cat > atp-main-appliance/atpctl/atpctl/main.py <<'EOF'
import typer
app = typer.Typer()

@app.command()
def status():
	print('{"status":"stub"}')

if __name__ == '__main__':
	app()
EOF
APPLIANCE_STEP:P2-1:OK:{"artifact":"atp-main-appliance/atpctl/pyproject.toml"}
```

- Verification: `python -m atpctl.main` prints stub.

19.6 P3-1: Create systemd unit templates (draft)

- Preconditions: P1-1 done.

- Action: write templated units under `systemd/` (do not install on host).
```sh
APPLIANCE_STEP:P3-1:START

[Service]
User=atp
Group=atp
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
EnvironmentFile=/etc/atp/atp.env
ExecStart=/opt/atp/current/venv/bin/python -m router_service.service
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
APPLIANCE_STEP:P3-1:OK:{"artifact":"atp-main-appliance/systemd/atp-router.service"}
```


Include them in schema under `runtime.env_overrides` with type & default.

---
## 5. Phase 2: CLI (atpctl) Core (★)

**Goal:** Provide operator surface for status + config mgmt + models.**

### Command Matrix
| Command | Description | Dependencies | Exit Codes |
|---------|-------------|--------------|------------|
| status | Aggregate `/healthz`, `/state_health`, derive degraded vs ok | Running router service (mock allowed) | 0 ok, 3 degraded, 4 error |
| config validate | Validate JSON/YAML against schema | P1-4 | 0 valid, 2 invalid |
| config diff | Compare on-disk vs proposed file | P1-6 | 0 no diff, 1 diff |
| config apply | Validate -> atomic write -> optional reload endpoint | P1-5 | 0 success, 2 invalid |
| models list | Query admin model status endpoint | Router running | 0 success |
| models promote/demote | POST admin endpoints | Auth key present | 0 success, 4 fail |
| diag bundle | Tar logs, config, metrics, redacting secrets | P1-6 | 0 success |
| upgrade plan | Show current vs target versions | P5-1 | 0 success |
| upgrade apply | Validate bundle, switch symlink | P5-2, P5-3 | 0 success, 4 failure |

### Implementation Order
1. P2-1 Create `pyproject.toml` with Typer + jsonschema deps pinned.  
2. P2-2 Implement `main.py` Typer app & basic `status` skeleton returning static structure.  
3. P2-3 Add HTTP client wrapper (requests or httpx) with timeout + admin key injection.  
4. P2-4 Implement config subcommands using schema.  
5. P2-5 Add model management (use existing endpoints from router service admin area).  
6. P2-6 Add diag bundler (exclude secrets by regex: `(?i)(key|token|secret)` replacement `***`).  
7. P2-7 Add output format negotiation (`--format json|yaml|table`).  

### Tests
| Test | Scenario | Assertions |
|------|----------|------------|
| test_status_ok | Mock endpoints healthy | exit=0, `status: ok` |
| test_status_degraded | Inject one failing endpoint | exit=3 |
| test_config_validate_invalid | Bad field triggers error | exit=2, stderr contains path |
| test_models_promote | Mock promote returns 200 | success msg |

---
## 6. Phase 3: System Services & Hardening (★)

**Goal:** Run components as managed systemd units with secure defaults.**

### Units to Create
1. `atp-router.service`
2. `atp-memory.service` (optional if memory-gateway distinct)
3. `atp-admin.service`

### Common Unit Hardening Fields
```
[Service]
User=atp
Group=atp
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
AmbientCapabilities=
CapabilityBoundingSet=
EnvironmentFile=/etc/atp/atp.env
ExecStart=/opt/atp/current/venv/bin/python -m router_service.service
WorkingDirectory=/opt/atp/current
Restart=on-failure
RestartSec=3
```

### Tasks
| ID | Task | Steps | Depends | Acceptance |
|----|------|-------|---------|------------|
| P3-1 | Router unit draft | Place file under `systemd/`; copy during provisioning | P2 status | systemctl start succeeds |
| P3-2 | Admin aggregator unit | ExecStart points to aggregator app | P3-1 | `/routers` returns list |
| P3-3 | Memory-gateway unit | Use its app module | P3-1 | `/healthz` returns 200 |
| P3-4 | Permissions script | Ensure chown on /var/lib/atp, /var/log/atp | P1-2 | Script idempotent |
| P3-5 | Secret perms audit | `bin/atp-check-perms` scanning 0600/0400 | P3-4 | Non-zero on violation |
| P3-6 | TLS bootstrap (R) | Self-signed via openssl; store cert/key in secrets.d | Decision | Cert present |
| P3-7 | Watchdog (optional) | Add WatchdogSec + /healthz ping | P3-1 | systemd logs no watchdog timeouts |

---
## 7. Phase 4: Build Automation & Images (★)

**Goal:** Produce reproducible VM images with CI smoke tests.**

### Packer Template Outline (`packer/atp-qemu.pkr.hcl`)
```
variable "version" { type = string }
source "qemu" "atp" {
	iso_url      = "https://cloud-images.ubuntu.com/minimal/releases/24.04/release/ubuntu-24.04-minimal-cloudimg-amd64.img"
	output_directory = "build/qemu"
	ssh_username = "ubuntu"
	headless = true
	disk_size = 4096
}
build {
	sources = ["source.qemu.atp"]
	provisioner "shell" { script = "provision/00-base-deps.sh" }
	provisioner "shell" { script = "provision/05-python-env.sh" }
	provisioner "shell" { script = "provision/10-permissions.sh" }
	provisioner "shell" { script = "provision/15-copy-code.sh" }
	provisioner "shell" { script = "provision/20-install-systemd.sh" }
	provisioner "shell" { script = "provision/25-config-seed.sh" }
	provisioner "shell" { script = "provision/30-post-verify.sh" }
	post-processor "manifest" {}
}
```

### Provision Script Ordering Constraints
| Script | Must Occur After | Reason |
|--------|------------------|--------|
| 00-base-deps.sh | None | Base packages + useradd |
| 05-python-env.sh | 00 | Needs python & user for ownership |
| 10-permissions.sh | 05 | Venv directory created |
| 15-copy-code.sh | 05 | Code goes into /opt/atp/releases/<ver> |
| 20-install-systemd.sh | 15 | Units reference code paths |
| 25-config-seed.sh | 20 | Config relies on service paths |
| 30-post-verify.sh | All prior | Final smoke test pre-image finalize |

### Smoke Test Checklist (30-post-verify.sh)
1. `systemctl enable atp-router`  
2. `systemctl start atp-router`  
3. Wait for `/healthz` (curl 127.0.0.1:7443/healthz)  
4. Run `/usr/bin/atpctl status --json` expect `status":"ok`  
5. Stop service, confirm clean journal (no ERROR).  

---
## 8. Phase 5: Upgrade & Rollback Mechanism (★)

**Goal:** Transactional version switching with integrity.**

### Bundle Layout
```
bundle-
	metadata.json (version, build_time, sha256 map)
	files/
		venv/**
		router_service/**
		admin_aggregator/**
		memory_gateway/**
	post_install.sh (optional hooks)
	LICENSE
```

### Algorithm (upgrade apply)
1. Verify free disk space > size(bundle) * 2.  
2. Extract to `/opt/atp/releases/<version>.staging`.  
3. Hash every file; compare with metadata.json; abort on mismatch.  
4. Symlink update: move `/opt/atp/current` -> `<version>.staging` atomically to `<version>`.  
5. Run `systemctl restart atp-router`.  
6. Probe health; if fail within timeout revert symlink to previous version.  
7. Log audit record JSON to `/var/log/atp/audit.log`.  

### Rollback Logic
Store previous target in `/opt/atp/.previous`. If rollback triggered or explicit command, re-point symlink and restart.

---
## 9. Phase 6: Extended Observability & Diagnostics

Additions rely on stable CLI.

| Task | Description | Technical Notes | Depends |
|------|-------------|-----------------|---------|
| Metrics snapshot | New admin route returns structured JSON (counters, gauges) | Leverage existing REGISTRY.export() | Router service stable |
| Trace toggle | Set env flag or in-memory switch through admin endpoint | Add ephemeral flag storage | CLI upgrade done |
| Log level set | Endpoint sets logger level | Use StructuredLogger instance | CLI base |
| Session purge | Expose endpoint to clear `_SESSION_ACTIVE` | Rate-limit admin action | Security review |

---
## 10. Phase 7: Security Hardening & Compliance

| Control | Implementation | Test |
|---------|----------------|------|
| Read-only root | Mount remount + overlay except /var /etc/atp | Boot script toggles; attempt write to /opt fails |
| Minimal Python | Build wheels offline; remove pip cache | Image size diff < target | 
| Vulnerability gating | Run `pip-audit` & `syft` on artifact | CI fails on HIGH |
| Secret rotation | Document & script replacing admin.key without restart (hot-reload) | CLI rotates and validates |

---
## 11. Phase 8: Advanced / Optional

Summarized earlier; defer until MVP stable.

---
## 12. Cross-Cutting Quality Gates

| Gate | Tooling | Threshold |
|------|---------|-----------|
| Lint | ruff/black | No new warnings |
| Types | mypy | No errors in `atpctl` |
| Tests | pytest | ≥80% CLI lines |
| Image smoke | custom script | <60s health pass |
| Upgrade rollback | integration test | Reverts w/o data loss |

---
## 13. Automation Make Targets

| Target | Action | Depends |
|--------|--------|---------|
| `make venv` | Create dev venv for appliance work | python3 | 
| `make cli` | Install editable atpctl | venv |
| `make lint` | Run ruff + mypy | venv |
| `make packer-qemu` | Build QCOW2 image | packer installed |
| `make smoke` | Boot local QEMU + run status | packer-qemu |
| `make sbom` | Generate SBOM artifact | syft decision |
| `make audit` | pip-audit + license scan | venv |

---
## 14. Step-by-Step Execution Script (Agent Friendly)

Pseudo-sequenced macro steps (stop if any fails):
1. Phase0: create directory skeleton → add ADR template → commit.  
2. Phase1: write layout.md → implement schemas → implement atomic write script → add migration hook.  
3. Phase2: scaffold atpctl (Typer) → add status command (mock) → implement config validate (jsonschema) → add real HTTP integration.  
4. Phase3: draft systemd units → write permission script → local manual dry-run (simulate systemd with `ExecStart` command only).  
5. Phase4: write packer template → create provision scripts in order → packer build → run smoke test script.  
6. Phase5: specify bundle format → implement `upgrade plan/apply/rollback` → create dummy bundle for test → run upgrade integration test.  
7. Phase6+: add metrics snapshot endpoint & CLI -> add trace toggle.  
8. Phase7: implement read-only root test harness → finalize security docs.  

Each step: produce log line `APPLIANCE_STEP:<id>:<status>` for machine parsing.

---
## 15. Risk Register (Expanded)

| Risk | Likelihood | Impact | Mitigation | Fallback |
|------|------------|--------|-----------|----------|
| Schema drift vs code | Medium | High | Generate schema from annotated dataclasses later | Manual sync review |
| Packer upstream image change | Medium | Medium | Pin SHA256 of base image | Fallback mirror |
| CLI dependency CVE | Medium | Medium | Weekly pip-audit cron | Auto bump PR |
| Symlink race on upgrade | Low | High | Use `ln -sfn` + fsync directory | Lock file around apply |
| Log PII in diag bundle | Low | High | Redaction regex + allowlist | Manual review step |

---
## 16. Open Decisions (Active)

- SBOM: (R) syft vs cyclonedx (choose syft for multi-ecosystem).  
- TLS issuance: (R) self-signed default; documented replacement.  
- Distribution channel: (R) static HTTPS vs OCI artifact (consider OCI for provenance).  
- gRPC mgmt timeline: (R) post hardening.  
- Model registry HA: (R) external DB vs file replication (phase after MVP).  

---
## 17. Quick Future README Snippet

```
virt-install --name atp --memory 2048 --disk path=atp-appliance-<ver>.qcow2 --import --noautoconsole
cloud-init ssh into host then:
sudo atpctl status --json
sudo atpctl models list
```

---
## 18. Immediate Next Actions

1. Execute A0-1 through A0-3.  
2. Draft layout doc (P1-1).  
3. Start schema (P1-4) with minimal required fields (admin key, model registry path).  
4. Scaffold atpctl with empty status command (P2-1..P2-2).  

---
*(End of deep plan)*

---
## 19. Agent-Executable Playbook (Atomic steps)

This section converts the plan into atomic, ordered steps with preconditions, commands, expected artifacts, verification, and failure handling. Each step emits a machine-parseable line to stdout so an orchestration engine can track progress:

APPLIANCE_STEP:<step-id>:<START|OK|FAIL>:<optional-json>

Where <optional-json> is a small JSON payload with keys: {"artifact":"path","elapsed_s":N,"notes":"..."}

All shell commands below are POSIX sh style and must be executed inside a Linux build host (Packer/VM). If your orchestration runs on Windows, use WSL or a Linux runner.

Step preconditions are explicit. Do NOT copy or move production code until the specified precondition is satisfied.

Each numbered step below is atomic and idempotent where feasible. Steps that create artifacts write to `artifacts/` under the appliance folder for CI pickup.

19.1 A0-1: Create skeleton directories (atomic)
- Preconditions: repo root writable.  
- Action (commands):
```sh
APPLIANCE_STEP:A0-1:START
mkdir -p atp-main-appliance/{adr,bin,packer,provision,schemas,systemd,cloud-init,upgrade,atpctl,docs,tests,artifacts}
touch atp-main-appliance/adr/.gitkeep
touch atp-main-appliance/bin/.gitkeep
touch atp-main-appliance/provision/.gitkeep
echo '{"created_by":"agent","time":"'"$(date -u)"'"}' > atp-main-appliance/artifacts/skeleton.json
APPLIANCE_STEP:A0-1:OK:{"artifact":"atp-main-appliance/artifacts/skeleton.json"}
```
- Verification: check existence of directories and `artifacts/skeleton.json`.
- Failure: log and abort.

19.2 A0-2: Commit ADR template
- Preconditions: A0-1 done. Git available.
- Action:
```sh
APPLIANCE_STEP:A0-2:START
cat > atp-main-appliance/adr/0001-template.md <<'EOF'
## ADR-0001: [Title]

Context: ...

Decision: ...

Consequences: ...
EOF
git add atp-main-appliance/adr/0001-template.md && git commit -m "appliance: add ADR template" || true
APPLIANCE_STEP:A0-2:OK
```
- Verification: file exists; optional commit hash in artifact.

19.3 P1-1: Author `docs/layout.md` (canonical layout)
- Preconditions: A0-1.  
- Action (generate from template; do not move repo code):
```sh
APPLIANCE_STEP:P1-1:START
cat > atp-main-appliance/docs/layout.md <<'EOF'
Paths:
- /opt/atp/releases/<version>/  (immutable release)
- /opt/atp/current -> /opt/atp/releases/<version> (symlink)
- /etc/atp/ (config, env)
- /etc/atp/secrets.d/ (0400 files)
- /var/lib/atp/ (persistent runtime state)
- /var/log/atp/
EOF
APPLIANCE_STEP:P1-1:OK:{"artifact":"atp-main-appliance/docs/layout.md"}
```
- Verification: file present.

19.4 P1-4: Generate minimal `router_config.schema.json` (read-only generation)
- Preconditions: A0-1, ability to run Python. DO NOT change `router_service` yet.  
- Action: create a minimal schema capturing env keys the router expects (seed only), then iterate.
```sh
APPLIANCE_STEP:P1-4:START
cat > atp-main-appliance/schemas/router_config.schema.json <<'EOF'
{
	"$schema": "http://json-schema.org/draft-07/schema#",
	"type": "object",
	"properties": {
		"ROUTER_ADMIN_API_KEY": {"type":"string"},
		"ROUTER_MODEL_REGISTRY_WATCH": {"type":"boolean"}
	},
	"required": ["ROUTER_ADMIN_API_KEY"]
}
EOF
APPLIANCE_STEP:P1-4:OK:{"artifact":"atp-main-appliance/schemas/router_config.schema.json"}
```
- Verification: jsonschema CLI or Python `jsonschema.validate` passes for sample file.

19.5 P2-1: Scaffold `atpctl` Typer project (no runtime wiring)
- Preconditions: Python3 available on build host.  
- Action:
```sh
APPLIANCE_STEP:P2-1:START
mkdir -p atp-main-appliance/atpctl/atpctl/commands
cat > atp-main-appliance/atpctl/pyproject.toml <<'EOF'
[project]
name = "atpctl"
version = "0.0.0"
dependencies = ["typer[all]", "httpx", "jsonschema", "PyYAML"]
EOF
cat > atp-main-appliance/atpctl/atpctl/main.py <<'EOF'
import typer
app = typer.Typer()

@app.command()
def status():
		print('{"status":"stub"}')

if __name__ == '__main__':
		app()
EOF
APPLIANCE_STEP:P2-1:OK:{"artifact":"atp-main-appliance/atpctl/pyproject.toml"}
```
- Verification: `python -m atpctl.main` prints stub.

19.6 P3-1: Create systemd unit templates (draft)
- Preconditions: P1-1 done.  
- Action: write templated units under `systemd/` (do not install on host).
```sh
APPLIANCE_STEP:P3-1:START
cat > atp-main-appliance/systemd/atp-router.service <<'EOF'
[Unit]
Description=ATP Router Service
After=network.target

[Service]
User=atp
Group=atp
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
EnvironmentFile=/etc/atp/atp.env
ExecStart=/opt/atp/current/venv/bin/python -m router_service.service
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
APPLIANCE_STEP:P3-1:OK:{"artifact":"atp-main-appliance/systemd/atp-router.service"}
```

19.7 P4-1: Draft Packer template & provisioner skeleton (NO build yet)
- Preconditions: P1-1, P3-1.  
- Action: create `packer/` files with placeholders; do not run packer until provision scripts exist and validated.
```sh
APPLIANCE_STEP:P4-1:START
cat > atp-main-appliance/packer/atp-qemu.pkr.hcl <<'EOF'
variable "version" { type = string }
source "qemu" "atp" {}
build { sources = ["source.qemu.atp"] }
EOF
APPLIANCE_STEP:P4-1:OK:{"artifact":"atp-main-appliance/packer/atp-qemu.pkr.hcl"}
```

19.8 P4-2: Implement provision scripts in order (atomic files)
- Preconditions: P4-1. DO NOT copy repo code until `15-copy-code.sh` step executed.  
- Action: create skeleton provision scripts and enforce ordering with `set -e`.
```sh
APPLIANCE_STEP:P4-2:START
cat > atp-main-appliance/provision/00-base-deps.sh <<'EOF'
#!/bin/sh
set -e
apt-get update
apt-get install -y python3 python3-venv python3-pip jq curl tar unzip openssl
useradd --system --create-home --home-dir /var/lib/atp -M atp || true
EOF
cat > atp-main-appliance/provision/05-python-env.sh <<'EOF'
#!/bin/sh
set -e
python3 -m venv /opt/atp/venv
/opt/atp/venv/bin/pip install -U pip
EOF
cat > atp-main-appliance/provision/15-copy-code.sh <<'EOF'
#!/bin/sh
set -e
# This script runs *inside* packer VM and expects repo bundle to be available at /tmp/repo
REPO_DIR=/tmp/repo
VER="$1"
TARGET=/opt/atp/releases/$VER
mkdir -p "$TARGET"
cp -a "$REPO_DIR"/router_service "$TARGET/"
cp -a "$REPO_DIR"/memory-gateway "$TARGET/" || true
cp -a "$REPO_DIR"/admin_aggregator "$TARGET/" || true
/opt/atp/venv/bin/python -m pip install -r "$REPO_DIR"/requirements.txt --target "$TARGET/venv-packages" || true
EOF
APPLIANCE_STEP:P4-2:OK
```
- Verification: files present, executable bit set.

19.9 P4-3: Copy-only step (guarded) — move repo into staging area inside image
- Preconditions: provision/15-copy-code.sh exists and is tested in VM; DO NOT run on host.
- Action: executed by packer during build.

19.10 P4-4: Smoke test script (post-verify)
- Preconditions: `systemd` unit files in place and services started.  
- Action:
```sh
APPLIANCE_STEP:P4-4:START
# Wait for health endpoint with timeout
for i in 1 2 3 4 5; do
	if curl -fsS http://127.0.0.1:7443/healthz; then
		APPLIANCE_STEP:P4-4:OK
		exit 0
	fi
	sleep 2

### Command Matrix

| Command | Description | Dependencies | Exit Codes |
|---------|-------------|--------------|------------|
| status | Aggregate `/healthz`, `/state_health`, derive degraded vs ok | Running router service (mock allowed) | 0 ok, 3 degraded, 4 error |
| config validate | Validate JSON/YAML against schema | P1-4 | 0 valid, 2 invalid |
| config diff | Compare on-disk vs proposed file | P1-6 | 0 no diff, 1 diff |
| config apply | Validate -> atomic write -> optional reload endpoint | P1-5 | 0 success, 2 invalid |
| models list | Query admin model status endpoint | Router running | 0 success |
| models promote/demote | POST admin endpoints | Auth key present | 0 success, 4 fail |
| diag bundle | Tar logs, config, metrics, redacting secrets | P1-6 | 0 success |
| upgrade plan | Show current vs target versions | P5-1 | 0 success |
| upgrade apply | Validate bundle, switch symlink | P5-2, P5-3 | 0 success, 4 failure |
cd "$STAGING"
# validate hashes in metadata.json
python3 - <<'PY'
import json,hashlib,sys,os
md=json.load(open('metadata.json'))
for f,h in md.get('sha256',{}).items():
	if hashlib.sha256(open(f,'rb').read()).hexdigest()!=h:
		print('hash mismatch',f)
		sys.exit(2)
print('ok')
PY
ln -sfn "$STAGING" /opt/atp/current
systemctl restart atp-router || true
sleep 3
if curl -fsS http://127.0.0.1:7443/healthz; then
	APPLIANCE_STEP:P5-2:OK
else
	# rollback
	APPLIANCE_STEP:P5-2:FAIL
	exit 3
fi
```

19.12 P6-1: Add metrics snapshot endpoint
- Preconditions: router service code writable in working tree (developer phase). Make no changes until P4-2 is tested.  
- Guidance: implement endpoint `/admin/metrics_snapshot` that returns JSON of relevant metrics (counters, histograms). Add feature flag via env `ENABLE_METRICS_SNAPSHOT` default false.

19.13 P7-1: Security gating (CI)
- Preconditions: artifacts produced.  
- Action: run `pip-audit --json > artifacts/pip_audit.json` and `syft packages dir:/opt/atp/releases/<ver> -o json > artifacts/sbom.json` and fail if HIGH vulns.

---
## 20. Dependency Manifest (Tools & Versions)

Agent must ensure these tools are installed on the build host (CI runner or local):

- packer >= 1.9  (for `packer` builds)
- qemu-img, qemu-system-x86_64  (for QCOW2 builds)
- virt-install (optional for local smoke boot)
- python3.11 or python3.10
- pip, python3-venv
- jq, curl, tar, unzip, openssl
- cosign (for signing artifacts)
- syft (SBOM generation)
- pip-audit (vuln scanning)
- git

Package versions that the agent should pin in CI matrix (recommendation):
- python: 3.11
- packer: latest stable pinned in CI image
- syft: 0.80+
- cosign: 2.0+
- pip-audit: 2.0+

Install examples (Debian/Ubuntu):
```sh
sudo apt-get update; sudo apt-get install -y qemu-utils qemu-system-x86 virtinst jq curl unzip git python3 python3-venv python3-pip openssl
pip3 install --user packer-python-cli syft pip-audit
```

---
## 21. File-level Mapping (Concrete)

The agent must map repo files into the appliance release layout. Do not move files in the repo—copy into release staging during packer/`15-copy-code.sh`.

Key mappings (source -> release target):

- `router_service/service.py` -> `/opt/atp/releases/<ver>/router_service/service.py`  (entrypoint)
- `router_service/config_hot_reload.py` -> `/opt/atp/releases/<ver>/router_service/config_hot_reload.py`
- `router_service/__init__.py` -> `/opt/atp/releases/<ver>/router_service/__init__.py`
- `memory-gateway/*` -> `/opt/atp/releases/<ver>/memory_gateway/` (if present)
- `client/*` -> `/opt/atp/releases/<ver>/client/` (CLI helpers retained)
- `atp-main-appliance/atpctl/*` (scaffold) -> `/opt/atp/releases/<ver>/tools/atpctl/` then install entry to `/usr/bin/atpctl`
- `requirements.txt` -> `/opt/atp/releases/<ver>/requirements.txt`
- `data/*` seed files -> `/usr/share/atp/seed/`
- `docs/*` (selected) -> `/usr/share/doc/atp/`

Special note: runtime-only artifacts (counters, lifecycle) MUST be created under `/var/lib/atp/` on first boot by a systemd pre-start hook. The provisioner must not pre-populate `/var/lib/atp` unless migrating an existing installation.

---
## 22. Safety Rules & Preconditions (Agent must enforce)

1. Never change repository source files in-place. Instead, copy into release staging inside the image during `15-copy-code.sh`.  
2. Always validate schema (P1-4) before applying config.  
3. All secrets must land in `/etc/atp/secrets.d` with perms 0400. The provision scripts must set those perms.  
4. Use `ln -sfn` for atomic symlink switch and `fsync` the parent dir where possible.  
5. When restarting services during upgrade, implement a health gate (probe TTL) and automatic rollback on failure.  
6. Emit APPLIANCE_STEP status lines after each atomic action for orchestration parsing.

---
## 23. Failure Modes & Recovery

- Hash mismatch during bundle verify -> mark step FAIL, delete staging folder, keep previous symlink.  
- service restart causes crash loop -> rollback symlink and surface journal entries to `artifacts/rollback-<time>.log` and mark FAIL.  
- packer provision step fails -> capture `packer/log.json` into `artifacts/` and stop build.  

---
## 24. Quick Agent Checklist (before running)

- [ ] Ensure Linux build host (WSL/CI) with required packages (see dependency manifest).  
- [ ] Create a dedicated build user with sudo access in CI.  
- [ ] Do not run `15-copy-code.sh` on developer machine—only inside packer VM or staging container.  
- [ ] Confirm `ROUTER_ADMIN_API_KEY` is present in example config for tests, but never commit real keys.  

---
## 25. Next immediate automated work I can do now

1. Create the scaffold files listed in the `atp-main-appliance/` skeleton (I already created TODO and many placeholders).  
2. Scaffold `provision/*` scripts with strict `set -euo pipefail` and basic idempotent checks.  
3. Create a minimal packer build that runs the skeleton provision scripts but does not copy code yet (dry-run).  


---
## Phase-by-Phase Atomic Actions (Agent Execution Blueprint)

### Phase 0: Foundations & Scaffolding

**Step 1: Scaffold Directories**
- Prerequisites: repo root writable
- Inputs: None
- Outputs: directory tree, `artifacts/skeleton.json`
- APPLIANCE_STEP:A0-1:START
- Commands:
	- `mkdir -p ...` (see skeleton)
	- `touch .gitkeep` in empty dirs
	- `echo ... > artifacts/skeleton.json`
- Verification: `test -d atp-main-appliance/adr` etc.
- APPLIANCE_STEP:A0-1:OK
- Rollback: `rm -rf atp-main-appliance/*`
- CI: Upload `artifacts/skeleton.json`

**Step 2: ADR Template**
- Prerequisites: A0-1:OK
- Inputs: None
- Outputs: `adr/0001-template.md`
- APPLIANCE_STEP:A0-2:START
- Commands:
	- `cat > adr/0001-template.md <<EOF ... EOF`
	- `git add ... && git commit ... || true`
- Verification: `test -f adr/0001-template.md`
- APPLIANCE_STEP:A0-2:OK
- Rollback: `rm adr/0001-template.md`
- CI: Upload ADR file

### Phase 1: Runtime Layout & Packaging Model

**Step 3: Directory Spec Doc**
- Prerequisites: A0-1:OK
- Inputs: None
- Outputs: `docs/layout.md`
- APPLIANCE_STEP:P1-1:START
- Commands:
	- `cat > docs/layout.md <<EOF ... EOF`
- Verification: `grep /opt/atp docs/layout.md`
- APPLIANCE_STEP:P1-1:OK
- Rollback: `rm docs/layout.md`
- CI: Upload doc

**Step 4: User/Group Creation**
- Prerequisites: P1-1:OK
- Inputs: None
- Outputs: system user `atp`
- APPLIANCE_STEP:P1-2:START
- Commands:
	- `id -u atp || useradd --system ...`
- Verification: `id -u atp`
- APPLIANCE_STEP:P1-2:OK
- Rollback: `userdel atp`
- CI: Log user creation

**Step 5: Config Schema**
- Prerequisites: P1-1:OK
- Inputs: None
- Outputs: `schemas/router_config.schema.json`
- APPLIANCE_STEP:P1-4:START
- Commands:
	- `cat > schemas/router_config.schema.json <<EOF ... EOF`
- Verification: `jsonschema validate ...`
- APPLIANCE_STEP:P1-4:OK
- Rollback: `rm schemas/router_config.schema.json`
- CI: Upload schema

### Phase 2: CLI Core

**Step 6: atpctl CLI Scaffold**
- Prerequisites: Python3 available
- Inputs: None
- Outputs: `atpctl/pyproject.toml`, `atpctl/atpctl/main.py`
- APPLIANCE_STEP:P2-1:START
- Commands:
	- `mkdir -p atpctl/atpctl/commands`
	- `cat > atpctl/pyproject.toml <<EOF ... EOF`
	- `cat > atpctl/atpctl/main.py <<EOF ... EOF`
- Verification: `python -m atpctl.main` prints stub
- APPLIANCE_STEP:P2-1:OK
- Rollback: `rm -rf atpctl/*`
- CI: Run CLI stub, upload output

### Phase 3: System Services & Hardening

**Step 7: Systemd Unit Draft**
- Prerequisites: P2-1:OK
- Inputs: None
- Outputs: `systemd/atp-router.service`
- APPLIANCE_STEP:P3-1:START
- Commands:
	- `cat > systemd/atp-router.service <<EOF ... EOF`
- Verification: `grep ExecStart systemd/atp-router.service`
- APPLIANCE_STEP:P3-1:OK
- Rollback: `rm systemd/atp-router.service`
- CI: Upload unit file

### Phase 4: Build Automation & Images

**Step 8: Packer Template**
- Prerequisites: P3-1:OK
- Inputs: None
- Outputs: `packer/atp-qemu.pkr.hcl`
- APPLIANCE_STEP:P4-1:START
- Commands:
	- `cat > packer/atp-qemu.pkr.hcl <<EOF ... EOF`
- Verification: `grep qemu packer/atp-qemu.pkr.hcl`
- APPLIANCE_STEP:P4-1:OK
- Rollback: `rm packer/atp-qemu.pkr.hcl`
- CI: Upload packer file

**Step 9: Provision Scripts**
- Prerequisites: P4-1:OK
- Inputs: None
- Outputs: `provision/*.sh`
- APPLIANCE_STEP:P4-2:START
- Commands:
	- `cat > provision/00-base-deps.sh <<EOF ... EOF` etc.
- Verification: `test -x provision/00-base-deps.sh`
- APPLIANCE_STEP:P4-2:OK
- Rollback: `rm provision/*.sh`
- CI: Upload provision scripts

**Step 10: Copy Repo to Staging**
- Prerequisites: P4-2:OK
- Inputs: repo tarball
- Outputs: `/opt/atp/releases/<ver>/...` tree
- APPLIANCE_STEP:P4-3:START
- Commands:
	- `tar -xzf ... && cp -a ...`
- Verification: `test -f /opt/atp/releases/<ver>/router_service/service.py`
- APPLIANCE_STEP:P4-3:OK
- Rollback: `rm -rf /opt/atp/releases/<ver>`
- CI: Upload tree manifest

**Step 11: Smoke Test**
- Prerequisites: P4-3:OK
- Inputs: None
- Outputs: `artifacts/post-verify-*.txt`
- APPLIANCE_STEP:P4-4:START
- Commands:
	- `systemctl start atp-router`
	- `curl .../healthz`
- Verification: `grep ok artifacts/post-verify-*.txt`
- APPLIANCE_STEP:P4-4:OK
- Rollback: `systemctl stop atp-router`
- CI: Upload smoke test log

### Phase 5: Upgrade & Rollback

**Step 12: Upgrade Bundle Verify**
- Prerequisites: bundle present
- Inputs: `/tmp/bundle-<ver>.tar.gz`
- Outputs: `/opt/atp/releases/<ver>.staging`, symlink switch
- APPLIANCE_STEP:P5-2:START
- Commands:
	- `tar -xzf ...`
	- `python3 -c ...` (hash check)
	- `ln -sfn ...`
	- `systemctl restart atp-router`
- Verification: `curl .../healthz`
- APPLIANCE_STEP:P5-2:OK
- Rollback: `ln -sfn /opt/atp/.previous /opt/atp/current; systemctl restart atp-router`
- CI: Upload upgrade log

### Phase 6: Observability & Diagnostics

**Step 13: Metrics Snapshot Endpoint**
- Prerequisites: router service code writable
- Inputs: None
- Outputs: `/admin/metrics_snapshot` endpoint
- APPLIANCE_STEP:P6-1:START
- Commands:
	- Implement endpoint in code
- Verification: `curl .../metrics_snapshot` returns JSON
- APPLIANCE_STEP:P6-1:OK
- Rollback: revert code change
- CI: Upload metrics snapshot

### Phase 7: Security Gating

**Step 14: Security Gating**
- Prerequisites: artifacts produced
- Inputs: None
- Outputs: `artifacts/pip_audit.json`, `artifacts/sbom.json`
- APPLIANCE_STEP:P7-1:START
- Commands:
	- `pip-audit --json > ...`
	- `syft ... > ...`
- Verification: `grep HIGH artifacts/pip_audit.json` (should be empty)
- APPLIANCE_STEP:P7-1:OK
- Rollback: fix CVEs, rerun audit
- CI: Upload audit and SBOM

---
**End of maximally explicit agent blueprint.**
