# Provisioning API Service

## Delivery Summary

- Beads feature root: `atomixos-dhe`
- Status: delivered locally
- Pull request: not created
- Delivery: ready on `feat/provisioning-api-service`; no merge or push has occurred
- Design record: [design.md](design.md)
- Completion commits: `2a08b9a65be7a92bf5fac3fa125759d5882bc7d0`,
  `3dd5be205f792f4b75845702be07d86337bbfd9d`, `b498d873222f670b7287e6105a63a974aebcb78c`,
  `3a6bf5152db2ae2128c7eb9ad94801f062e2d92d`, `f61953d939fcc8efb865524b42713be5c7391e7d`,
  `0a82f208e3b247e168a49323e82ea0d8ab5aaa3b`, `7c01d8d94e4e18f0db92d9c49ebcff25ca33f055`, and
  `6bcf58585cc11757aaaf75538c468fbff464b1d3`; pinned formatting was finalized in
  `92fc15567ba6a129e4595b331dd562bd5044e5a9`

## Delivered Capability

AtomixOS now provides a long-lived, socket-activated Litestar provisioning service backed by one desired-state apply
pipeline. It supports authenticated config submission, validation, asynchronous jobs, health reporting, first-boot UI
flows, maintenance commands, and deterministic complete config-bundle export and import.

The portable bundle contains canonical `config.toml` plus managed `files/` payloads. Export excludes generated runtime
state and credentials, takes a locked snapshot, enforces archive limits and safe member types, and produces stable bytes
for equivalent input.

## User-Facing Behavior

Fresh devices accept bootstrap provisioning without an SSH signature while provisioned devices require the documented
nonce and SSH-signature flow. Production admission uses a bounded FIFO and a serialized privileged worker; direct test
or development roots retain a one-active-job guard. Clients receive typed job and error responses and poll the job API
for progress and completion.

Bundle export downloads `config-bundle.tar.gz`, which can be validated and imported through the existing CLI. Fleet
bootstrap keeps ownership of its transport and does not invoke the local network-source reconciliation path.

## Design Integration

The service preserves `config.toml` as the desired-state authority and reuses validation, rendering, candidate
promotion, activation, health checking, and rollback for every mutation path. The network-facing process remains
unprivileged; the root worker alone performs durable promotion and activation. Systemd socket activation and the
existing first-boot and SSH-signature trust boundaries remain intact.

## Operational Impact

Desired state and managed payloads remain under `/data/config`; transient queue, active-job, and result state lives
under `/run/atomixos-provision`. Operators can validate, import, export, and reapply bundles with the
`first-boot-provision` command. The squashfs result is 418.5 MB, below the 1 GiB closure budget.

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
  deterministic export, and complete import/export round trips. The unfiltered macOS run passes with the two
  Linux-setgid-specific assertions explicitly skipped. Those exact permission assertions require a Linux package pytest
  run; the current target VM suite exercises staged provisioning without duplicating them.
- The exact aarch64 `first-boot-provision` and `first-boot-source-discovery` checks passed on the restored builder.
- A serialized repository-wide Nix gate passed at `92fc15567ba6a129e4595b331dd562bd5044e5a9`, including provisioning,
  fleet bootstrap, RAUC confirmation, rollback, networking, security, watchdog, and forensics VM checks.
- The aarch64 squashfs build produced a 418.5 MB result against the 1 GiB budget.
- Each discovered implementation regression received a focused check and an independent review before commit.

## Design Reconciliation

### Delivered as Designed

The package boundary, socket activation, SSH-signature contract, typed API responses, bounded production FIFO,
serialized privileged execution, atomic promotion, activation, health checks, rollback, and complete portable bundle
contract were delivered without creating a second desired-state path.

### Intentional Changes

Target validation exposed stale VM fixtures after LAN defaults were centralized and bundle export became an archive.
Those fixtures now install the production defaults contract and inspect exported `config.toml` from the bundle. Fleet
bootstrap also received an explicit transport guard so it cannot invoke local bootstrap reconciliation.

### Deferred Work

True live `pulling` status remains deferred until activation can consume a reliable journal, Podman event, or direct
Podman operation stream. It does not change the delivered job-state or service-status contract.

### Rejected or Removed Scope

A database, Redis-backed queue, fleet orchestration, default credentials, arbitrary patch semantics, and export of
generated runtime state or signer material remain intentionally excluded.

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

Specification reconciliation completed in `3dbec928ef18d91f17401edb4a6f9cccc3e3dd73`. The completion commits listed above
closed bundle, admission, error, packaging, fleet-transport, target-fixture, and formatting gaps. Exact aarch64 checks,
the serialized repository Nix gate, and the closure-budget build passed before final close-out review. Beads preserves
task-level findings, review results, validation commands, and artifact paths under the feature root.
