# Feature: provisioning-api-service

## Overview

Build the provisioning implementation as a long-lived Litestar API service rather
than a one-off first-boot importer. The config bundle and `config.toml` remain the
bootstrap, backup, restore, and clone format, but runtime configuration changes
should increasingly flow through a typed API surface backed by the same validation,
candidate rendering, atomic promotion, activation, health-check, and rollback
pipeline.

The first step was replacing the monolithic `first-boot-provision.py` with the
`atomixos-provision` Python package, Litestar + uvicorn, module-level tests, SSH
signature authentication, async jobs, and structured deployment progress. The next
step is to harden the package into a service foundation that can support dynamic
partial reconfiguration without creating divergent mutation paths.

## Source

`docs/src/planned-features.md` — originally tracked as "Bootstrap provisioning
subproject" / `provision-restructure`. Reframed as `provisioning-api-service`
after comparing the implementation against the Litestar fullstack reference
application at `/Users/DeRoseR/workspace/personal/litestar-fullstack`.

## Goals

1. Keep `config.toml` and config bundles as the canonical import/export format for
   first boot, backups, restore, and cloning deployments.
2. Treat the running provisioning service as the canonical control plane for future
   dynamic changes.
3. Ensure every mutation path uses the same state machine:
   - load current desired state
   - apply a full config import or typed partial change
   - validate the resulting full desired state
   - render candidate state
   - promote atomically
   - activate runtime services
   - report structured job progress
   - roll back on activation or required-health failure
4. Keep the current Litestar + uvicorn foundation, SSH-signature authentication,
   first-boot auth bypass, socket activation, and single-flight job execution.
5. Move from raw route functions returning open-ended dictionaries toward typed
   controllers, services, schemas, and exception handling suitable for a larger API.
6. Preserve the current device constraints: small closure, read-only rootfs, F2FS
   `/data`, no default credentials, and no unnecessary database/Redis dependency.

## Non-Goals

- Replacing `config.toml` or config bundles as bootstrap/backup/clone artifacts.
- Adding a database, Redis, SAQ, OAuth, JWT, or fleet-management dependency.
- Modifying the NixOS module interface beyond what's needed for the new package.
- Boot UI redesign or HTMX integration (planned as follow-up feature).
- Multi-device orchestration.
- Implementing every partial config API in this feature. This feature establishes
  the service architecture those APIs should use.

## Constraints

- Must fit within the existing 1 GB squashfs rootfs closure.
- Litestar + uvicorn must be available in nixpkgs or trivially packageable.
- Must preserve systemd socket activation (uvicorn accepts inherited fd via
  `LISTEN_FDS`/`LISTEN_PID` environment variables, matching current behavior).
- Must preserve the SSH signature authentication contract:
  - `GET /api/nonce` issues a single-use `secrets.token_urlsafe(32)` nonce (TTL 300s).
  - Signed message format:
    `"atomixos-reapply-v1\nnonce:{nonce}\npath:{request_path}\nsha256:{payload_sha256_hex}\n"`
- Headers: `X-AtomixOS-Nonce` + `X-AtomixOS-Signature` (base64 SSH sig blob).
- Verification via `ssh-keygen -Y verify` against `{config_root}/admin-signers`.
- Must preserve the first-boot provisioning flow without SSH signatures. The Boot UI
  form includes an in-memory bootstrap token to prevent cross-site form posts; this
  is a CSRF control, not operator authentication. Programmatic `/api/config`
  submissions do not require the Boot UI token before initial provisioning.
- No default credentials in any state.
- Python 3.11+ (uses `tomllib` from stdlib).
- Litestar + uvicorn are now part of the provisioning package closure; future
  service-foundation changes must avoid adding heavyweight runtime dependencies
  unless they solve a concrete device requirement.

## Architecture

### Current Package Layout

