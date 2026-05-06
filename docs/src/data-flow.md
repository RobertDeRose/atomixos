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

| Output                   | Path                                     |
|--------------------------|------------------------------------------|
| Imported source config   | `/data/config/config.toml`               |
| Admin SSH keys           | `/data/config/ssh-authorized-keys/admin` |
| WAN inbound policy       | `/data/config/firewall-inbound.json`     |
| LAN runtime settings     | `/data/config/lan-settings.json`         |
| Required health units    | `/data/config/health-required.json`      |
| Rendered Quadlets        | `/data/config/quadlet/*.container`       |
| Quadlet runtime metadata | `/data/config/quadlet-runtime.json`      |
| Bundle payload files     | `/data/config/files/`                    |

`first-boot.service` fails before RAUC slot confirmation if Quadlet sync, LAN runtime apply, or provisioned firewall apply
fails.

## Update Flow

`os-upgrade.service` sends the compact lowercase 12-hex eth0 MAC in `X-Device-ID`, compares available bundle metadata
with the booted version, downloads the bundle to `/data`, installs it with RAUC, and reboots into the newly selected slot.

`os-verification.service` commits a slot only after service, network, LAN, and required-unit checks remain healthy through
the sustained verification window.

## Firewall and LAN Apply Flow

`lan-gateway-apply.service` consumes `/data/config/lan-settings.json`, writes the eth1 network drop-in, updates dnsmasq
and chrony runtime snippets, and restarts the affected services. `provisioned-firewall-inbound.service` consumes
`/data/config/firewall-inbound.json` and adds only the requested WAN inbound nftables rules. The baseline firewall keeps
new eth0 inbound traffic denied unless provisioned state opens a port.

## Application Runtime Flow

Provisioned Quadlets are rendered under `/data/config/quadlet/`, mirrored into the active rootful or rootless systemd
Quadlet search path, and described by `/data/config/quadlet-runtime.json`. Rootless containers are constrained to pasta
networking with loopback publish rewrites; privileged rootful containers use host networking.
