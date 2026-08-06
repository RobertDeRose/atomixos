<!-- workflow-migration:legacy-markdown-to-beads -->

# Feature: Provisioning API Service

## Metadata

- Beads feature root: `atomixos-dhe`
- Feature slug: `provisioning-api-service`
- Design path: `docs/src/features/provisioning-api-service/design.md`
- Implemented record: `docs/src/features/provisioning-api-service/index.md`
- Base branch: `dev`
- Status: in progress

## Feature Summary

Evolve local provisioning from a one-shot script into a long-lived Litestar service with typed domain boundaries,
asynchronous jobs, complete config-bundle import/export, and one reusable desired-state apply pipeline.

## User Intent

Operators and client developers need a stable local control plane for first boot, re-apply, validation, recovery, and
typed changes without losing the canonical portable bundle or adding a database and second mutation path.

## User-Facing Behavior

The service exposes nonce, config submission, validation, jobs, health, complete bundle export, CLI maintenance, and
first-boot UI behavior through systemd socket activation. Fresh bootstrap and provisioned SSH-signature rules remain
distinct. The current implementation is partially complete; the retained implementation and validation tasks below must
close the bundle contract and target-evidence gaps before delivery.

## Requirements

The package must preserve config and bundle compatibility, socket activation, key-based auth, bounded production FIFO
admission with serialized privileged execution, atomic promotion, activation, rollback, small closure, explicit routing,
and dependency-light operation. Direct test/development roots retain a one-active-job guard; production `/data/config`
uses the staged unprivileged API plus root-owned worker boundary.

### Bundle Contract

- The portable bundle is a compressed tar archive with top-level `config.toml` and optional `files/` entries.
- `GET /api/config/export` returns a complete `config-bundle.tar.gz` containing the canonical `config.toml` and every
  managed payload under `/data/config/files/`; it does not expose generated JSON, Quadlet output, markers, signer
  material, or other runtime state.
- The exported archive must be accepted by the existing bundle importer and preserve regular-file contents and the
  managed-file ownership/mode policy after import. Archive members must be deterministic, relative, regular files or
  directories, and bounded by the existing upload/member/decompressed-size limits.
- Export reads a consistent active snapshot under the provisioning lock. Bundle export and import round-trip tests are
  required before the feature is delivered.

## Existing Context

First-Boot Local Provisioning and Config Reapply already supplied parsing, rendering, auth, promotion, and rollback in a
monolithic script. The service refactor modularizes those capabilities and is the foundation for live schema, partial
API, HTMX UI, and privilege separation.

## Proposed Design

Package the implementation as `atomixos_provision`, keep explicit Litestar controllers and service facades, model
responses and domain errors, preserve CLI and inherited systemd sockets, and route every mutation through complete desired
state. Export uses the same canonical desired state plus a locked snapshot of managed
`files/` payloads, never a tar of the whole `/data/config` tree. Detailed package
layout and flows remain below.

## Architecture Consistency

The design preserves one `config.toml` authority, immutable rootfs, mutable `/data/config`, systemd activation, SSH
signatures, first-boot exceptions, bounded admission, root-owned promotion, and rollback. The unprivileged service may
parse, validate, render, stage, and export approved state; only the root worker may promote `/data/config`, activate
runtime services, or publish privileged results. It avoids SQL, Redis, auto-discovery, and fleet concerns.

The original foundation has delivered follow-up capabilities for privilege separation, live schema, typed partial routes,
config reapply, and the HTMX Boot UI. This design records their current contracts and links their standalone feature
records rather than treating them as future route examples.

## Operational Considerations

The service is long-lived and socket-activated, so upgrades must preserve the inherited descriptor and unit contract.
Direct development/test jobs are memory-only and single-flight. Production jobs use a bounded FIFO (four pending jobs by
default), one root worker at a time, and result files under `/run/atomixos-provision` for restart recovery. Export is
read-only but still uses the provisioning lock to avoid reading a partially promoted tree. Closure size and full target
builds remain active validation obligations.

## Documentation Impact

- `docs/src/provisioning.md`: current API routes, authentication matrix, staged/direct job semantics, and complete export
  archive contract; updated with T086 when the endpoint changed.
- `docs/src/data-flow.md`: raw USB seed versus API bundle sources, persisted `files/` payloads, marker fallback, and
  export/import bookend.
