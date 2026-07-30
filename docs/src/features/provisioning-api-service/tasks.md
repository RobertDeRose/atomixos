# Tasks: provisioning-api-service

## Feature Spec And Setup

- [x] T001 Create feature branch and worktree
- [x] T002 Draft and review `design.md`
- [x] T003 Reframe feature from `provision-restructure` to `provisioning-api-service`
- [x] T004 Create `scripts/atomixos_provision/pyproject.toml` with deps and metadata
- [x] T005 Update the design to use Litestar instead of the original Starlette direction
- [x] T006 Compare against Litestar fullstack reference and record applicable patterns

## Package Structure

- [x] T007 Create `src/atomixos_provision/` package with `__init__.py`
- [x] T008 Create module files: app, auth, config, config_builder, quadlet,
  quadlet_sync, activation, jobs, provision, bundle, ui, server
- [x] T009 Create `tests/` directory with `conftest.py`

## Config Parsing And Generation

- [x] T010 Move `config.toml` parsing and schema validation to `config.py`
- [x] T011 Preserve `tomllib` usage and validation rules
- [x] T012 Keep config generation logic in `config_builder.py` for tests/future use; no `/generate` route is exposed
- [x] T013 Add tests covering config parsing and config generation behavior

## Authentication

- [x] T014 Move SSH signature verification logic to `auth.py`
- [x] T015 Implement nonce issuance, TTL, and single-use consumption
- [x] T016 Implement Litestar guards with first-boot bypass
- [x] T017 Preserve `ssh-keygen -Y verify` subprocess verification
- [x] T018 Require SSH auth after provisioning for `/api/config` and `/api/validate`
- [x] T019 Keep job polling authorized by unguessable job UUID only
- [x] T020 Add tests covering valid signatures, invalid signatures, expired nonces, replay, and unprovisioned bypass

## Quadlet Rendering And Sync

- [x] T021 Move container, network, volume, and build rendering to `quadlet.py`
- [x] T022 Move `quadlet-runtime.json` tracking logic
- [x] T023 Move rendered-unit copy logic to `quadlet_sync.py`
- [x] T024 Add tests covering rendering and sync behavior

## Bundle Import

- [x] T025 Move tar.gz/tar.zst extraction and file placement to `bundle.py`
- [x] T026 Preserve `${CONFIG_DIR}` and `${FILES_DIR}` token substitution behavior
- [x] T027 Add tests covering bundle import behavior

## Activation And Rollback

- [x] T028 Move activation script execution to `activation.py`
- [x] T029 Move rootful and rootless service health checks to `activation.py`
- [x] T030 Move candidate, active, and rollback config swap handling to `activation.py`
- [x] T031 Add F2FS-safe parent-directory fsync during promotion
- [x] T032 Add tests covering activation and rollback behavior

## Async Job API

- [x] T033 Create `jobs.py` with single-flight job execution
- [x] T034 Define job states: SUBMITTED, RUNNING, SUCCEEDED, FAILED
- [x] T035 Track rollback status in failed jobs
- [x] T036 Implement mutual exclusion for concurrent submissions
- [x] T037 Bound retained job history to avoid unbounded memory growth
- [x] T038 Add tests for concurrent submission, state transitions, and cleanup

## Litestar HTTP Application

- [x] T039 Create `app.py` with Litestar app factory
- [x] T040 Wire API routes: GET `/api/nonce`, POST `/api/config`, GET `/api/jobs/{job_id}`, GET `/api/health`, POST `/api/validate`
- [x] T041 Integrate SSH auth guards with first-boot bypass
- [x] T042 Integrate job manager for POST `/api/config`

## Boot UI Routes

- [x] T043 Create `ui.py` with HTML form endpoints
- [x] T044 GET `/` — serve Boot UI HTML
- [x] T045 GET `/assets/atomixos.png` — serve static logo
- [x] T046 POST `/apply` — multipart form to async provision job progress (updated by
  `boot-ui-htmx`)
- [x] T047 Do not expose `/generate`; first-boot UI only uploads or pastes a prepared config
- [x] T048 Escape user-controlled HTML output

## Server Entry Point

- [x] T049 Create `server.py` with click-based CLI
- [x] T050 Implement commands: `serve`, `validate`, `import`, `recover`, `sync-quadlet`
- [x] T051 Implement sd_listen_fds socket inheritance from systemd
- [x] T052 Preserve systemd unit compatibility

## Nix Integration

