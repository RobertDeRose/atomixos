# NixOS Modules

All NixOS modules live in the `modules/` directory. `base.nix` imports all service modules and is itself imported by the
hardware-specific modules (`hardware-rock64.nix`, `hardware-qemu.nix`).

## Module Dependency Graph

```text
hardware-rock64.nix ──┐
                      ├──> base.nix ──> imports 11 service modules
hardware-qemu.nix  ───┘

base.nix imports:
  ├── networking.nix
  ├── firewall.nix
  ├── lan-gateway.nix
  ├── openvpn.nix
  ├── rauc.nix
  ├── cockpit.nix
  ├── traefik.nix
  ├── first-boot.nix
  ├── os-verification.nix
  ├── os-upgrade.nix
  └── watchdog.nix
```

---

## base.nix

**Purpose**: Shared NixOS configuration for both hardware and QEMU targets. Defines the core system layout, filesystem
mounts, user accounts, and system packages.

**Key configuration:**

| Setting                        | Value       | Notes                             |
|--------------------------------|-------------|-----------------------------------|
| `system.stateVersion`          | `"25.11"`   | NixOS release                     |
| `networking.hostName`          | `"gateway"` |                                   |
| `nix.enable`                   | `false`     | No Nix daemon on read-only rootfs |
| `documentation.enable`         | `false`     | Saves closure space               |
| `security.sudo.enable`         | `false`     | Uses `run0` instead               |
| `virtualisation.podman.enable` | `true`      | Container runtime                 |

**Filesystem layout (OverlayFS root):**

The root filesystem uses a single OverlayFS set up in the initrd (via `boot.initrd.postMountCommands`):

| Layer              | Mount            | Filesystem | Size   | Description                                    |
|--------------------|------------------|------------|--------|------------------------------------------------|
| overlay (combined) | `/`              | overlay    | --     | Unified writable root presented to userspace   |
| lower (read-only)  | `/media/root-ro` | squashfs   | --     | Immutable NixOS system (`PARTLABEL=rootfs-a`)  |
| upper (writable)   | `/media/root-rw` | tmpfs      | 256 MB | Ephemeral writes, lost on reboot               |
| persistent state   | `/persist`       | f2fs       | ~13 GB | Survives reboots (`PARTLABEL=persist`, nofail) |

The overlay is assembled in the initrd after the squashfs root is mounted at `/mnt-root` but before `switch_root`:

1. Move squashfs from `/mnt-root` to `/mnt-lower`
2. Mount tmpfs (256 MB) at `/mnt-upper`, create `upper/` and `work/` dirs
3. Mount overlay at `/mnt-root` with `lowerdir=/mnt-lower,upperdir=/mnt-upper/upper,workdir=/mnt-upper/work`
4. Move layers into final root at `/mnt-root/media/root-ro` and `/mnt-root/media/root-rw`

This approach replaces per-directory tmpfs mounts, which broke systemd's mount namespace sandboxing (PrivateTmp,
ProtectHome, etc.). The overlay presents a single writable filesystem, so mount propagation works correctly.

**First-boot persist partition:** Created by a custom `create-persist.service` (not upstream `systemd-repart`) that
fixes the GPT backup header (`sfdisk --relocate`) after the smaller image is dd'd onto the larger eMMC, then invokes
`systemd-repart` with an explicit device path.

**tmpfiles.d rules** (created on boot):

```text
/var/empty, /var/lib, /var/lib/systemd/network, /var/lib/private,
/var/lib/private/systemd/resolve, /var/lib/chrony, /var/lib/dnsmasq,
/var/cache, /var/cache/nscd, /var/log, /var/log/journal, /var/db, /var/run
```

**User accounts:**

| User    | Groups            | Authentication                                                                                                |
|---------|-------------------|---------------------------------------------------------------------------------------------------------------|
| `root`  | --                | Empty password (development)                                                                                  |
| `admin` | `wheel`, `podman` | Password from `/persist/config/admin-password-hash`; SSH key from `/persist/config/ssh-authorized-keys/admin` |

**System packages:** `nano`, `htop`, `curl`, `jq`, `f2fs-tools`, `kmod`, `python3Minimal`

---

## hardware-rock64.nix

**Purpose**: Rock64 (RK3328) hardware-specific kernel, device tree, and RAUC slot mapping.

**Kernel configuration:**

