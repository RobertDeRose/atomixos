# Provisioning API Privilege Separation

The network-facing provisioning API runs as the unprivileged `atomixos-provision` user. It validates and renders
complete candidates in tmpfs and queues bounded jobs. A root worker, started by a systemd path unit, independently
verifies each staged job before it promotes and activates anything. The original plan is in the
[design record](design.md); Beads tracks the work under `atomixos-vfi`.

## What changed for users

- First-boot submission, bootstrap CSRF protection, SSH-signed re-apply, partial endpoints, asynchronous jobs, recovery,
  export, activation, and rollback all work as before.
- The job queue has a fixed capacity.
- Job state survives a service restart through result files.
- Rejected or tampered jobs never change `/data`.

## How it fits in

The HTTP process parses network input and stages candidates without privileges. The root worker verifies the exact
signed request, consumes authorization nonces in root-owned state, and is the only component that re-renders
candidates, promotes them, and applies users, network and firewall settings, Quadlet units, and rollback. Atomic ready
markers, root-controlled parent directories, manifest hashes, path, mode, and owner checks, active administrator keys,
and an allowlist of operations define the trust boundary.

## Running it

Queue, active, and result state lives under `/run/atomixos-provision`; desired state stays under `/data/config`. The
FIFO queue accepts jobs up to its configured capacity, and one root worker applies them one at a time. At boot, the
worker recovers interrupted jobs before it accepts new work.

## Differences from the design

Snapshot verification, queue ordering, result recovery, ownership checks, and systemd sandbox settings were tightened
without changing the staged-worker design. Apply receipts distinguish an incomplete promotion from a commit backed by a
successful activation, so recovery after an interruption cannot report success too early.

## Not included

- A setuid helper, direct writes to `/data` from the HTTP process, heavyweight IPC or a database, and arbitrary
  privileged commands. New kinds of change must use the same manifest and allowlist model.

## Tests

- `scripts/atomixos_provision/tests/test_staging.py`, `test_jobs.py`, and `test_state.py`: staging manifests, hashes,
  path normalization, unsafe entries, queueing, state recovery, tampering, rollback, and result reporting.
- `nix/tests/first-boot-provision.nix`: the unprivileged service and root worker on a VM.

## Related pages

- [Runtime Boundaries](../../runtime-boundaries.md)
- [Provisioning](../../provisioning.md)
- [Data Flow](../../data-flow.md)
- `modules/first-boot.nix`
