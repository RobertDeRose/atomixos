# Provisioning API Service

AtomixOS runs a long-lived, socket-activated Litestar provisioning service on top of one desired-state apply pipeline.
It handles authenticated configuration submission, validation, asynchronous jobs, health reporting, the first-boot UI,
maintenance commands, and deterministic export and import of complete configuration bundles. The original plan is in
the [design record](design.md); Beads tracks the work under `atomixos-dhe`.

## What changed for users

- A fresh device accepts its first configuration without an SSH signature; a provisioned device requires the nonce and
  SSH-signature flow.
- Clients get typed job and error responses and poll the job API for progress.
- **Operators** export the full configuration with `GET /api/config/export`, which downloads `config-bundle.tar.gz`.
  The bundle holds the canonical `config.toml` and the managed `files/`, and can be validated and imported with the
  `first-boot-provision` command.
- Exported bundles can contain secrets, such as TLS private keys in managed files, so treat them as sensitive.
- Managed files are installed read-only by default. A writable `${FILES_DIR}` mount is allowed for trusted integrators
  but produces a warning.

## How it fits in

`config.toml` is the desired-state authority. Every change path reuses validation, rendering, candidate promotion,
activation, health checking, and rollback. The network-facing process is unprivileged; only the apply worker promotes
and activates. A separate export worker reads only the bundle allowlist and publishes results through a `systemd.path`
request boundary, so workload-owned private files can be exported without changing their permissions. One staged-apply
transaction component owns receipt phases, recovery of interrupted promotions, and finalization of abandoned jobs.

Export takes a locked snapshot, leaves out generated runtime state and device-generated signer material, applies the
importer's archive limits and safe member types, and produces the same bytes for the same input. Any tree the importer
accepts can be exported again.

## Running it

- Desired state and managed files live under `/data/config`; queue, active-job, and result state lives under
  `/run/atomixos-provision`.
- Production uses a bounded FIFO queue and a serialized privileged worker. Direct test and development roots allow one
  active job at a time.
- Keep mutable application data in Podman volumes; volumes are not exported, and backing them up is up to the operator.
- Fleet bootstrap uses its own transport and never runs the local network-source path.
- The service fits within the 1 GiB rootfs slot budget.

## Differences from the design

- Production export runs through a dedicated root worker with UUID-correlated requests and results. It bounds
  admission, finalizes interrupted requests, keeps a request claimed until its archive or error is published, and
  expires abandoned state.
- Export follows the importer's limits instead of its own and omits parent directories the importer recreates.
- Fleet bootstrap gained an explicit guard so it cannot run local bootstrap reconciliation.

## Not included

- A live `pulling` status while images download; job and service states are reported without it.
- A database or Redis queue, fleet orchestration, default credentials, arbitrary patch semantics, and export of runtime
  state, Podman volume data, or signer material.

## Tests

- `scripts/atomixos_provision/tests/`: authentication, typed responses, queue admission, state recovery, bundle safety,
  deterministic export, the export worker, and import and export round trips. Two setgid staging tests run only on
  Linux.
- `checks.<system>.first-boot-provision`, `first-boot-source-discovery`, and `provisioning-export`: the staged apply
  path and the production export worker on a VM.

## Related pages

- [Provisioning](../../provisioning.md)
- [Data Flow](../../data-flow.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Testing](../../testing.md)
- [NixOS Modules](../../code-reference/modules.md)
- [Scripts](../../code-reference/scripts.md)
- [Flash an Image](../../provisioning/flash-image.md)
