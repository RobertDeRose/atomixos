# Feature: provisioning-api-privilege-separation

## Source

Seeded from `docs/src/planned-features.md` entry
`provisioning-api-privilege-separation` and the existing provisioning API
foundation.

## Overview

Split the network-facing provisioning API from privileged host mutation work
without using setuid Python helpers. The Litestar/uvicorn service runs as an
unprivileged user and performs HTTP handling, authentication, upload parsing,
validation, sanitization, and candidate rendering into tmpfs under
`/run/atomixos-provision`.

Root-owned systemd units then consume completed staged jobs. A `systemd.path`
unit watches for ready markers and starts a root oneshot apply service. The root
worker verifies the staged job, copies the verified candidate into a durable
`/data/config-candidate`, promotes it within `/data`, runs activation, performs
rollback on failure, and writes job results for the API to report.

This design reduces disk churn and keeps untrusted request parsing out of root.
Root still performs the final host mutation, but it consumes a narrow staged
contract instead of raw HTTP uploads or arbitrary helper commands.

## Goals

1. Run the Litestar/uvicorn provisioning service without root privileges.
2. Parse, validate, sanitize, and render submitted config sources before any root
   process handles them.
3. Stage candidate jobs in tmpfs under `/run/atomixos-provision` to avoid
   persistent writes for failed validation or render attempts.
4. Trigger privileged apply work with root-owned systemd path and oneshot service
   units, not setuid application helpers.
5. Keep root mutation limited to verifying staged jobs, writing `/data`,
   promoting configs, activating allowlisted services, and rolling back.
6. Preserve first-boot bootstrap provisioning behavior.
7. Preserve SSH-signed re-apply behavior on provisioned devices.
8. Preserve serialized applies and progress reporting while allowing bounded
   FIFO submission backpressure.
9. Document the privilege boundary, staging contract, and systemd hardening
   model.

## Non-Goals

- Adding a full multi-tenant authorization model.
- Adding remote fleet orchestration behavior.
- Replacing `config.toml` or the existing validation/render/promote/activate
  semantics.
- Adding a database, Redis, persistent privileged daemon, or heavyweight IPC
  dependency solely for privilege separation.
- Allowing arbitrary filesystem mutation through staged jobs.
- Relying on setuid Python, setuid shell scripts, or a root HTTP server.

## Constraints

- Must work with a read-only squashfs root and mutable `/data`.
- Must not regress first-boot operator workflow or bootstrap exposure controls.
- Must not weaken SSH-signature authentication for provisioned re-apply.
- Must preserve rollback-on-failure semantics.
- Must keep root operations auditable and narrowly scoped.
- Must not trust staged files without verifying ownership, mode, path, and
  content hashes.
- Must maintain EN18031-aligned defaults: no default credentials, key-only SSH,
  and no IP forwarding.

## Current Behavior

The provisioning service owns network-facing API handling and privileged host
mutation paths in one process boundary. It validates submitted configuration,
renders desired state, promotes candidates under `/data/config`, activates host
services, updates firewall/bootstrap socket state where applicable, reports job
progress, and rolls back failed activations.

The previous privilege-separation approach moved mutation behind a setuid helper.
That reduced direct root exposure for the HTTP service, but it still ran a large
Python provisioning path as root and introduced fragile setuid wrapper behavior.

## Proposed Design

### Process Boundary

Run the provisioning API service as a dedicated unprivileged system user,
`atomixos-provision`. The service remains responsible for:

- HTTP and multipart parsing
- bootstrap origin and CSRF checks
- SSH-signature authentication for provisioned re-apply
- config and bundle validation
- semantic sanitization
- rendering a complete candidate tree
- creating staged job manifests
- reporting job state to API and UI clients

Root work moves to a systemd-managed apply worker. The worker is not
network-facing and does not parse raw uploads. It consumes only completed staged
jobs from `/run/atomixos-provision`.

### Runtime Staging Layout

Use tmpfs-backed runtime state for unprivileged staging:

```text
/run/atomixos-provision/
  queue/
    <job-id>/
      manifest.json
      candidate/
        config.toml
        users.json
        ssh-authorized-keys/
        ... rendered desired state ...
      bundle-files/
        ... validated bundle files, if present ...
    <job-id>.ready
  active/
    <job-id>/
      ... atomically claimed job ...
  results/
    <job-id>.json
  config.lock
  queue.lock
```