```text
scripts/atomixos_provision/
├── pyproject.toml
├── src/
│   └── atomixos_provision/
│       ├── __init__.py
│       ├── app.py              # Litestar application factory, route wiring
│       ├── auth.py             # SSH signature verification guard + nonce manager
│       ├── config.py           # config.toml parsing and schema validation
│       ├── config_builder.py   # Build config TOML from structured inputs (future use)
│       ├── quadlet.py          # Quadlet unit rendering (container, network, volume, build)
│       ├── quadlet_sync.py     # Copy rendered units to rootful/rootless target dirs
│       ├── activation.py       # Activation script runner + service health checks + rollback
│       ├── jobs.py             # Async job manager (single-flight, status tracking)
│       ├── provision.py        # First-boot and re-apply orchestration
│       ├── bundle.py           # Bundle import (tar extraction, file placement, tokens)
│       ├── ui.py               # Boot UI HTML routes (/, /apply) — sync adapters
│       └── server.py           # Uvicorn entry point, sd_listen_fds socket activation
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_config_builder.py
│   ├── test_quadlet.py
│   ├── test_activation.py
│   ├── test_jobs.py
│   ├── test_provision.py
│   └── test_bundle.py
└── README.md                   # Developer notes (not user-facing docs)
```

### Target Service Layout

The package should evolve toward explicit domain modules. Avoid the full
`litestar-fullstack` auto-discovery/plugin stack for now; explicit route wiring is
smaller, easier to audit, and better suited to an appliance. Adopt the separation
of concerns, not the whole dependency stack.

```text
scripts/atomixos_provision/src/atomixos_provision/
├── app.py                    # explicit Litestar app factory and route registration
├── server.py                 # CLI + uvicorn + systemd socket activation
├── settings.py               # small env/default settings object
├── deps.py                   # dependency providers for settings, services, state
├── exceptions.py             # domain errors -> HTTP responses
├── domain/
│   ├── auth/
│   │   ├── controller.py     # nonce/auth-related API routes
│   │   ├── service.py        # nonce and SSH signature verification helpers
│   │   └── schemas.py        # NonceResponse, auth errors if needed
│   ├── config/
│   │   ├── controller.py     # /api/config, /api/validate, future partial APIs
│   │   ├── service.py        # import/export/patch orchestration facade
│   │   └── schemas.py        # typed request/response DTOs
│   ├── jobs/
│   │   ├── controller.py     # /api/jobs/{id}
│   │   ├── service.py        # single-flight job manager facade if needed
│   │   └── schemas.py        # JobResponse, JobEvent
│   └── system/
│       ├── controller.py     # /api/health and system status
│       └── schemas.py
├── provision.py              # core candidate/promote/activate orchestration
├── activation.py             # activation hook, service status, rollback
├── config.py                 # config parser and validation
├── config_builder.py         # config generation from form/API inputs
├── quadlet.py                # render Quadlet desired state
├── quadlet_sync.py           # sync rendered Quadlet units
├── bundle.py                 # config bundle extraction/import/export helpers
└── ui.py                     # Boot UI routes until HTMX/server components are split out
```

The target layout should remain intentionally smaller than the Litestar reference
application. Domain auto-discovery, SQLAlchemy repositories, SAQ/Redis workers,
OAuth, Vite, and email plugins are not part of this foundation.

### HTTP Endpoints

| Method | Path                   | Auth                                      | Response | Description                            |
|--------|------------------------|-------------------------------------------|----------|----------------------------------------|
| GET    | `/`                    | none                                      | HTML     | Boot UI page                           |
| GET    | `/api/nonce`           | none                                      | JSON     | Issue single-use nonce for auth        |
| GET    | `/api/health`          | none                                      | JSON     | Liveness check                         |
| GET    | `/api/jobs/{id}`       | job UUID                                  | JSON     | Poll async job status                  |
| GET    | `/assets/atomixos.png` | none                                      | image    | Static logo                            |
| POST   | `/api/config`          | SSH sig (provisioned) / none (first-boot) | JSON     | Submit config, returns job ID (async)  |
| POST   | `/api/validate`        | SSH sig                                   | JSON     | Validate config without applying       |
| POST   | `/apply`               | bootstrap token (first-boot only)         | HTML     | Form upload → sync apply → result page |

Future dynamic API endpoints should be typed resource operations that reuse the
same config service and job pipeline, for example:

| Method | Path                            | Description                                               |
|--------|---------------------------------|-----------------------------------------------------------|
| GET    | `/api/config/current`           | Return normalized current desired state                   |
| GET    | `/api/config/export`            | Export current config bundle for backup/clone             |
| PATCH  | `/api/config/users/{name}`      | Apply a typed user change through candidate promotion     |
| PATCH  | `/api/config/network`           | Apply typed network changes through candidate promotion   |
| PATCH  | `/api/config/containers/{name}` | Apply typed container changes through candidate promotion |

