# Data Flow

AtomixOS keeps the immutable image, the operator's configuration, and update state in separate places, so switching
A/B slots never rewrites operator data. This page follows data through each flow. The rules each component enforces
are in [Runtime Boundaries](runtime-boundaries.md).

## Boot Flow

1. U-Boot's RAUC boot method picks a slot from `BOOT_ORDER` and `BOOT_x_LEFT` in the U-Boot environment.
2. `boot.scr` loads the kernel, initrd, and DTB from that slot's boot partition.
3. `boot.scr` passes `root=fstab`, `rauc.slot`, and `atomixos.lowerdev` to Linux.
4. On a fresh flash, initrd `systemd-repart` creates the missing `boot-b`, `rootfs-b`, and `/data` partitions.
5. The initrd mounts the selected squashfs at `/run/rootfs-base`.
6. `sysroot.mount` assembles `/` as an OverlayFS: the squashfs below, tmpfs above.

## Provisioning Flow

Provisioning imports exactly one operator configuration into `/data/config/`. `first-boot.service` looks for it in this
order:

1. `/boot/config.toml`, only on a fresh flash.
2. A `config.toml` on a USB stick.
3. Otherwise, the socket-activated bootstrap console, where you upload a `config.toml` or a compressed config bundle.

USB discovery reads a plain `config.toml` only; bundles go through the console or the API. The operator steps are in
[Provisioning](provisioning.md).

Provisioning writes:

| Output                    | Path                                      |
|---------------------------|-------------------------------------------|
| Imported source config    | `/data/config/config.toml`                |
| First config marker       | `/data/config/.first-config`              |
| Managed users             | `/data/config/users.json`                 |
| User SSH keys             | `/data/config/ssh-authorized-keys/<user>` |
| WAN and LAN inbound rules | `/data/config/firewall-inbound.json`      |
| LAN runtime settings      | `/data/config/lan-settings.json`          |
| Host network settings     | `/data/config/host-network.json`          |
| Activation policy         | `/data/config/activation-policy.json`     |
| OS upgrade settings       | `/data/config/os-upgrade.json`            |
| Required health units     | `/data/config/health-required.json`       |
| Rendered Quadlets         | `/data/config/quadlet/*.container`        |
| Quadlet runtime metadata  | `/data/config/quadlet-runtime.json`       |
| Managed user tracking     | `/data/config/managed-users.json`         |
| Bundle payload files      | `/data/config/files/`                     |

If syncing Quadlets, applying LAN settings, or applying the firewall fails, `first-boot.service` fails before the slot
is confirmed.

## Re-Apply Flow

Once a device is provisioned, every configuration change must carry an admin signature; see
[Change a provisioned device](provisioning.md#change-a-provisioned-device) for the signing protocol.

The request then crosses from the unprivileged API to a root worker:

1. The API, running as `atomixos-provision`, validates the configuration and stages a complete candidate and manifest
   under `/run/atomixos-provision`, then marks it ready in a first-in, first-out queue.
2. The root worker, `atomixos-provision-apply.service`, claims the job, checks the staged files and the signature, and
   renders the configuration again from the verified bytes into `/data/config-candidate/`.
3. It renames the active `/data/config` to `/data/config-rollback` and the candidate to `/data/config`.
4. It runs activation: user apply, Quadlet sync, LAN and host network apply, and the firewall, followed by the restart,
   timing, and health rules in `/data/config/activation-policy.json`.
5. On success it marks the apply committed and removes `/data/config-rollback`.
6. On failure it restores `/data/config-rollback` and activates the restored configuration again.

`POST /api/config` returns at once with `202 Accepted`, a `job_id`, a `state`, and a `job_url`; the `Location` header
points at the same job. Poll the job to see each provisioning step, service deployment events, the final result, and
whether a rollback happened.

The typed partial endpoints use the same path. The API loads the active `config.toml`, applies the change in memory,
writes a complete candidate that keeps the existing bundle `files/`, and queues it for the same worker. A partial update
is accepted only when no other job is queued, so two partial changes can never overwrite each other.

The first configuration needs no signature: the device accepts it while neither the `.first-config` marker nor a valid
`config.toml` exists. Once either exists, a missing signer file rejects every change.

How the worker verifies jobs and recovers from interruptions is described in
[Runtime Boundaries](runtime-boundaries.md#apply-transactions-and-finalization).

## Bundle Export Flow

`GET /api/config/export` (authenticated) returns the device's configuration as a deterministic `config-bundle.tar.gz`
that the importer accepts unchanged. It contains only `config.toml` and the managed `files/` tree:

1. The API drops an empty, UUID-named request file in `/run/atomixos-provision/export/requests`.
2. A `systemd.path` unit starts the root export worker, which takes the provisioning lock and snapshots the two inputs.
3. The worker publishes the archive, or an error, under the same UUID in a results directory the API can read.
4. The API returns the archive and acknowledges the result so it can be cleaned up. Abandoned requests and results
   expire.

Generated JSON, rendered Quadlets, markers, signer keys, and the apply receipt are never exported. Podman volumes are
not part of the bundle either; back them up with Podman tools. The lock keeps exports and applies apart, but it does not
pause containers, so stop writes to managed files first if you need an application-consistent export. The archive rules
are listed in [Runtime Boundaries](runtime-boundaries.md#bundle-export).

## Managed Users Flow

`atomixos-apply-users.service` creates the accounts in `/data/config/users.json` on every boot and after every
re-apply. It runs before `sshd.service`, so accounts exist before SSH accepts connections.

- Admin users join the `wheel` group.
- Users removed from the configuration are locked (`expiredate=1`, shell `/sbin/nologin`), not deleted.
- The image users `root` and `appsvc` are never created or locked by this service.

## Update Flow

`os-upgrade.service` reads `/data/config/os-upgrade.json` and does nothing when no update server is provisioned.
Otherwise it sends the device ID and the board's RAUC compatible, skips a bundle offered for another board, compares
the server's bundle with the running version, downloads a newer bundle to `/data`, installs it with RAUC, and reboots
into the new slot. The request and response are described in
[Update Polling](architecture/update-rollback.md#update-polling). `os-verification.service` then decides
whether to keep it; see [Update and Rollback](architecture/update-rollback.md).

## Firewall and LAN Apply Flow

`lan-gateway-apply.service` reads `/data/config/lan-settings.json` and `/data/config/host-network.json`. It writes
networkd drop-ins for `wan` and `lan`, `.network` files for any other configured Ethernet interface, and runtime
snippets for `dnsmasq` and `chrony`. It restarts a service only when that service's files changed. Because
`host-network.json` is part of `/data/config`, DNS, route, and interface changes roll back with the rest of the
configuration.

`provisioned-firewall-inbound.service` reads `/data/config/firewall-inbound.json` and adds nftables rules for each
scope present. WAN stays closed unless ports are listed. LAN stays open unless a `lan` scope is present, which replaces
the open rule with an allowlist of the listed ports plus the ports the platform itself needs on the LAN.

## Application Runtime Flow

Provisioned Quadlets are rendered into `/data/config/quadlet/`, copied into the rootful or rootless systemd Quadlet
search path, and described in `/data/config/quadlet-runtime.json`. Rootless containers always use pasta networking and
publish ports on loopback only. Privileged rootful containers use host networking. The rules are in
[Runtime Boundaries](runtime-boundaries.md#quadlet-safety-boundary).