The API service writes `<job-id>/manifest.json` and the rendered candidate tree
first. It creates `<job-id>.ready` only after staging is complete and fsynced as
far as practical for tmpfs. The ready marker is the trigger contract for systemd.
`queue/` is root-owned and group-writable by `atomixos-provision`; `results/` is
root-writable and only group-readable so the unprivileged API can report terminal
states without being able to forge them.

The root worker claims a job by atomically renaming the staged directory from
`queue/<job-id>` to `active/<job-id>` and removing or consuming the ready marker.
Claim and timeout-abandon operations share `/run/atomixos-provision/queue.lock`
so the API cannot mark a job failed while the root worker is claiming it. Only
one apply mutates `/data` at a time under `/run/atomixos-provision/config.lock`.

### Staging Manifest

Each staged job includes a bounded JSON manifest. The manifest should contain at
least:

- manifest version
- job ID
- operation type: initial apply, re-apply, or typed partial apply rendered to a
  full candidate
- source filename and source digest
- rendered candidate file list with relative paths, SHA-256 hashes, sizes, and
  expected modes
- bundle file list with relative paths, SHA-256 hashes, sizes, and expected
  modes when bundle files are present
- activation policy summary
- whether re-apply is authorized
- API service UID/GID expected to own staged files
- created timestamp

The root worker must treat the manifest as untrusted input until verification
passes.

### Root Worker Verification

Before touching `/data`, the root worker verifies:

- the job path is below `/run/atomixos-provision/active`
- the job ID and manifest filename match the ready marker that triggered work
- all paths in the manifest are relative, normalized, and do not contain `..`
- no staged path is a symlink
- every staged file is regular and every staged directory is a directory
- staged ownership is the expected `atomixos-provision` UID/GID or stricter
  root-owned state where explicitly allowed
- staged files and directories are not group/world writable
- file sizes and SHA-256 hashes match the manifest
- no unexpected top-level entries are present
- operation type and re-apply authorization are consistent with current
  `/data/config` state

Verification failure writes a failed result and discards the staged job without
mutating `/data`.

### Durable Promotion

Because `/run` and `/data` are different filesystems, root cannot atomically
rename the tmpfs candidate directly into `/data/config`. The worker should:

1. Copy verified staged state into `/data/config-candidate` with root-controlled
   ownership and modes.
2. Fsync files and directories needed for crash safety.
3. Promote `/data/config-candidate` to `/data/config` using the existing
   crash-safe promotion and rollback protocol within `/data`.
4. Run activation and health checks.
5. Roll back on activation failure.
6. Write `/run/atomixos-provision/results/<job-id>.json` with terminal state,
   warnings, rollback status, forwarding URL, and error details.

This keeps validation and render churn in tmpfs while limiting persistent writes
to the final candidate and rollback metadata.

### Systemd Units

The design uses systemd as the privilege boundary:

- `atomixos-bootstrap.service`
  - runs as `atomixos-provision`
  - owns HTTP/API/UI handling
  - writes only approved runtime staging paths and approved read-only state
  - does not execute setuid helpers

- `atomixos-provision-apply.path`
  - root-owned path unit
  - watches `/run/atomixos-provision/queue/*.ready`
  - starts `atomixos-provision-apply.service`

- `atomixos-provision-apply.service`
  - root oneshot
  - claims one ready job
  - verifies staged inputs
  - writes durable candidate state under `/data`
  - promotes, activates, rolls back, and writes result JSON
  - runs a stop-post finalizer that writes failed results for claimed jobs left
    behind if the worker is interrupted before terminal result publication

The API can poll result files and expose the same `/api/jobs/{id}` contract. If
the API service restarts, it can reconstruct terminal job state from result JSON
for recent jobs. The API accepts staged submissions into a bounded FIFO queue and
keeps only one staged job active with the root worker at a time. Polling may
abandon a job only if it is still queued under the shared queue lock; once the
root worker claims a job, the API extends the active wait until the worker or
worker finalizer writes a terminal result.

### Existing Behavior Preservation

The implementation must preserve:

- first-boot unauthenticated `POST /api/config` behavior before provisioning
- bootstrap UI CSRF behavior for browser form submission
- SSH-signature authentication for provisioned re-apply and validation endpoints
- serialized apply semantics with bounded FIFO submission backpressure
- job status/progress reporting
- crash-safe candidate promotion
- activation health checks
- rollback on failure
- config export/backup semantics

### Privileged Operation Split