### Endpoint Architecture

All endpoints share a common core:

```text
/api/config  ─→  parse raw body    ─→  jobs.submit(provision.apply)  ─→  JSON {job_id}
/apply       ─→  parse multipart   ─→  provision.apply(sync)         ─→  HTML result
```

- `/api/config` uses the async job manager; returns immediately with job ID.
- `/apply` calls the provision core synchronously for first-boot upload/paste only.

`POST /api/config` returns `202 Accepted` with `job_id`, initial `state`,
`job_url`, and a `Location` header pointing at `/api/jobs/{id}`. Clients must
poll the job resource for final success, failure, deployment progress, rollback
status, and forwarding URL.

### Control-Plane Model

The service should have one mutation engine. Full config imports and future partial
API calls differ only in how the desired state is produced.

```text
POST /api/config
  -> parse bundle/config.toml
  -> validate full desired state
  -> render/promote/activate/rollback

PATCH /api/config/users/admin
  -> load active desired state
  -> apply typed patch
  -> validate full desired state
  -> render/promote/activate/rollback
```

Do not allow dynamic API calls to directly mutate derived files under `/data/config`
or runtime systemd/Quadlet state. The rendered files remain derived state, not the
primary API model.

### Reconciliation Bookends

The API and config bundle paths must round-trip through the same desired-state
model. Any future partial API must include these reconciliation points:

1. **Import bookend**: Convert `config.toml` or a config bundle into normalized
   desired state before validation and rendering.
2. **Patch bookend**: Apply typed API changes to the normalized desired state, not
   directly to rendered files.
3. **Validation bookend**: Validate the complete resulting desired state after any
   import or patch.
4. **Export bookend**: Export the active desired state back to `config.toml` or a
   config bundle so backups and deployment cloning remain equivalent to API-managed
   state.
5. **Drift bookend**: Treat files under `/data/config/` as derived from the active
   desired state. If a future API detects derived-state drift, it should report it
   and re-render through the normal candidate pipeline rather than patching files in
   place.

### Typed API Schemas

Job and API responses should be explicit typed schemas rather than ad hoc
`dict[str, Any]` values. At minimum, define typed models for:

- `NonceResponse`
- `SubmitConfigResponse`
- `ValidateConfigResponse`
- `ProvisionResult`
- `JobResponse`
- `JobEvent`
- `ServiceDeployEvent`
- `ServiceStatusEvent`

The current job response shape is:

```json
{
  "id": "...",
  "state": "running | succeeded | failed",
  "current_step": "service-status",
  "events": [
    {
      "step": "service-status",
      "elapsed_seconds": 32.71,
      "message": "caddy-gateway.service (rootful) is running",
      "service": "caddy-gateway.service",
      "mode": "rootful",
      "status": "running"
    }
  ]
}
```

This response shape should be preserved and formalized with schemas so clients do
not parse human-readable strings.

### Job Lifecycle

```text
SUBMITTED → RUNNING → SUCCEEDED
                   ↘ FAILED (+ rollback_status: completed | failed | skipped)
```

- Only one job at a time; concurrent submissions return 409 Conflict.
- Job state persists in memory (lost on restart; acceptable — single-request model).
- Client polls `GET /api/jobs/{id}` for completion.

Structured job events should distinguish provisioning steps from service deployment
state:

- `prepare`
- `recover`
- `validate`
- `write-candidate`
- `promote`
- `service-deploy`
- `activate`
- `service-status`
- `health-check`
- `rollback`
- `cleanup`
- `complete`

Service events should include `service`, `mode`, and `status` fields. Status values
currently include `building`, `starting`, `running`, `failed`, and `unknown`. True
live `pulling` status is deferred until the activation path can stream journal,
Podman events, or direct Podman operations.

### Settings And Dependencies

Add a small settings layer rather than scattering constants through handlers and
services. This should stay simple and environment-backed:

```python
@dataclass(frozen=True)
class AppSettings:
    config_root: Path = Path("/data/config")
    host: str = "172.20.30.1"
    port: int = 8080
    app_runtime_user: str = "appsvc"
    max_source_bytes: int = MAX_SOURCE_BYTES
```

Use Litestar dependency providers for settings and service facades once controllers
are introduced. This keeps route handlers thin and makes CLI/background paths use
the same service code as HTTP paths.

