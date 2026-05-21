# Tasks: provisioning-api-service

## Feature Spec And Setup

- [x] Create feature branch and worktree
- [x] Draft and review `design.md`
- [x] Reframe feature from `provision-restructure` to `provisioning-api-service`
- [x] Create `scripts/atomixos_provision/pyproject.toml` with deps and metadata
- [x] Update the design to use Litestar instead of the original Starlette direction
- [x] Compare against Litestar fullstack reference and record applicable patterns

## Package Structure

- [x] Create `src/atomixos_provision/` package with `__init__.py`
- [x] Create module files: app, auth, config, config_builder, quadlet, quadlet_sync, activation, jobs, provision, bundle, ui, server
- [x] Create `tests/` directory with `conftest.py`

## Config Parsing And Generation

- [x] Move `config.toml` parsing and schema validation to `config.py`
- [x] Preserve `tomllib` usage and validation rules
- [x] Keep config generation logic in `config_builder.py` for tests/future use; no `/generate` route is exposed
- [x] Add tests covering config parsing and config generation behavior

## Authentication

- [x] Move SSH signature verification logic to `auth.py`
- [x] Implement nonce issuance, TTL, and single-use consumption
- [x] Implement Litestar guards with first-boot bypass
- [x] Preserve `ssh-keygen -Y verify` subprocess verification
- [x] Require SSH auth after provisioning for `/api/config`, `/api/validate`, and job polling
- [x] Add tests covering valid signatures, invalid signatures, expired nonces, replay, and unprovisioned bypass

## Quadlet Rendering And Sync

- [x] Move container, network, volume, and build rendering to `quadlet.py`
- [x] Move `quadlet-runtime.json` tracking logic
- [x] Move rendered-unit copy logic to `quadlet_sync.py`
- [x] Add tests covering rendering and sync behavior

## Bundle Import

- [x] Move tar.gz/tar.zst extraction and file placement to `bundle.py`
- [x] Preserve `${CONFIG_DIR}` and `${FILES_DIR}` token substitution behavior
- [x] Add tests covering bundle import behavior

## Activation And Rollback

- [x] Move activation script execution to `activation.py`
- [x] Move rootful and rootless service health checks to `activation.py`
- [x] Move candidate, active, and rollback config swap handling to `activation.py`
- [x] Add F2FS-safe parent-directory fsync during promotion
- [x] Add tests covering activation and rollback behavior

## Async Job API

- [x] Create `jobs.py` with single-flight job execution
- [x] Define job states: SUBMITTED, RUNNING, SUCCEEDED, FAILED
- [x] Track rollback status in failed jobs
- [x] Implement mutual exclusion for concurrent submissions
- [x] Bound retained job history to avoid unbounded memory growth
- [x] Add tests for concurrent submission, state transitions, and cleanup

## Litestar HTTP Application

- [x] Create `app.py` with Litestar app factory
- [x] Wire API routes: GET `/api/nonce`, POST `/api/config`, GET `/api/jobs/{id}`, GET `/api/health`, POST `/api/validate`
- [x] Integrate SSH auth guards with first-boot bypass
- [x] Integrate job manager for POST `/api/config`

## Boot UI Routes

- [x] Create `ui.py` with HTML form endpoints
- [x] GET `/` — serve Boot UI HTML
- [x] GET `/assets/atomixos.png` — serve static logo
- [x] POST `/apply` — multipart form to sync provision to HTML result
- [x] Do not expose `/generate`; first-boot UI only uploads or pastes a prepared config
- [x] Escape user-controlled HTML output

## Server Entry Point

- [x] Create `server.py` with click-based CLI
- [x] Implement commands: `serve`, `validate`, `import`, `recover`, `sync-quadlet`
- [x] Implement sd_listen_fds socket inheritance from systemd
- [x] Preserve systemd unit compatibility

## Nix Integration

