# Provisioning API Privilege Separation

## References

- Beads feature root: `atomixos-vfi`
- Design record: [design.md](design.md)

## Delivered Capability

The network-facing provisioning API runs as the dedicated unprivileged `atomixos-provision` user. It validates and
renders complete candidates in tmpfs, publishes bounded queued jobs, and delegates durable mutation to a root
systemd-path-triggered worker that independently verifies staged content before promotion and activation.

## User-Facing Behavior

Existing first-boot config submission, bootstrap CSRF protection, SSH-signed re-apply, partial endpoints, asynchronous
jobs, recovery, export, activation, and rollback remain available. Queue capacity is bounded, job state survives service
restarts through result files, and rejected or tampered jobs never mutate `/data`.

## Design Integration

The HTTP process owns network parsing and unprivileged staging, while the root worker verifies the exact signed request,
consumes authorization nonces in root-owned state, and alone owns candidate re-rendering, promotion, users,
network/firewall apply, Quadlet activation, and rollback. Atomic ready markers, root-controlled parent directories,
manifest hashes, path/mode/owner checks, active administrator keys, and allowlisted operations define the trust boundary.

## Operational Impact

Runtime queue, active, and result state lives under `/run/atomixos-provision`; desired state remains under `/data/config`.
A bounded FIFO queue accepts up to the configured capacity and one root worker serializes mutation. Boot recovery handles
interrupted active jobs before accepting new work.

## Reference and Contracts

- [Runtime Boundaries](../../runtime-boundaries.md)
- [Provisioning](../../provisioning.md)
- [Firmware Data Flow](../../data-flow.md)
- `modules/first-boot.nix`

## Test Coverage

- Provisioning Python tests cover staging manifests, hashes, path normalization, unsafe entries, queueing, state recovery,
  tampering, rollback, and result reporting.
- `nix/tests/first-boot-provision.nix` exercises the unprivileged service and root worker boundary.

## Design Reconciliation

### Delivered as Designed

Unprivileged validation/staging, bounded FIFO jobs, atomic publication/claim, independent root verification,
root-controlled re-rendering, serialized promotion/activation, result handoff, recovery, and rollback were delivered.

### Intentional Changes

Hardening reviews refined snapshot verification, queue ordering, result recovery, ownership checks, and systemd sandbox
settings while preserving the staged-worker architecture. Apply receipts now
distinguish incomplete promotion from activation-backed commit so interruption
recovery cannot publish premature success.

### Deferred Work

No known privilege-boundary behavior is deferred. Future mutation types must use the same manifest and allowlist model.

### Rejected or Removed Scope

A setuid helper, direct HTTP-process writes to `/data`, heavyweight IPC or databases, and arbitrary privileged command
execution remain rejected.

## Documentation Updated

- `docs/src/runtime-boundaries.md`
- `docs/src/provisioning.md`
- `docs/src/data-flow.md`
- affected architecture and specification pages