| Category    | Drivers                                                          | Build           |
|-------------|------------------------------------------------------------------|-----------------|
| eMMC        | `MMC_DW`, `MMC_DW_ROCKCHIP`                                      | built-in (`=y`) |
| Ethernet    | `STMMAC_ETH`, `DWMAC_ROCKCHIP`                                   | built-in        |
| USB         | `DWC2`, `USB_XHCI_HCD`, `USB_EHCI_HCD`, `USB_OHCI_HCD`           | built-in        |
| Watchdog    | `DW_WATCHDOG`                                                    | built-in        |
| Filesystems | `SQUASHFS`, `SQUASHFS_ZSTD`, `F2FS_FS`, `OVERLAY_FS`             | built-in        |
| WiFi        | `RTL8XXXU`, `ATH9K_HTC`, `MT76_USB`, `MT7601U`, `RTW88`, `RTW89` | module (`=m`)   |
| Bluetooth   | `BT`, `BT_HCIBTUSB`                                              | module          |
| USB Serial  | `FTDI_SIO`, `CP210X`                                             | module          |

**RAUC slot mapping:**

```nix
atomixos.rauc.slots = {
  boot0 = "/dev/mmcblk1p1";     # boot-a
  boot1 = "/dev/mmcblk1p2";     # boot-b
  rootfs0 = "/dev/mmcblk1p3";   # rootfs-a
  rootfs1 = "/dev/mmcblk1p4";   # rootfs-b
};
```

**Serial console:** `ttyS2` at 1.5 Mbaud (Rock64 UART2), enabled via `serial-getty@ttyS2.service`.

---

## hardware-qemu.nix

**Purpose**: QEMU aarch64-virt configuration for development and testing.

**Differences from hardware-rock64.nix:**

| Setting        | Rock64            | QEMU                             |
|----------------|-------------------|----------------------------------|
| Boot method    | U-Boot `boot.scr` | extlinux                         |
| Block devices  | `/dev/mmcblk1pN`  | `/dev/vdN` (virtio)              |
| RAUC backend   | `uboot`           | `custom` (file-based)            |
| Kernel modules | Hardware-specific | `virtio_pci`, `virtio_blk`, etc. |

---

## networking.nix

**Purpose**: Deterministic NIC naming and systemd-networkd configuration.

**Link files:**

| Priority         | Match                                        | Result         |
|------------------|----------------------------------------------|----------------|
| `10-onboard-eth` | Platform `platform-ff540000.ethernet`        | Name = `eth0`  |
| `20-usb-eth`     | Drivers `r8152`, `ax88179_178a`, `cdc_ether` | Kernel default |
| `30-wifi`        | WiFi drivers                                 | Kernel default |

**Network files:**

| Priority | Interface | Configuration                            |
|----------|-----------|------------------------------------------|
| `10-wan` | `eth0`    | DHCP v4, uses DHCP DNS, no NTP from DHCP |
| `20-lan` | `eth1`    | Static `172.20.30.1/24`, no DHCP         |

**Sysctl:** `net.ipv4.ip_forward = 0`, `net.ipv6.conf.all.forwarding = 0`

---

## firewall.nix

**Purpose**: nftables firewall with per-interface rules and dynamic SSH-on-WAN toggle.

**nftables rules (inet filter):**

| Chain     | Policy | Rules                                                                                                    |
|-----------|--------|----------------------------------------------------------------------------------------------------------|
| `input`   | drop   | lo: accept; established: accept; eth0: TCP 443, UDP 1194; eth1: UDP 67-68, UDP 123, TCP 22; tun0: TCP 22 |
| `forward` | drop   | (no exceptions)                                                                                          |
| `output`  | accept |                                                                                                          |

**Dynamic SSH toggle services:**

| Service          | When                  | What                                          |
|------------------|-----------------------|-----------------------------------------------|
| `ssh-wan-toggle` | Boot (after nftables) | Reads flag file, adds SSH rule if present     |
| `ssh-wan-reload` | On demand             | Removes old rule, re-adds if flag file exists |

Flag file: `/persist/config/ssh-wan-enabled`

---

## lan-gateway.nix

**Purpose**: DHCP and NTP server for isolated LAN devices.

**dnsmasq configuration:**

| Setting        | Value                                        |
|----------------|----------------------------------------------|
| Interface      | `eth1` (bind-interfaces)                     |
| DHCP range     | `172.20.30.10` -- `172.20.30.254`, 24h lease |
| Gateway option | `172.20.30.1`                                |
| DNS option     | (empty -- no DNS forwarding)                 |
| NTP option     | `172.20.30.1`                                |
| DNS port       | `0` (disabled)                               |

