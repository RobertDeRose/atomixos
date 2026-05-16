# Firmware Data Flow

AtomixOS keeps immutable firmware, provisioned runtime state, and update state in separate paths so A/B slot switches do
not rewrite operator data.

## Boot Flow

1. U-Boot RAUC bootmeth selects the slot using `BOOT_ORDER` and `BOOT_x_LEFT` from the SPI environment.
2. `boot.scr` loads kernel, initrd, and DTB from the selected boot partition.
3. `boot.scr` passes `root=fstab`, `rauc.slot`, and `atomixos.lowerdev` to Linux.
4. Initrd mounts the selected squashfs rootfs as `/run/rootfs-base`.
5. `sysroot.mount` assembles `/` as OverlayFS with squashfs lowerdir and tmpfs upper/work dirs.
6. Initrd `systemd-repart` creates missing `boot-b`, `rootfs-b`, and `/data` partitions on a fresh flash.

## Provisioning Flow

Provisioning imports exactly one operator configuration into `/data/config/` from `/boot/config.toml` on fresh flash, a
USB seed, a supported seed bundle, or the LAN bootstrap console.

Persisted outputs are:

| Output                   | Path                                      |
|--------------------------|-------------------------------------------|
| Imported source config   | `/data/config/config.toml`                |
| Managed users            | `/data/config/users.json`                 |
| User SSH keys            | `/data/config/ssh-authorized-keys/<user>` |
| WAN inbound policy       | `/data/config/firewall-inbound.json`      |
| LAN runtime settings     | `/data/config/lan-settings.json`          |
| OS upgrade settings      | `/data/config/os-upgrade.json`            |
| Required health units    | `/data/config/health-required.json`       |
| Rendered Quadlets        | `/data/config/quadlet/*.container`        |
| Quadlet runtime metadata | `/data/config/quadlet-runtime.json`       |
| Managed user tracking    | `/data/config/managed-users.json`         |
| Bundle payload files     | `/data/config/files/`                     |

`first-boot.service` fails before RAUC slot confirmation if Quadlet sync, LAN runtime apply, or provisioned firewall apply
fails.

## Re-Apply Flow

Mutating bootstrap POST paths on an already-provisioned device require SSH signature authentication. The operator
requests a nonce via `GET /api/nonce`, then signs a request-bound message containing the nonce, target path, and
SHA-256 digest of the submitted config payload (`ssh-keygen -Y sign -n atomixos-reapply`). The request includes the
nonce and base64 signature in the `X-Atomicnix-Nonce` and `X-Atomicnix-Signature` headers. Nonces are single-use and
expire after 5 minutes (configurable via `ATOMIXOS_NONCE_TTL`).

Re-apply uses atomic candidate promotion:

1. Validate and render candidate config in `/data/config-candidate/`.
2. Rename active `/data/config` to `/data/config-rollback`.
3. Rename candidate to `/data/config`.
4. Run activation services synchronously (user apply, Quadlet sync, LAN apply, firewall).
5. On success, clean up `/data/config-rollback`.
6. On failure, restore `/data/config-rollback` to `/data/config` and re-activate.

First provisioning (no existing `config.toml`) remains unauthenticated and writes directly.

## Managed Users Flow

`atomixos-apply-users.service` materializes managed users from `/data/config/users.json` on every boot and after
re-apply. It runs before `sshd.service` so accounts exist before SSH accepts connections. Admin users are added to the
`wheel` group. Users removed from the config are locked (`expiredate=1`, `shell=/sbin/nologin`). Protected image users
(`root`, `appsvc`) are never created or locked by this service.

## Update Flow

`os-upgrade.service` reads `/data/config/os-upgrade.json` when present, falls back to the module-configured update URL for
legacy deployments, and skips polling cleanly when no update server is configured. When polling is configured, it sends
the compact lowercase 12-hex eth0 MAC in `X-Device-ID`, compares available bundle metadata with the booted version,
downloads the bundle to `/data`, installs it with RAUC, and reboots into the newly selected slot.

`os-verification.service` commits a slot only after service, network, LAN, and required-unit checks remain healthy through
the sustained verification window.

## Firewall and LAN Apply Flow

`lan-gateway-apply.service` consumes `/data/config/lan-settings.json`, writes the eth1 network drop-in, updates dnsmasq
and chrony runtime snippets, and restarts the affected services. `provisioned-firewall-inbound.service` consumes
`/data/config/firewall-inbound.json` and applies the requested WAN and LAN nftables rules for the configured scopes.
WAN remains deny-by-default unless explicitly opened. LAN is open by default, but an explicit `lan` scope replaces that
default-open rule with an allowlist of the configured ports merged with platform-required LAN ports.

## Application Runtime Flow

Provisioned Quadlets are rendered under `/data/config/quadlet/`, mirrored into the active rootful or rootless systemd
Quadlet search path, and described by `/data/config/quadlet-runtime.json`. Rootless containers are constrained to pasta
networking with loopback publish rewrites; privileged rootful containers use host networking.