- `docs/src/runtime-boundaries.md`: WAN/LAN bootstrap exposure, unprivileged/root ownership, export allowlist, and the
  shared provisioning predicate.
- `docs/src/provisioning/flash-image.md`: USB discovery accepts raw `config.toml`; bundle import is available through
  API/UI/CLI paths.
- `docs/src/introduction.md` and `docs/src/features/rock64-ab-image/design.md`: qualify pre- and post-provisioning
  network exposure.
- `docs/src/testing.md`, `docs/src/code-reference/modules.md`, and `docs/src/code-reference/scripts.md`: first-boot-only
  UI wording, CLI commands, and direct provisioning check commands.
- `docs/src/features/index.md`, `docs/src/features/provisioning-api-service/index.md`, and `docs/src/SUMMARY.md`: create
  and register the delivered record only after T063, T086, and T092 close.

Documentation updates for current delivered behavior are part of specification reconciliation; the final export response
and round-trip instructions were completed by T086 and remain subject to the documentation-reconcile gate.

## Validation Strategy

Run provisioning package pytest and Ruff checks, route/schema/auth/job/promotion tests, relevant NixOS VM checks, Nix
parse/evaluation, the explicit aarch64 target checks, complete config-bundle import/export round-trip tests,
closure-budget verification, and documentation validation. Do not use an unbounded all-systems evaluation on constrained
macOS hosts; use split target evaluation and `NIX_CONFIG='max-jobs = 1'` where required.

## Implementation Decomposition

Imported work covers package structure, parsing/rendering, auth, bundles, activation, jobs, HTTP/UI/CLI, Nix integration,
service-domain refactoring, dynamic API groundwork, docs, and validation. The implementation graph retains the three
legacy validation tasks and adds bounded contract-hardening and complete-bundle tasks before delivery.

## Dependencies and Parallelism

The feature builds on first-boot provisioning and config re-apply. Package/domain refactoring and typed schema work could
advance in parallel; route and Nix integration depended on the stable service and socket contracts.

## Open Questions

The export contract decision is resolved in favor of complete compressed-tar bundle export, and T086 now owns the
implemented archive and round-trip evidence. Remaining close-out work is concrete: the full aarch64 build/VM run and
rootfs closure-budget verification.

## Overview

Build the provisioning implementation as a long-lived Litestar API service rather
than a one-off first-boot importer. The config bundle and `config.toml` remain the
bootstrap, backup, restore, and clone format, but runtime configuration changes
should increasingly flow through a typed API surface backed by the same validation,
candidate rendering, atomic promotion, activation, health-check, and rollback
pipeline.

The first step replaced the monolithic `first-boot-provision.py` with the
`atomixos-provision` Python package, Litestar + uvicorn, module-level tests, SSH
signature authentication, async jobs, and structured deployment progress. Delivered
follow-up work added privilege-separated staging, live OpenAPI schema, typed partial
routes, config reapply, and the asynchronous Boot UI. The retained implementation
work completes portable bundle export and hardens the remaining job/error/package
contracts without creating divergent mutation paths.

## Source

`docs/src/planned-features.md` — originally tracked as "Bootstrap provisioning
subproject" / `provision-restructure`. Reframed as `provisioning-api-service`
after comparing the implementation against the Litestar fullstack reference
application at `/Users/DeRoseR/workspace/personal/litestar-fullstack`.

## Goals

1. Keep `config.toml` and complete compressed-tar config bundles as the canonical
   import/export format for first boot, backups, restore, and cloning deployments.
   A bundle contains only `config.toml` and managed `files/` payloads; generated
   runtime outputs and credentials are not exported.
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
4. Keep the current Litestar + base uvicorn foundation, SSH-signature authentication,
   first-boot auth bypass, socket activation, and serialized mutation execution. The
   production API admits up to four pending staged jobs while the privileged worker
   applies one at a time; direct test roots reject a second active job.
5. Move from raw route functions returning open-ended dictionaries toward typed
   controllers, services, schemas, and exception handling suitable for a larger API.
   Known `ProvisionError` validation failures map to `400`; unexpected failures use
   the framework's `500` path.
6. Preserve the current device constraints: small closure, read-only rootfs, F2FS
   `/data`, no default credentials, and no unnecessary database/Redis dependency.

## Non-Goals