- [x] Update `modules/first-boot.nix` to reference the new Python package
- [x] Build Python environment with Litestar, uvicorn, and the new package
- [x] Bind first-boot socket to `0.0.0.0:8080`, then rebind to provisioned LAN IP
- [x] Preserve PATH dependencies (openssh, gzip, zstd, systemd, util-linux)
- [x] Update `nix/tests/first-boot-provision.nix` for the new package
- [x] Update `nix/tests/first-boot-source-discovery.nix` for the new package

## Cleanup And Close

- [x] Move provisioning implementation into `scripts/atomixos_provision/` while preserving the `first-boot-provision` command interface
- [x] Update docs and reference pages for the new package layout
- [x] Update `docs/src/planned-features.md` to mark feature complete
- [x] Add `boot-ui-htmx` to `planned-features.md` as a follow-up feature
- [ ] Run full Nix build and VM tests on aarch64-linux builder

## Service Foundation Follow-Up

- [x] Add `settings.py` with a small environment-backed `AppSettings` object
- [x] Add `deps.py` with Litestar dependency providers for settings and service facades
- [x] Add `exceptions.py` for consistent domain-error to HTTP-response mapping
- [x] Add typed schemas for nonce, validation, submit-config, job, job event, and provision result responses
- [x] Convert job response serialization to use the typed schemas
- [x] Split `/api/health` into a `domain/system/controller.py`
- [x] Split `/api/nonce` into a `domain/auth/controller.py`
- [x] Split `/api/jobs/{id}` into a `domain/jobs/controller.py`
- [x] Split `/api/config` and `/api/validate` into a `domain/config/controller.py`
- [x] Add a `ConfigService` facade for apply and validate operations
- [x] Keep `create_app()` route wiring explicit; do not add domain auto-discovery yet
- [x] Add OpenAPI operation IDs, summaries, tags, and typed response metadata for API routes
- [x] Add docs updates for `docs/src/provisioning.md`, `docs/src/data-flow.md`, `docs/src/runtime-boundaries.md`, `docs/src/reference/project-structure.md`, `docs/src/code-reference/scripts.md`, and `docs/src/testing.md` when service API behavior changes
- [x] Keep Boot UI routes in `ui.py` until the `boot-ui-htmx` follow-up splits server-rendered partials

## Future Dynamic API Direction

- [x] Design `GET /api/config/current` to return normalized current desired state
- [x] Design `GET /api/config/export` to export a backup/clone config bundle
- [x] Design typed user partial updates such as `PATCH /api/config/users/{name}`
- [x] Design typed network partial updates such as `PATCH /api/config/network`
- [x] Design typed container partial updates such as `PATCH /api/config/containers/{name}`
- [x] Ensure every partial update loads current desired state, applies a typed patch, validates full desired state, renders candidate state, promotes atomically, activates, reports job progress, and rolls back on failure
- [x] Do not allow partial API paths to directly mutate derived files or runtime systemd/Quadlet state
- [x] Define normalized desired-state import and export bookends before implementing partial mutation APIs
- [ ] Add import/export round-trip tests so API-managed state can always be backed up or cloned as a config bundle
- [x] Add drift detection/reporting expectations for rendered files under `/data/config/`

## Validation And Readiness

- [x] Run `uv run --extra dev pytest` for the provisioning package
- [x] Run `uv run --extra dev ruff check .` for the provisioning package
- [x] Run Nix parse checks for touched modules and VM tests
- [x] Run the relevant NixOS VM tests after controller/service refactors
- [ ] Verify rootfs closure remains within the 1 GB squashfs budget after dependency changes
- [x] Search docs for stale synchronous `/api/config` response descriptions after API changes

## Explicitly Deferred

- [x] Do not add SQLAlchemy, a database, or repository abstractions without a persistent data model that cannot be represented by config state
- [x] Do not add Redis/SAQ unless jobs must survive service restarts or run independently of the provisioning process
- [x] Do not add OAuth/JWT auth unless SSH-signature administration stops meeting operator needs
- [x] Do not add Vite/SPA integration for the bootstrap UI; prefer server-rendered/HTMX follow-up work