**chrony configuration:**

| Setting  | Value                      |
|----------|----------------------------|
| Upstream | `pool pool.ntp.org iburst` |
| Serve to | `172.20.30.0/24` only      |
| Fallback | `local stratum 10`         |

---

## rauc.nix

**Purpose**: RAUC A/B update system configuration. Defines custom NixOS options and generates `/etc/rauc/system.conf`.

**Custom NixOS options (`atomixos.rauc.*`):**

| Option          | Type   | Default                      | Description                  |
|-----------------|--------|------------------------------|------------------------------|
| `compatible`    | string | `"rock64"`                   | RAUC compatible string       |
| `bootloader`    | string | `"uboot"`                    | Backend: `uboot` or `custom` |
| `statusFile`    | string | `/persist/rauc/status.raucs` | RAUC status file             |
| `slots.boot0`   | string | (required)                   | Boot slot A device path      |
| `slots.boot1`   | string | (required)                   | Boot slot B device path      |
| `slots.rootfs0` | string | (required)                   | Rootfs slot A device path    |
| `slots.rootfs1` | string | (required)                   | Rootfs slot B device path    |

When `bootloader = "custom"`, a file-based shell script is generated that simulates U-Boot environment management using
files in `/var/lib/rauc/`.

---

## cockpit.nix

**Purpose**: Cockpit web UI as a podman container.

| Setting         | Value                                          |
|-----------------|------------------------------------------------|
| Image           | `quay.io/cockpit/ws`                           |
| Network         | Host networking                                |
| Listen          | `127.0.0.1:9090` (loopback, no TLS)            |
| TLS termination | Traefik (port 443)                             |
| Volumes         | `/persist/config/cockpit:/etc/cockpit:ro`      |
| Ordering        | After `network-online.target`, `podman.socket` |

---

## traefik.nix

**Purpose**: Traefik v3 reverse proxy as a podman container.

| Setting  | Value                                                                    |
|----------|--------------------------------------------------------------------------|
| Image    | `docker.io/library/traefik:v3`                                           |
| Network  | Host networking                                                          |
| Listen   | `0.0.0.0:443` (TLS), `0.0.0.0:80` (redirect)                             |
| Volumes  | Static config, dynamic config, TLS certs from `/persist/config/traefik/` |
| Ordering | After `cockpit-ws.service`; requires `cockpit-ws.service`                |

---

## watchdog.nix

**Purpose**: systemd hardware watchdog configuration.

```nix
systemd.settings.Manager = {
  RuntimeWatchdogSec = "30s";
  RebootWatchdogSec = "10min";
};
```

---

## os-verification.nix

**Purpose**: Post-update health-check service.

| Setting   | Value                                                |
|-----------|------------------------------------------------------|
| Type      | oneshot                                              |
| Condition | `ConditionPathExists=/persist/.completed_first_boot` |
| Timeout   | 600s (10 min)                                        |
| Script    | `scripts/os-verification.sh`                         |
| PATH      | `rauc`, `podman`, `jq`, `systemd`, `iproute2`        |

---

## os-upgrade.nix

**Purpose**: OTA update polling service.

**Custom NixOS options (`os-upgrade.*`):**

| Option            | Type   | Default                      | Description                    |
|-------------------|--------|------------------------------|--------------------------------|
| `useHawkbit`      | bool   | `false`                      | Switch to rauc-hawkbit-updater |
| `pollingInterval` | string | `"1h"`                       | Timer interval                 |
| `serverUrl`       | string | `"http://localhost/updates"` | Update server URL              |

**Timer:** `OnBootSec=5min`, `OnUnitActiveSec=<pollingInterval>`, `RandomizedDelaySec=10min`

---

## first-boot.nix

**Purpose**: One-time first-boot slot confirmation.

| Setting   | Value                                                 |
|-----------|-------------------------------------------------------|
| Type      | oneshot                                               |
| Condition | `ConditionPathExists=!/persist/.completed_first_boot` |
| Script    | `scripts/first-boot.sh`                               |
| Effect    | `rauc status mark-good` + write sentinel              |

Mutually exclusive with `os-verification.service` via the sentinel file.

---

## openvpn.nix

**Purpose**: OpenVPN recovery tunnel.

| Setting     | Value                                                     |
|-------------|-----------------------------------------------------------|
| Config path | `/persist/config/openvpn/client.conf`                     |
| Auto-start  | `false`                                                   |
| Condition   | `ConditionPathExists=/persist/config/openvpn/client.conf` |