### Exception Handling

Introduce a small exception module that maps domain errors to consistent HTTP
responses:

- `ProvisionError` -> `400 Bad Request`
- auth missing/invalid -> `401 Unauthorized`
- permission denied -> `403 Forbidden` if needed
- busy job -> `409 Conflict`
- unknown job/resource -> `404 Not Found`
- unexpected error -> `500 Internal Server Error`

The goal is consistent JSON error bodies for API clients while preserving useful
HTML errors for Boot UI routes.

### API Schema Hygiene

Keep operation IDs, tags, summaries, and typed response models on controllers so
the API contract remains explicit in code and live OpenAPI schema routes can be
used by online clients. Suggested tags:

- `System`
- `Auth`
- `Config`
- `Jobs`
- `Provisioning`

This is useful for client generation, API discovery, and tests as the control-plane API grows.

### Future Dynamic API Direction

The current API intentionally keeps config bundle import as the only mutation
surface. Future typed partial APIs must be designed around normalized desired
state, not direct edits to rendered runtime artifacts.

Planned read/export bookends:

- `GET /api/config/current` returns the normalized current desired state loaded
  from `/data/config/config.toml` plus any API-managed fields once those exist.
- `GET /api/config/export` returns a backup/clone config bundle generated from
  normalized desired state and managed files, preserving the config bundle as the
  portable artifact.

Planned partial mutation examples:

- `PATCH /api/config/users/{name}` applies typed user changes.
- `PATCH /api/config/network` applies typed LAN, DNS, NTP, and firewall changes.
- `PATCH /api/config/containers/{name}` applies typed container changes.

Every partial mutation must run the same safety pipeline as full config import:

1. Load current normalized desired state.
2. Apply the typed patch in memory.
3. Validate the full resulting desired state.
4. Render candidate state under the candidate config root.
5. Promote atomically through the existing F2FS-safe promotion path.
6. Activate runtime services and report job progress.
7. Roll back on activation or required health-check failure.

Partial APIs must not directly mutate files under `/data/config/quadlet/`, sync
systemd/Quadlet search paths, or edit runtime systemd state. Import/export
round-trip tests must land before implementing partial mutation endpoints so
API-managed state can always be backed up or cloned as a config bundle. Drift
detection should report differences between normalized desired state and rendered
files under `/data/config/`, but drift reports are read-only and must not repair
state outside the safe apply pipeline.

### Activation Model

Two-phase activation (preserving current behavior):

1. **Activation script**: External script path from `ATOMIXOS_BOOTSTRAP_ACTIVATION` env
   var, run with 300s timeout.
2. **Health checks**: Read `health-required.json`, check each required service via
   `systemctl is-active` (rootful) or `runuser -u appsvc -- systemctl --user is-active`
   (rootless).
3. **Rollback**: On any failure, restore rollback directory → active, re-run activation
   with old config.

### Socket Activation

Uvicorn accepts the systemd-passed file descriptor. Current code already parses
`LISTEN_FDS`/`LISTEN_PID` and wraps fd 3 into a socket. The new `server.py` will pass
this fd to uvicorn via `--fd 3` or programmatic server configuration.

The socket unit (`atomixos-bootstrap.socket`) initially listens on
`0.0.0.0:8080` for first provisioning. After LAN settings are applied,
`lan-gateway-apply.py` writes a socket override for the configured
`gateway_ip`, then schedules a delayed restart of the socket/service. The delay
lets clients poll the original apply job before following the result's
`forwarding_url` to the configured LAN endpoint.

## Dependencies

- **New**: Litestar
- **New**: uvicorn (pure Python mode, no uvloop)
- **New (dev)**: pytest, httpx (test client), ruff
- **Existing**: tomllib (stdlib 3.11+), openssh (ssh-keygen), gzip, zstd, systemd,
  util-linux (runuser)

Parallelization and execution model:

- Mutating apply jobs remain single-flight per device to protect `/data/config` and
  runtime activation ordering.
- Read-only operations such as health, nonce issuance, job polling, validation, and
  future export/status reads may run concurrently.
- Future partial mutation endpoints must submit work through the same job manager or
  an equivalent single-flight mutation gate.

Explicitly avoid adding these until there is a concrete need:

