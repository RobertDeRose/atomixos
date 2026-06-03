# Tasks: provisioning-api-privilege-separation

## Feature Spec And Setup

- [x] T000 Create feature branch and worktree from `dev`
- [x] T001 Draft initial `design.md` from `docs/src/planned-features.md`
- [x] T002 Review existing provisioning API service, systemd units, scripts, and tests
- [x] T003 Identify why the setuid helper approach is not the desired boundary
- [x] T004 Redesign privilege separation around tmpfs staging and root systemd worker
- [x] T005 Identify minimal writable paths for the unprivileged API service

## Runtime Boundary Design

- [x] T010 Define `/run/atomixos-provision` directory layout, ownership, and tmpfiles rules
- [x] T011 Define staged job manifest schema and versioning
- [x] T012 Define ready marker and atomic job-claim protocol
- [x] T013 Define result JSON schema for API/worker handoff
- [x] T014 Define bounded FIFO queueing across API submissions and serialized root worker execution
- [x] T015 Define retention and cleanup policy for queue, active, and result files
- [x] T016 Define root-worker verification rules for paths, owners, modes, symlinks, hashes, and unexpected entries
- [x] T017 Define which activation steps stay as existing systemd units and which are called by the root worker
- [x] T018 Define failure, rollback, and reboot recovery behavior for queued, active, and partially promoted jobs

## Unprivileged API Implementation

- [x] T020 Run network-facing provisioning API service as `atomixos-provision`
- [x] T021 Remove setuid helper usage from the API apply path
- [x] T022 Parse and validate raw config uploads entirely in the unprivileged service
- [x] T023 Unpack and validate config bundles entirely in tmpfs staging
- [x] T024 Render complete candidate state into `/run/atomixos-provision/queue/<job-id>/candidate`
- [x] T025 Stage bundle `files/` content into `/run/atomixos-provision/queue/<job-id>/bundle-files`
- [x] T026 Render typed partial operations into full candidate configs before staging
- [x] T027 Write manifest file with hashes, sizes, expected modes, operation type, and source metadata
- [x] T028 Atomically publish ready marker only after staging is complete
- [x] T029 Poll worker result JSON and expose existing `/api/jobs/{job_id}` response shape
- [x] T030 Preserve first-boot unauthenticated `POST /api/config` behavior before provisioning
- [x] T031 Preserve bootstrap UI CSRF behavior for browser form submission
- [x] T032 Preserve SSH-signed provisioned re-apply behavior
- [x] T033 Preserve config export/backup behavior

## Root Worker Implementation

- [x] T040 Add `atomixos-provision-apply.path` to watch ready markers
- [x] T041 Add root `atomixos-provision-apply.service` oneshot worker
- [x] T042 Claim exactly one ready job by atomic rename into `/run/atomixos-provision/active`
- [x] T043 Verify staged manifest, relative paths, ownership, modes, no symlinks, hashes, and allowed entries
- [x] T044 Reject stale, malformed, or tampered staged jobs without mutating `/data`
- [x] T045 Re-render verified staged source config into `/data/config-candidate` with root-controlled ownership and modes
- [x] T046 Copy verified staged bundle files into the durable candidate with final app runtime ownership and modes
- [x] T047 Promote `/data/config-candidate` to `/data/config` using existing crash-safe promotion semantics
- [x] T048 Carry forward managed state needed for re-apply and rollback
- [x] T049 Run activation, managed-user materialization, Quadlet sync, LAN/firewall application, and bootstrap rebinding
  through allowlisted commands/units
- [x] T050 Roll back on activation or health-check failure
- [x] T051 Write terminal result JSON for success, validation rejection, activation failure, rollback status, and
  unexpected worker errors
- [x] T052 Recover or discard interrupted active jobs on boot before accepting new ready jobs

## Systemd Hardening

- [x] T060 Restrict API service writable paths to `/run/atomixos-provision` and required read-only config assets
- [x] T061 Keep API service non-root with `NoNewPrivileges=true` unless a concrete exception is required
- [x] T062 Harden API service with appropriate `ProtectSystem`, `ProtectHome`, `PrivateTmp`, and capability restrictions
- [x] T063 Harden root worker with required writable paths while allowing activation-time networking
- [x] T064 Ensure root worker is the only service that writes `/data/config-candidate`, `/data/config-rollback`, and
  promotion markers
- [x] T065 Ensure tmpfiles create runtime queue directories with root-controlled parents and service-writable leaf directories
- [x] T066 Remove obsolete setuid wrapper definitions and helper launcher code

## Tests And Validation

- [x] T100 Add Python tests for manifest creation and hash generation
- [x] T101 Add Python tests for staged path normalization and unsafe path rejection
- [x] T102 Add Python tests for symlink, wrong owner, group/world writable, wrong hash, oversized file, and unexpected
  entry rejection
- [x] T103 Add Python route/job tests for queued, running, succeeded, failed, and service-restart result recovery states
- [x] T104 Add Python tests proving failed validation/render never writes to `/data`
- [x] T105 Add automated coverage for unprivileged API apply behavior through the staged worker boundary
- [x] T106 Add Python coverage proving tampered staged jobs are rejected without `/data` mutation
- [x] T107 Add automated coverage proving activation failure rolls back and reports terminal result JSON
- [x] T108 Add Python coverage proving queued, active, missing, and finalized staged-job recovery states
- [x] T109 Keep existing provisioning tests passing
- [x] T110 Keep existing re-apply and rollback tests passing
- [x] T111 Keep OpenAPI schema tests passing if public routes are affected
- [x] T112 Run feature-specific Nix VM checks
- [x] T113 Run `hk check -a`
- [x] T114 Run final security-boundary review against the systemd worker and staging contract

## Documentation And Closeout

- [x] T900 Update `docs/src/runtime-boundaries.md` with API/staging/root-worker separation
- [x] T901 Review authentication and update/rollback architecture docs for affected trust-model changes
- [x] T902 Update provisioning docs if operator-visible behavior changes
- [x] T903 Review affected specs under `docs/src/specs/` for privilege-boundary changes
- [x] T904 Update `docs/src/planned-features.md` after the systemd-worker implementation completes
- [x] T905 Add this feature spec to `docs/src/SUMMARY.md` if feature specs are listed there
- [x] T999 Reconcile implementation, docs, specs, tests, and security review before closing the feature