- [x] T053 Update `modules/first-boot.nix` to reference the new Python package
- [x] T054 Build Python environment with Litestar, uvicorn, and the new package
- [x] T055 Bind first-boot socket to `0.0.0.0:8080`, then rebind to provisioned LAN IP
- [x] T056 Preserve PATH dependencies (openssh, gzip, zstd, systemd, util-linux)
- [x] T057 Update `nix/tests/first-boot-provision.nix` for the new package
- [x] T058 Update `nix/tests/first-boot-source-discovery.nix` for the new package

## Cleanup And Close

- [x] T059 Move provisioning implementation into `scripts/atomixos_provision/`
  while preserving the `first-boot-provision` command interface
- [x] T060 Update docs and reference pages for the new package layout
- [x] T061 Update `docs/src/planned-features.md` to mark feature complete
- [x] T062 Add `boot-ui-htmx` to `planned-features.md` as a follow-up feature
- [ ] T063 Run full Nix build and VM tests on aarch64-linux builder

## Service Foundation Follow-Up

- [x] T064 Add `settings.py` with a small environment-backed `AppSettings` object
- [x] T065 Add `deps.py` with Litestar dependency providers for settings and service facades
- [x] T066 Add `exceptions.py` for consistent domain-error to HTTP-response mapping
- [x] T067 Add typed schemas for nonce, validation, submit-config, job, job event, and provision result responses
- [x] T068 Convert job response serialization to use the typed schemas
- [x] T069 Split `/api/health` into a `domain/system/controller.py`
- [x] T070 Split `/api/nonce` into a `domain/auth/controller.py`
- [x] T071 Split `/api/jobs/{job_id}` into a `domain/jobs/controller.py`
- [x] T072 Split `/api/config` and `/api/validate` into a `domain/config/controller.py`
- [x] T073 Add a `ConfigService` facade for apply and validate operations
- [x] T074 Keep `create_app()` route wiring explicit; do not add domain auto-discovery yet
- [x] T075 Add OpenAPI operation IDs, summaries, tags, and typed response metadata for API routes
- [x] T076 Add docs updates for `docs/src/provisioning.md`,
  `docs/src/data-flow.md`, `docs/src/runtime-boundaries.md`,
  `docs/src/reference/project-structure.md`,
  `docs/src/code-reference/scripts.md`, and `docs/src/testing.md` when
  service API behavior changes
- [x] T077 Keep Boot UI routes in `ui.py` until the `boot-ui-htmx` follow-up splits server-rendered partials

## Future Dynamic API Direction

- [x] T078 Design `GET /api/config/current` to return normalized current desired state
- [x] T079 Design `GET /api/config/export` to export a backup/clone config bundle
- [x] T080 Design typed user partial updates such as `PATCH /api/config/users/{name}`
- [x] T081 Design typed network partial updates such as `PATCH /api/config/network`
- [x] T082 Design typed container partial updates such as `PATCH /api/config/containers/{name}`
- [x] T083 Ensure every partial update loads current desired state, applies a typed
  patch, validates full desired state, renders candidate state, promotes
  atomically, activates, reports job progress, and rolls back on failure
- [x] T084 Do not allow partial API paths to directly mutate derived files or runtime systemd/Quadlet state
- [x] T085 Define normalized desired-state import and export bookends before implementing partial mutation APIs
- [ ] T086 Add import/export round-trip tests so API-managed state can always be backed up or cloned as a config bundle
- [x] T087 Add drift detection/reporting expectations for rendered files under `/data/config/`

## Validation And Readiness

- [x] T088 Run `uv run --extra dev pytest` for the provisioning package
- [x] T089 Run `uv run --extra dev ruff check .` for the provisioning package
- [x] T090 Run Nix parse checks for touched modules and VM tests
- [x] T091 Run the relevant NixOS VM tests after controller/service refactors
- [ ] T092 Verify rootfs closure remains within the 1 GB squashfs budget after dependency changes
- [x] T093 Search docs for stale synchronous `/api/config` response descriptions after API changes
- [x] T999: Reconcile final implementation, feature specs, and docs before close-out

## Explicitly Deferred

- [x] T094 Do not add SQLAlchemy, a database, or repository abstractions without a
  persistent data model that cannot be represented by config state
- [x] T095 Do not add Redis/SAQ unless jobs must survive service restarts or run independently of the provisioning process
- [x] T096 Do not add OAuth/JWT auth unless SSH-signature administration stops meeting operator needs
- [x] T097 Do not add Vite/SPA integration for the bootstrap UI; prefer server-rendered/HTMX follow-up work
