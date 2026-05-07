# NixOS Modules

All NixOS modules live in the `modules/` directory. `base.nix` imports all service modules and is itself imported by the
hardware-specific modules (`hardware-rock64.nix`, `hardware-qemu.nix`).

## Module Dependency Graph

```mermaid
flowchart TD
    KERNEL["kernel-config.nix<br/>shared stripped kernel baseline"]

    subgraph HARDWARE["hardware targets"]
        direction LR
        ROCK64["hardware-rock64.nix"]
        QEMU["hardware-qemu.nix"]
    end

    ROCK64 --> BASE["base.nix"]
    QEMU --> BASE

    subgraph IMPORTS["base.nix imports"]
        direction LR
        LOGGING["logging.nix"]
        NETWORKING["networking.nix"]
        FIREWALL["firewall.nix"]
        LAN["lan-gateway.nix"]
        OPENVPN["openvpn.nix"]
        RAUC["rauc.nix"]
        FIRSTBOOT["first-boot.nix"]
        VERIFY["os-verification.nix"]
        UPGRADE["os-upgrade.nix"]
        WATCHDOG["watchdog.nix"]
    end

    BASE --> NETWORKING
    BASE --> LOGGING
    BASE --> FIREWALL
    BASE --> LAN
    BASE --> OPENVPN
    BASE --> RAUC
    BASE --> FIRSTBOOT
    BASE --> VERIFY
    BASE --> UPGRADE
    BASE --> WATCHDOG

    KERNEL -. shared baseline .-> ROCK64
    KERNEL -. shared baseline .-> QEMU
```

---

## base.nix

**Purpose**: Shared NixOS configuration for both hardware and QEMU targets. Defines the core system layout, filesystem
mounts, user accounts, and system packages.

**Key configuration:**

| Setting                | Value       | Notes                             |
|------------------------|-------------|-----------------------------------|
| `system.stateVersion`  | `"25.11"`   | NixOS release                     |
| `networking.hostName`  | `"gateway"` |                                   |
| `nix.enable`           | `false`     | No Nix daemon on read-only rootfs |
| `documentation.enable` | `false`     | Saves closure space               |
| `security.sudo.enable` | `false`     | Uses `run0` instead               |

**Filesystem layout (OverlayFS root):**

The root filesystem uses a single OverlayFS assembled in the initrd from the selected squashfs slot and tmpfs-backed
upper/work directories:

| Layer              | Mount                 | Filesystem | Size    | Description                                               |
|--------------------|-----------------------|------------|---------|-----------------------------------------------------------|
| overlay (combined) | `/`                   | overlay    | --      | Unified writable root presented to userspace              |
| lower (read-only)  | `/run/rootfs-base`    | squashfs   | --      | Immutable NixOS system from the selected RAUC rootfs slot |
| upper (writable)   | `/run/overlay-root/*` | tmpfs      | runtime | Ephemeral writes, lost on reboot                          |
| persistent state   | `/data`               | f2fs       | dynamic | Created on first boot (`PARTLABEL=data`, nofail, noatime) |

The overlay is assembled in the initrd before `switch_root`:

1. `boot.scr` passes `root=fstab` and `atomixos.lowerdev=/dev/...` for the selected squashfs slot
2. `initrd-prepare-overlay-lower.service` mounts that slot read-only at `/run/rootfs-base`
3. `sysroot.mount` mounts `/` as overlay with `lowerdir=/run/rootfs-base`, `upperdir=/run/overlay-root/upper`, and `workdir=/run/overlay-root/work`
4. `sysroot-run.mount` bind-mounts `/run` into the switched root

This approach replaces the older `/sysroot` mutation logic and keeps the root mount fstab-driven, which fits systemd's
initrd model more cleanly.

The lower squashfs is selected by U-Boot/RAUC, while `/data` remains outside the A/B slots and survives updates.

**Sandboxing note:** `nsncd` (the NSS lookup daemon) runs as root due to permission issues on the overlay filesystem.