- Replacing `config.toml` or config bundles as bootstrap/backup/clone artifacts.
- Adding a database, Redis, SAQ, OAuth, JWT, or fleet-management dependency.
- Modifying the NixOS module interface beyond what's needed for the new package.
- Multi-device orchestration.
- Arbitrary partial or JSON-patch semantics; delivered typed partial routes remain
  bounded to the documented resource operations and are not a second state store.
- Replacing the delivered privilege-separation, live-schema, typed-partial, config-
  reapply, or HTMX follow-up contracts; their records remain the authoritative
  delivery history.

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
│       ├── bundle.py           # Bundle import/export, safe archive and file placement
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
│   │   ├── controller.py     # /api/config, /api/validate, typed partial APIs
│   │   ├── service.py        # import/export/patch orchestration facade
│   │   └── schemas.py        # typed request/response DTOs
│   ├── jobs/
│   │   ├── controller.py     # /api/jobs/{job_id}
│   │   ├── service.py        # job manager facade if needed
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
├── bundle.py                 # config bundle extraction, locked export, and file helpers
└── ui.py                     # Boot UI routes until HTMX/server components are split out
```

The target layout should remain intentionally smaller than the Litestar reference
application. Domain auto-discovery, SQLAlchemy repositories, SAQ/Redis workers,
OAuth, Vite, and email plugins are not part of this foundation. `config_builder.py`
and unused request `TypedDict`s plus operation-specific `ConfigService` convenience
wrappers remain explicitly deferred scaffolding; controllers use the generic facade
until a caller requires those helpers. They are not required runtime surfaces for
this feature.

### HTTP Endpoints

| Method | Path                   | Auth                                      | Response | Description                           |
|--------|------------------------|-------------------------------------------|----------|---------------------------------------|
| GET    | `/`                    | none                                      | HTML     | Boot UI page                          |
| GET    | `/api/nonce`           | none                                      | JSON     | Issue single-use nonce for auth       |
| GET    | `/api/health`          | none                                      | JSON     | Liveness check                        |
| GET    | `/api/jobs/{job_id}`   | job UUID                                  | JSON     | Poll async job status                 |
| GET    | `/assets/atomixos.png` | none                                      | image    | Static logo                           |
| POST   | `/api/config`          | SSH sig (provisioned) / none (first-boot) | JSON     | Submit config, returns job ID (async) |
| GET    | `/api/config/export`   | SSH signature                             | tar.gz   | Export complete config bundle         |
| POST   | `/api/validate`        | SSH sig                                   | JSON     | Validate config without applying      |
| POST   | `/apply`               | bootstrap token (first-boot only)         | HTML     | Form upload → async job progress page |

The delivered typed API endpoints are resource operations that reuse the same
config service and job pipeline. Future additions must follow the same boundary.
The current and planned resource surface is:

| Method | Path                            | Description                                               |
|--------|---------------------------------|-----------------------------------------------------------|
| GET    | `/api/config/current`           | Return normalized current desired state                   |
| GET    | `/api/config/export`            | Complete config.toml + managed files bundle               |
| PATCH  | `/api/config/users/{name}`      | Apply a typed user change through candidate promotion     |
| PATCH  | `/api/config/network`           | Apply typed network changes through candidate promotion   |
| PATCH  | `/api/config/containers/{name}` | Apply typed container changes through candidate promotion |

### Endpoint Architecture

All endpoints share a common core:

```text
/api/config  ─→  parse raw body    ─→  jobs.submit(provision.apply)  ─→  JSON {job_id}
/apply       ─→  parse multipart   ─→  jobs.submit(provision.apply)  ─→  HTML progress
```

- `/api/config` uses the async job manager; returns immediately with job ID.
- `/apply` uses the same async job manager for first-boot browser upload/paste and
  renders first-boot-only job progress fragments. Older synchronous `/apply`
  behavior was superseded by `boot-ui-htmx`.

`POST /api/config` returns `202 Accepted` with `job_id`, initial `state`,
`job_url`, and a `Location` header pointing at `/api/jobs/{job_id}`. Clients must
poll the job resource for final success, failure, deployment progress, rollback
status, and forwarding URL.

### Privilege and Staging Boundary

On production `/data/config` roots, the Litestar process runs as the unprivileged
`atomixos-provision` user. It may read the approved config, authenticate requests,
parse and validate uploads, render a candidate under `/run/atomixos-provision`, and
write a manifest containing relative paths, owners, modes, sizes, and SHA-256
hashes. A root-owned path/oneshot worker verifies that manifest and owns promotion,
activation, rollback, recovery, and result publication. The API cannot directly
replace `/data/config` or runtime systemd/Quadlet state.

First-boot seed discovery and the compatibility CLI remain trusted maintenance
exceptions: `first-boot.sh` may invoke the privileged import path for local seeds,
while network API submissions use the service boundary. Their distinct failure
semantics are documented and tested; the API and partial operations always use the
shared candidate pipeline.

### Control-Plane Model

The service has one mutation engine. Full config imports and typed partial API calls
differ only in how desired state is produced, and both submit through the same
validation, rendering, promotion, activation, health, and rollback pipeline. The
trusted first-boot CLI seed path is the explicit local-maintenance exception.

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

Do not allow API calls to directly mutate derived files under `/data/config` or
runtime systemd/Quadlet state. The rendered files remain derived state, not the
primary API model. Export is read-only and allowlisted to `config.toml` plus
`files/`; it must never archive the whole config root.

### Reconciliation Bookends

The API and config bundle paths must round-trip through the same desired-state
model. Any future partial API must include these reconciliation points:

1. **Import bookend**: Convert `config.toml` or a config bundle into normalized
   desired state before validation and rendering.
2. **Patch bookend**: Apply typed API changes to the normalized desired state, not
   directly to rendered files.
3. **Validation bookend**: Validate the complete resulting desired state after any
   import or patch.
4. **Export bookend**: Under the provisioning lock, export the active desired state
   as a deterministic compressed tar bundle containing canonical `config.toml` and
   managed `files/` payloads. Exclude generated JSON, Quadlet output, markers,
   signer material, and other runtime state so backups and deployment cloning remain
   equivalent to API-managed state without leaking platform credentials.
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

- Direct development/test roots use `JobManager`: one active job, `409 Conflict` on
  a concurrent mutation, and in-memory terminal state.
- Production `/data/config` roots use `StagedJobManager`: four pending jobs by
  default, FIFO admission with `409 Conflict` only when capacity is full, one
  privileged worker applying at a time, and result files that permit status
  recovery after service restart.
- Queue admission, staging, and root-worker execution are distinct; the production
  queue is not concurrent promotion. Partial endpoints additionally require an
  otherwise empty staged queue until their candidate is published.
- Clients poll `GET /api/jobs/{job_id}` for completion in either mode.

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

Use Litestar dependency providers for settings and service facades in the current
controllers. This keeps route handlers thin and makes CLI/background paths use the
same service code as HTTP paths.

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

### Delivered and Future Dynamic API Direction

The delivered typed partial routes are input conveniences over normalized desired
state, not a second mutation surface. They use the same authenticated job and
candidate pipeline as full imports. Future typed partial APIs must follow the same
rule and must not directly edit rendered runtime artifacts.

The export bookend is implemented by T086. The endpoint returns a deterministic
compressed tar bundle generated from the canonical desired state and managed files,
preserving the config bundle as the portable artifact. The implementation does not
archive unrelated `/data/config` state.

Future read/mutation examples include:

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
systemd/Quadlet search paths, or edit runtime systemd state. Complete bundle
import/export round-trip tests now ensure API-managed state can always be backed up
or cloned as a config bundle. Drift
detection should report differences between normalized desired state and rendered
files under `/data/config/`, but drift reports are read-only and must not repair
state outside the safe apply pipeline.

### Provisioning-State Predicate

The shared intended predicate is `_is_provisioned_config_root`: a root is considered
provisioned when `.first-config` exists or a valid `config.toml` exists. The config
file fallback preserves compatibility with state created before the marker was
introduced. Authentication must fail closed when this predicate is true and signer
state is unavailable; UI exposure guards must use the same predicate rather than
an independent signer-only test. Unifying the code paths and retaining the
config-without-marker regression test is part of the execution-hardening task.

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

- **New**: pinned Litestar
- **New**: pinned base uvicorn (pure Python mode; do not request `uvicorn[standard]`
  or uvloop in the appliance package)
- **New (dev)**: pytest, httpx (test client), ruff
- **Existing**: tomllib (stdlib 3.11+), openssh (ssh-keygen), gzip, zstd, systemd,
  util-linux (runuser)

Parallelization and execution model:

- Production mutating jobs may be admitted into a bounded FIFO, but promotion and
  activation remain one-at-a-time per device to protect `/data/config` and runtime
  ordering. Direct roots retain single-flight rejection.
- Read-only operations such as health, nonce issuance, job polling, validation, and
  locked export may run concurrently with each other but export must take the
  provisioning read/snapshot lock.
- Delivered and future partial mutation endpoints must submit work through the
  same job manager or an equivalent staged admission and single-flight mutation
  gate.

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
- **Async complexity**: Limited to the job manager path. Core provision logic is
  synchronous; the job manager wraps it in a background task and the Boot UI returns
  asynchronous HTML job fragments. The root worker remains serialized.
- **First-party dep risk**: Moving from zero deps to Litestar creates an upstream
  dependency. Litestar must be pinned and available in nixpkgs.
- **Over-abstracting too early**: The Litestar fullstack example includes many layers
  we do not need. Mitigate by adopting typed controllers/services/settings/errors
  only, and keeping app assembly explicit.
- **Divergent mutation paths**: Partial APIs could accidentally bypass the safe
  import/reapply pipeline. Mitigate by forcing every mutation through the same
  config service and candidate promotion flow.
- **API/bundle drift**: API-managed state could stop exporting to the same
  `config.toml`/bundle contract. Mitigate with complete import/export round-trip
  tests and by making normalized desired state plus managed `files/` the source for
  both API patches and exports.
- **Privilege-boundary drift**: A future route could read or mutate an allowlisted
  path incorrectly. Mitigate with root-worker manifest verification, export path
  allowlisting, no-symlink tests, and one shared provisioning predicate.

## Affected Files and Modules

- `scripts/first-boot-provision.py` — compatibility entry point / legacy wrapper behavior aligned with the new package
- `scripts/atomixos_provision/src/atomixos_provision/bundle.py` — safe archive export and managed-file snapshot
- `scripts/atomixos_provision/src/atomixos_provision/domain/config/controller.py` — export response contract
- `scripts/atomixos_provision/tests/test_bundle.py` and `tests/test_config_service.py` — archive and service tests
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
- Async job API works: POST `/api/config` returns a job ID, GET `/api/jobs/{job_id}`
  returns status, production admission is bounded FIFO, and direct concurrent
  submissions return 409.
- `GET /api/config/export` returns an authenticated compressed tar bundle containing
  canonical `config.toml` and managed `files/` payloads, and the result imports
  successfully into a clean config root with equivalent managed-file contents.
- Package tests cover archive path/type/size safety, deterministic export contents,
  missing/empty managed files, authentication, and full import/export round trips.
- Existing NixOS VM integration tests pass unchanged.
- Rootfs closure stays within 1 GB.
- `ruff check` and `ruff format` pass.
- API response shapes for jobs and validation are typed and documented.
- The package has explicit typed partial operations that reuse the full
  import/reapply safety pipeline, and future operations follow the same contract.
- Import/export reconciliation is documented so complete config bundles remain
  equivalent to API-managed desired state without exporting derived runtime files.
- Affected documentation pages are updated in the same unit of work as service API
  behavior changes.

## Validation

- `pytest` on host for unit tests, including complete bundle round trips.
- `nix build` to verify closure size and the explicit aarch64 target checks.
- Existing NixOS VM tests: `nix/tests/first-boot-provision.nix`,
  `nix/tests/first-boot-source-discovery.nix`.
- New NixOS VM test scenario: authenticated re-apply with async job polling.
- `ruff check` and `ruff format` pass.
- API schema/serialization tests cover job response shape and service deployment
  event fields.
- Complete import/export round-trip tests cover `config.toml` plus managed files
  before the feature is delivered.
- Documentation search confirms no stale references describe `/api/config` as a
  synchronous success response, the Boot UI as post-provision management, or USB
  discovery as accepting bundles when it only discovers raw `config.toml`.

## Related Delivered Features

- **Boot UI HTMX**: The first-boot `/apply` route is an asynchronous HTML job
  interface; it remains first-boot-only.
- **Typed partial provisioning API**: Authenticated typed user, network, container,
  network, and volume operations reuse the full candidate promotion and rollback
  pipeline.
- **Config reapply, privilege separation, and live schema**: These delivered records
  define the current staged worker, auth, and OpenAPI contracts that this foundation
  preserves.