Unprivileged API responsibilities:

- receive config source bytes
- unpack bundles into tmpfs
- reject unsafe bundle layouts, symlinks, oversized members, and unsupported
  entries
- parse and validate `config.toml`
- render all desired-state files into staged candidate directories
- render typed partial operations into a full candidate before staging
- create manifest hashes
- create ready markers
- report queued/running/completed job state

Root worker responsibilities:

- claim staged jobs
- verify staged paths, ownership, modes, and hashes
- re-render verified staged `config.toml` into `/data/config-candidate`
- carry forward rollback-managed state when required
- promote and recover `/data/config`
- apply managed users, firewall, LAN gateway state, Quadlet state, bootstrap
  rebinds, and activation health checks through existing allowlisted scripts and
  systemd units
- roll back on failure
- write result JSON

## Documentation Impact

- `docs/src/architecture/authentication.md`: describe the privilege boundary if
  it changes the trust model.
- `docs/src/architecture/update-rollback.md`: update only if rollback behavior or
  worker responsibilities affect recovery flow.
- `docs/src/runtime-boundaries.md`: document API/worker process boundary,
  runtime staging paths, writable paths, and service hardening.
- `docs/src/provisioning.md`: update operator-visible behavior only if commands,
  errors, or workflows change.
- `docs/src/specs/`: update any provisioning API or config re-apply specs that
  describe host mutation behavior.
- `docs/src/planned-features.md`: close out delivered behavior only after the
  systemd-worker implementation lands.
- `docs/src/features/provisioning-api-privilege-separation/tasks.md`: track
  implementation and validation.

## Validation

- Python unit tests for manifest creation, hash calculation, path normalization,
  symlink rejection, and unsafe staged tree rejection.
- Python route/job tests showing existing API behavior still produces expected
  progress, success, and failure responses.
- NixOS VM test proving the unprivileged API service stages a job and the root
  worker applies it through `systemd.path` and `systemd.service`.
- VM tests for rejected staged jobs: symlink, unexpected file, wrong hash,
  group/world writable file, wrong owner, stale ready marker, and concurrent job.
- Existing provisioning, re-apply, OpenAPI, and rollback tests remain passing.
- Security review of systemd unit hardening and the staging manifest contract.

## Success Criteria

1. The network-facing API process runs unprivileged.
2. Root does not parse raw uploads, multipart requests, or unvalidated bundle
   archives.
3. Root mutation is available only through the systemd apply worker and verified
   staged manifest contract.
4. Failed validation and rendering do not write to `/data`.
5. Apply, recover, activate, and rollback paths pass existing Python and Nix VM
   tests.
6. A VM test proves provisioning succeeds through the tmpfs staging and systemd
   worker boundary.
7. Systemd hardening and the staging trust boundary are documented.

## Risks And Tradeoffs

- The staged manifest contract adds implementation and test complexity.
- Progress reporting must bridge API memory state and root-written result files.
- The root worker must not trust the staging directory just because it is under
  `/run`.
- Copying from `/run` to `/data/config-candidate` adds one durable copy step, but
  avoids persistent writes for failed validation/render attempts.
- First-boot bootstrap behavior is security-sensitive and must not grow new
  unauthenticated post-provision mutation paths.

## Resolved Decisions

- Do not use setuid Python, setuid shell scripts, or a setuid application helper
  for the provisioning API privilege boundary.
- Use `/run/atomixos-provision` tmpfs state for API-rendered staging and job
  result exchange.
- Use root-owned `systemd.path` and oneshot service units to cross the privilege
  boundary.
- Keep durable promotion and rollback within `/data` so final config swaps remain
  filesystem-local and crash-safe.
- Treat staged results as boot-lifetime runtime state. They are retained under
  `/run/atomixos-provision/results` until tmpfs cleanup or reboot; no persistent
  job history store is introduced.
- Expose worker-owned progress as queued/running/terminal state through the
  existing job API. The production privilege boundary does not add file-backed
  root substep progress.
- Keep activation substeps in the existing allowlisted scripts and systemd units
  (`atomixos-apply-users`, `quadlet-sync`, LAN gateway, firewall, bootstrap
  rebind, and activation health checks), called by the root apply worker rather
  than moved into a new privileged daemon.

## Review Readiness

This spec is implementation-ready against the current repository direction. The
affected runtime-boundary and provisioning docs have been updated alongside the
spec, and there are no unresolved design questions that should block
implementation.