**Network wait:** `systemd-networkd-wait-online` is configured with a 30s timeout and `anyInterface=true`.

**Build ID:** The NixOS login banner (`/etc/issue`) displays the build ID for easy identification.

**Data partition:** Not included in the flashable image. Initrd `systemd-repart` creates it from the remaining eMMC space
on first boot.

**tmpfiles.d rules** (created on boot):

```text
/var/empty, /var/lib, /var/lib/systemd/network, /var/lib/private,
/var/lib/private/systemd/resolve, /var/lib/chrony, /var/lib/dnsmasq,
/var/cache, /var/cache/nscd, /var/log, /var/log/journal, /var/db, /var/run
```

**User accounts:**

| User    | Groups  | Authentication                                                                 |
|---------|---------|--------------------------------------------------------------------------------|
| `root`  | --      | Locked by default; Rock64 serial-root recovery only when `_RUT_OH_=1`          |
| `admin` | `wheel` | SSH key from `/data/config/ssh-authorized-keys/admin`; password remains locked |

**System packages:** `nano`, `htop`, `curl`, `jq`, `f2fs-tools`, `kmod`

---

## logging.nix

**Purpose**: Configure the runtime logging path: volatile `journald` as
ingress, buffered `rsyslog` appends to `/data/logs`, and a shutdown flush
hook.

**Key configuration:**

| Setting           | Value                                           | Notes                                                      |
|-------------------|-------------------------------------------------|------------------------------------------------------------|
| journald storage  | `Storage=volatile`                              | Keeps runtime logs in tmpfs-backed journal storage         |
| journald cap      | `RuntimeMaxUse=32M`                             | Bounds memory use for runtime logs                         |
| rsyslog output    | buffered `omfile` appends to `/data/logs/*.log` | Uses async buffered writes instead of direct per-line sync |
| Podman log driver | `journald`                                      | Routes container stdout/stderr into the same journald path |

**Services:**

| Service                          | Purpose                                                   |
|----------------------------------|-----------------------------------------------------------|
| `syslog.service`                 | Runs `rsyslogd` and drains journald into buffered files   |
| `logging-shutdown-flush.service` | Flushes journald and asks rsyslog to sync buffered output |

This module no longer installs slot-local forensic helpers. Runtime service and
script output is expected to go to stdout/stderr under `systemd`, which places
it into `journald` and then through the buffered `rsyslog` path.

---

## hardware-rock64.nix

**Purpose**: Rock64 (RK3328) hardware-specific kernel, device tree, and RAUC slot mapping.

**Kernel configuration:**

| Category     | Drivers                                                   | Build           |
|--------------|-----------------------------------------------------------|-----------------|
| eMMC         | `MMC_DW`, `MMC_DW_ROCKCHIP`                               | built-in (`=y`) |
| Ethernet     | `STMMAC_ETH`, `DWMAC_ROCKCHIP`                            | built-in        |
| USB          | `DWC2`, `USB_XHCI_HCD`, `USB_EHCI_HCD`, `USB_OHCI_HCD`    | built-in        |
| Watchdog     | `DW_WATCHDOG`                                             | built-in        |
| Filesystems  | `SQUASHFS`, `SQUASHFS_ZSTD`, `F2FS_FS`, `OVERLAY_FS`      | built-in        |
| USB Ethernet | `USB_RTL8152`, `USB_NET_AX88179_178A`, `USB_NET_CDCETHER` | module (`=m`)   |
| USB Serial   | `FTDI_SIO`, `CP210X`                                      | module          |
| WiFi/BT      | `WLAN`, `CFG80211`, `MAC80211`, `RFKILL`, `BT`            | unsupported     |

**RAUC slot mapping:**

```nix
atomixos.rauc.slots = {
  boot0 = "/dev/mmcblk1p1";     # boot-a
  boot1 = "/dev/mmcblk1p3";     # boot-b
  rootfs0 = "/dev/mmcblk1p2";   # rootfs-a
  rootfs1 = "/dev/mmcblk1p4";   # rootfs-b
};
```