- SQLAlchemy / database repository stack
- Redis / SAQ
- OAuth/JWT auth stack
- Vite/SPA integration
- domain auto-discovery plugin

## Risks and Tradeoffs

- **Migration risk**: Behavioral regressions from the first-phase rewrite or the
  controller/service split. Mitigated by pytest covering each module and existing
  NixOS VM integration tests continuing to pass.
- **Closure size**: Adding first-ever third-party Python packages. Litestar + uvicorn
  add runtime dependencies. Must verify after integration that rootfs stays within 1 GB.
- **Socket activation with uvicorn**: Uvicorn supports `--fd` for inherited sockets.
  Needs verification on aarch64. Current code already does sd_listen_fds parsing, so
  the pattern is proven.
- **Async complexity**: Limited to the job manager path. HTML routes remain synchronous.
  Core provision logic is synchronous — the job manager wraps it in a background task.
- **First-party dep risk**: Moving from zero deps to Litestar creates an upstream
  dependency. Litestar must be pinned and available in nixpkgs.
- **Over-abstracting too early**: The Litestar fullstack example includes many layers
  we do not need. Mitigate by adopting typed controllers/services/settings/errors
  only, and keeping app assembly explicit.
- **Divergent mutation paths**: Partial APIs could accidentally bypass the safe
  import/reapply pipeline. Mitigate by forcing every mutation through the same
  config service and candidate promotion flow.
- **API/bundle drift**: API-managed state could stop exporting to the same
  `config.toml`/bundle contract. Mitigate with import/export round-trip tests and
  by making normalized desired state the source for both API patches and exports.

## Affected Files and Modules

- `scripts/first-boot-provision.py` — compatibility entry point / legacy wrapper behavior aligned with the new package
- `modules/first-boot.nix` — updated to reference new package, add Python deps
- `nix/tests/first-boot-provision.nix` — must continue passing
- `nix/tests/first-boot-source-discovery.nix` — must continue passing
- `docs/src/planned-features.md` — mark feature complete when done
- `docs/src/provisioning.md` — first-boot and runtime provisioning behavior
- `docs/src/data-flow.md` — persisted state and re-apply flow
- `docs/src/runtime-boundaries.md` — API semantics and config/runtime boundary
- `docs/src/reference/project-structure.md` — package layout
- `docs/src/code-reference/scripts.md` — runtime scripts and provisioning CLI notes
- `docs/src/testing.md` — unit, lint, VM, and manual validation commands

## Success Criteria

- `scripts/atomixos_provision/` owns the provisioning implementation while the existing
  `first-boot-provision` command remains available for scripts, tests, and operators.
- `pyproject.toml` defines the package with all dependencies.
- Existing HTTP endpoint paths and authentication semantics are preserved, with documented
  response-shape changes for the async job API.
- Async job API works: POST `/api/config` returns job ID, GET `/api/jobs/{id}` returns
  status, concurrent submissions return 409.
- pytest suite passes with >80% coverage on module boundaries.
- Existing NixOS VM integration tests pass unchanged.
- Rootfs closure stays within 1 GB.
- `ruff check` and `ruff format` pass.
- API response shapes for jobs and validation are typed and documented.
- The package has an explicit path for future partial API operations that reuses the
  full import/reapply safety pipeline.
- Import/export reconciliation is documented so config bundles remain equivalent to
  API-managed desired state.
- Affected documentation pages are updated in the same unit of work as service API
  behavior changes.

## Validation

- `pytest` on host for unit tests.
- `nix build` to verify closure size.
- Existing NixOS VM tests: `nix/tests/first-boot-provision.nix`,
  `nix/tests/first-boot-source-discovery.nix`.
- New NixOS VM test scenario: authenticated re-apply with async job polling.
- `ruff check` and `ruff format` pass.
- API schema/serialization tests cover job response shape and service deployment
  event fields.
- Import/export round-trip tests are added before implementing partial mutation APIs.
- Documentation search confirms no stale references describe `/api/config` as a
  synchronous success response.

## Follow-Up Features

- **Boot UI HTMX redesign**: Convert Boot UI to HTMX-powered server-rendered partials
  on the clean Litestar foundation. Convert `/apply` to async with progress
  indicators.
- **Dynamic partial reconfiguration API**: Add typed PATCH/PUT endpoints for users,
  network, containers, and other desired-state resources, all backed by the same
  candidate promotion and rollback pipeline.
