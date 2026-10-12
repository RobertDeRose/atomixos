# Provisioning API Service

## Delivery Summary

- Beads feature root: `atomixos-dhe`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS now provides a long-lived, socket-activated Litestar provisioning service backed by one desired-state apply
pipeline. It supports authenticated config submission, validation, asynchronous jobs, health reporting, first-boot UI
flows, maintenance commands, and deterministic complete config-bundle export and import.

The portable bundle contains canonical `config.toml` plus managed `files/` payloads. Export excludes generated runtime
state and device-generated signer material, takes a locked snapshot, enforces the importer's archive limits and safe
member types, and produces stable bytes for equivalent input. Bundles can contain secrets stored in `config.toml` or
managed files, such as TLS private keys, so treat exported bundles as sensitive.

## User-Facing Behavior

Fresh devices accept bootstrap provisioning without an SSH signature while provisioned devices require the documented
nonce and SSH-signature flow. Production admission uses a bounded FIFO and a serialized privileged worker; direct test
or development roots retain a one-active-job guard. Clients receive typed job and error responses and poll the job API
for progress and completion.

Bundle export downloads `config-bundle.tar.gz`, which can be validated and imported through the existing CLI. Fleet
bootstrap keeps ownership of its transport and does not invoke the local network-source reconciliation path. Managed
files are installed read-only by default, while trusted integrators retain full Podman configuration control and receive
an advisory warning for writable `${FILES_DIR}` mounts. Production exports use a dedicated UUID-correlated root worker
so workload-owned private files remain exportable without changing their permissions. Mutable application data should
normally live in Podman volumes and remains outside config export.

## Design Integration

The service preserves `config.toml` as the desired-state authority and reuses validation, rendering, candidate
promotion, activation, health checking, and rollback for every mutation path. The network-facing process remains
unprivileged; the apply worker alone performs durable promotion and activation. A separate fixed-purpose export worker
reads only the bundle allowlist and atomically publishes API-readable results through a `systemd.path` request boundary.
Systemd socket activation and the
existing first-boot and SSH-signature trust boundaries remain intact. A single staged-apply transaction component owns
durable receipt phases, interrupted-promotion recovery, and abandoned-job result finalization.

## Operational Impact

Desired state and managed payloads remain under `/data/config`; transient queue, active-job, and result state lives
under `/run/atomixos-provision`. Operators can validate, import, and reapply bundles with the
`first-boot-provision` command; authenticated export is provided by `GET /api/config/export`. Podman volume backup,
restore, and transfer remain operator-managed through Podman tooling. The squashfs result is 418.5 MB, below the 1 GiB
closure budget.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Firmware Data Flow](../../data-flow.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Testing](../../testing.md)
- [Module Reference](../../code-reference/modules.md)
- [Script Reference](../../code-reference/scripts.md)
- [Flash Image Provisioning](../../provisioning/flash-image.md)

## Validation Evidence

- Provisioning package tests cover authentication, typed responses, queue admission, state recovery, bundle safety,
  deterministic export, export worker admission and recovery, and complete import/export round trips. Two
  Linux-setgid-specific staging assertions run only on Linux.
- The `first-boot-provision`, `first-boot-source-discovery`, and `provisioning-export` NixOS VM checks exercise the
  staged apply path and the production export worker on the target platform.

## Design Reconciliation

### Delivered as Designed

The package boundary, socket activation, SSH-signature contract, typed API responses, bounded production FIFO,
serialized privileged execution, atomic promotion, activation, health checks, rollback, and complete portable bundle
contract were delivered without creating a second desired-state path.

### Intentional Changes

Target validation exposed stale VM fixtures after LAN defaults were centralized and bundle export became an archive.
Those fixtures now install the production defaults contract and inspect exported `config.toml` from the bundle. Fleet
bootstrap also received an explicit transport guard so it cannot invoke local bootstrap reconciliation.

Production export runs through a dedicated root worker with UUID-correlated requests and results, so workload-owned
private files are exported without loosening their permissions. The worker bounds admission, finalizes interrupted
requests, keeps a request claimed until its archive or error is published, and expires abandoned state. Export applies
the importer's limits instead of its own budget and omits parent directories that the importer recreates, so any tree
the importer accepted can be exported.

### Deferred Work

True live `pulling` status remains deferred until activation can consume a reliable journal, Podman event, or direct
Podman operation stream. It does not change the delivered job-state or service-status contract.

### Rejected or Removed Scope

A database, Redis-backed queue, fleet orchestration, default credentials, arbitrary patch semantics, and export of
generated runtime state, Podman volume data, or signer material remain intentionally excluded.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/data-flow.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/provisioning/flash-image.md`
- `docs/src/introduction.md`
- `docs/src/testing.md`
- `docs/src/code-reference/modules.md`
- `docs/src/code-reference/scripts.md`
- affected feature design records, navigation, and roadmap pages

## Audit Trail

Delivery history, review findings, and validation runs are recorded in Beads under `atomixos-dhe`.