**Serial console:** `ttyS2` at 1.5 Mbaud (Rock64 UART2), enabled via `serial-getty@ttyS2.service`.

---

## kernel-config.nix

**Purpose**: Shared stripped kernel baseline used by both Rock64 and QEMU so the VM target stays close to the real
device kernel.

**Contents:**

- `baseKernelConfig`: the common stripped ARM64 gateway kernel baseline
- `optionalKernelConfig`: isolated optional USB serial support

`hardware-qemu.nix` imports this file and layers only the minimal `aarch64-virt`, virtio, and test-harness-specific
requirements on top.

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

The QEMU RAUC tests share their slot mapping through `nix/tests/rauc-qemu-config.nix`:

```nix
atomixos.rauc = {
  slots = {
    boot0 = "/dev/vdb";
    boot1 = "/dev/vdc";
    rootfs0 = "/dev/vdd";
    rootfs1 = "/dev/vde";
  };
  bootloader = "custom";
};
```

---

## networking.nix

**Purpose**: Deterministic NIC naming and systemd-networkd configuration.

**Link files:**

| Priority         | Match                                        | Result                                     |
|------------------|----------------------------------------------|--------------------------------------------|
| `10-onboard-eth` | Platform `platform-ff540000.ethernet`        | Name = `eth0`                              |
| `20-usb-eth`     | Drivers `r8152`, `ax88179_178a`, `cdc_ether` | Enabled as modules in Rock64 kernel config |
| WiFi             | Unsupported until hardware selection         | not part of current Rock64 image           |

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

| Chain     | Policy | Rules                                                                                                     |
|-----------|--------|-----------------------------------------------------------------------------------------------------------|
| `input`   | drop   | lo: accept; established: accept; eth1: accept by default; tun0: TCP 22 |
| `forward` | drop   | (no exceptions)                                                                                           |
| `output`  | accept |                                                                                                           |

**Dynamic SSH toggle services:**

| Service          | When                  | What                                          |
|------------------|-----------------------|-----------------------------------------------|
| `ssh-wan-toggle` | Boot (after nftables) | Reads flag file, adds SSH rule if present     |
| `ssh-wan-reload` | On demand             | Removes old rule, re-adds if flag file exists |

Flag file: `/data/config/ssh-wan-enabled`

**Provisioned inbound:** `/data/config/firewall-inbound.json` is applied by `provisioned-firewall-inbound.service`.
The file may contain `wan` and `lan` scopes. `wan` opens selected TCP/UDP ports on the WAN interface. `lan`, when
present with any ports, appends those ports to the platform-required LAN ports on the LAN interface.

---

## lan-gateway.nix

**Purpose**: DHCP and NTP server for isolated LAN devices.

**dnsmasq configuration:**

| Setting        | Value                                                                    |
|----------------|--------------------------------------------------------------------------|
| Interface      | `eth1` (`bind-dynamic`)                                                  |
| DHCP range     | provisioned range, fallback `172.20.30.10` -- `172.20.30.254`, 24h lease |
| Gateway option | provisioned gateway IP, fallback `172.20.30.1`                           |
| DNS option     | provisioned gateway IP (gateway-local DNS only)                          |
| NTP option     | provisioned gateway IP                                                   |
| DNS port       | `53` (local-only, no upstream forwarding)                                |

**chrony configuration:**

| Setting  | Value                                             |
|----------|---------------------------------------------------|
| Upstream | `pool pool.ntp.org iburst`                        |
| Serve to | provisioned LAN subnet, fallback `172.20.30.0/24` |
| Fallback | `local stratum 10`                                |

---

## rauc.nix

**Purpose**: RAUC A/B update system configuration. Defines project options (`atomixos.rauc.*`) and maps them onto the
upstream NixOS `services.rauc` module.

**Custom NixOS options (`atomixos.rauc.*`):**

| Option          | Type            | Default                   | Description                       |
|-----------------|-----------------|---------------------------|-----------------------------------|
| `compatible`    | string          | `"rock64"`                | RAUC compatible string            |
| `bootloader`    | enum            | `"uboot"`                 | Backend (`uboot`, `custom`, etc.) |
| `statusFile`    | string          | `/data/rauc/status.raucs` | RAUC status file                  |
| `bundleFormats` | list of strings | `[-plain, +verity]`       | Allowed bundle formats            |
| `slots.boot0`   | string          | (required)                | Boot slot A device path           |
| `slots.boot1`   | string          | (required)                | Boot slot B device path           |
| `slots.rootfs0` | string          | (required)                | Rootfs slot A device path         |
| `slots.rootfs1` | string          | (required)                | Rootfs slot B device path         |

When `bootloader = "custom"`, a file-based shell script is generated that simulates U-Boot environment management using
files in `/var/lib/rauc/`.

---

## watchdog.nix

**Purpose**: systemd hardware watchdog integration plus boot-count and rollback bookkeeping.

```nix
systemd.settings.Manager = {
  # RuntimeWatchdogSec = "30s";
  # RebootWatchdogSec = "10min";
};
```

The hardware watchdog manager settings remain disabled during development, but
`watchdog-boot-count.service` is installed so the real boot-count and rollback
path records lifecycle markers to the journal through normal service stdout.

---

## os-verification.nix

**Purpose**: Post-update health-check service.

| Setting   | Value                                             |
|-----------|---------------------------------------------------|
| Type      | oneshot                                           |
| Condition | `ConditionPathExists=/data/.completed_first_boot` |
| Timeout   | 180s                                              |
| Script    | `scripts/os-verification.sh`                      |
| PATH      | `rauc`, `jq`, `systemd`, `iproute2`               |

---

## os-upgrade.nix

**Purpose**: OTA update polling service.

**Custom NixOS options (`os-upgrade.*`):**

| Option            | Type   | Default                      | Description                              |
|-------------------|--------|------------------------------|------------------------------------------|
| `useHawkbit`      | bool   | `false`                      | Reserve hawkBit path and install package |
| `pollingInterval` | string | `"1h"`                       | Timer interval                           |
| `serverUrl`       | string | `""`                         | Optional fallback update server URL      |

**Timer:** `OnBootSec=5min`, `OnUnitActiveSec=<pollingInterval>`, `RandomizedDelaySec=10min`

`os-upgrade.service` prefers the provisioned `/data/config/os-upgrade.json` value and exits successfully without polling
when neither the provisioned config nor the legacy fallback URL is set.

When `useHawkbit = true`, AtomixOS disables the polling service and installs `rauc-hawkbit-updater`, but does not
configure an operational hawkBit systemd service in the current image.

---

## first-boot.nix

**Purpose**: One-time first-boot provisioning and optional slot confirmation, plus a persistent LAN bootstrap console.

| Setting   | Value                                                                     |
|-----------|---------------------------------------------------------------------------|
| Type      | oneshot                                                                   |
| Condition | `ConditionPathExists=!/data/.completed_first_boot`                        |
| Script    | `scripts/first-boot.sh`                                                   |
| Effect    | provision config, optionally `rauc status mark-good`, then write sentinel |

Mutually exclusive with `os-verification.service` via the sentinel file.

`atomixos-bootstrap.service` runs `first-boot-provision serve` on the LAN bootstrap endpoint and remains available after
provisioning so operators can recover or reprovision without re-imaging.

---

## openvpn.nix

**Purpose**: OpenVPN recovery tunnel.

| Setting     | Value                                                  |
|-------------|--------------------------------------------------------|
| Config path | `/data/config/openvpn/client.conf`                     |
| Auto-start  | `false`                                                |
| Condition   | `ConditionPathExists=/data/config/openvpn/client.conf` |
