# Scripts

Shell scripts in `scripts/` and `.mise/tasks/` implement the runtime services and build/provisioning tooling.

## Build Scripts (Nix Derivation Templates)

These scripts run inside Nix derivations. Variables like `@kernel@` are substituted by Nix at build time.

### build-squashfs.sh

**Location:** `scripts/build-squashfs.sh`

Builds the squashfs rootfs image from a NixOS closure.

| Input             | Description                                |
|-------------------|--------------------------------------------|
| `@systemClosure@` | Path to `system.build.toplevel`            |
| `@closureInfo@`   | Closure info (contains `store-paths` file) |
| `@maxSize@`       | Maximum image size in bytes                |

**Steps:** Copy store paths to pseudo-root, create init symlinks and mount-point dirs, run `mksquashfs` with zstd/19,
check size limit.

### build-rauc-bundle.sh

**Location:** `scripts/build-rauc-bundle.sh`

Builds a signed RAUC bundle (`.raucb`).

| Input                            | Description                                            |
|----------------------------------|--------------------------------------------------------|
| `@kernel@`                       | Kernel package (contains `Image` and `dtbs/`)          |
| `@dtbPath@`                      | Relative DTB path (e.g., `rockchip/rk3328-rock64.dtb`) |
| `@squashfs@`                     | Squashfs image directory                               |
| `@signingCert@` / `@signingKey@` | RAUC signing credentials                               |
| `@version@`                      | Bundle version string                                  |

**Steps:** Create 128 MB vfat with kernel + DTB (mtools), generate manifest, sign with `rauc bundle`.

### build-image.sh

**Location:** `scripts/build-image.sh`

Assembles the flashable disk image.

| Input                               | Description       |
|-------------------------------------|-------------------|
| `@kernel@`, `@initrd@`, `@dtbPath@` | Kernel artifacts  |
| `@squashfs@`                        | Squashfs image    |
| `@bootScript@`                      | Compiled boot.scr |
| `@uboot@`                           | U-Boot package    |
| `@imageName@`                       | Output filename   |

**Steps:** Create sparse image, write U-Boot at raw offsets, zero U-Boot environment regions, create GPT with sfdisk,
create vfat boot partitions (mtools), write squashfs to rootfs-a.

---

## Runtime Scripts

These scripts run on the device at runtime, invoked by systemd services.

### boot.cmd

**Location:** `scripts/boot.cmd`

U-Boot boot script implementing A/B slot selection with boot-count rollback. Compiled to `boot.scr` by `mkimage`.

**Key logic:**

1. Echo build ID (squashfs store hash) to console for identification
2. Set defaults: `BOOT_ORDER="A B"`, `BOOT_A_LEFT=3`, `BOOT_B_LEFT=3`
3. Auto-detect boot device number from `devnum`
4. Override `ramdisk_addr_r=0x08000000` (avoids kernel overlap)
5. Check for `slot_good` flag file on the active slot's boot FAT partition — if found, restore `BOOT_x_LEFT=3`,
   `saveenv`, and delete the flag via `fatrm`
6. Iterate `BOOT_ORDER`; for each slot with remaining attempts: decrement counter, `saveenv`, load kernel/initrd/DTB
   from boot partition, set `root=PARTLABEL=rootfs-x`, `booti`
7. If no slot bootable: print error and drop to U-Boot shell (changed from `reset` to allow debugging)

**Console:** `ttyS2,1500000` (Rock64 UART2)

### fw_env.config

**Location:** `scripts/fw_env.config`

Configuration for `fw_setenv` / `fw_printenv` (userspace U-Boot env tools). **No longer installed to `/etc/` on the
device** — kept in the repo for reference and debugging only. Raw eMMC writes from Linux brick NCard eMMC modules;
the FAT flag file approach is used instead (see boot.cmd).

| Entry       | Offset     | Size             |
|-------------|------------|------------------|
| Primary env | `0x3F8000` | `0x8000` (32 KB) |

Device: `/dev/mmcblk1` — single copy only (no `CONFIG_ENV_REDUNDANT` in Rock64 U-Boot)

### os-verification.sh

**Location:** `scripts/os-verification.sh`

Post-update health check. Runs after every boot (except first).

**Checks performed:**

1. RAUC slot status -- skip if already committed
2. `dnsmasq.service` is active
3. `chronyd.service` is active
4. `eth0` has a WAN IP
5. `eth1` has `172.20.30.1`
6. Containers from health manifest are `running` (5 min timeout)
7. Sustained 60s check (every 5s): dnsmasq still active, no container restarts
8. On success: `rauc status mark-good`

**Dependencies:** `rauc`, `podman`, `jq`, `systemctl`, `ip`

### os-upgrade.sh

**Location:** `scripts/os-upgrade.sh`

OTA update polling script. Checks for new RAUC bundles and installs them.

**Environment:** `OS_UPGRADE_URL` (update server base URL)

**Steps:**

1. Get current version from `rauc status` and device ID from eth0 MAC
2. Query `$URL/api/v1/updates/latest` with version and device headers
3. If newer version found: download to `/persist/config/bundles/`, `rauc install`, reboot
4. Non-fatal on network errors (timer retries later)

### first-boot.sh

**Location:** `scripts/first-boot.sh`

First-boot initialization. Writes boot confirmation flag and sentinel.

**Steps:**

1. Check for `/persist/.completed_first_boot` — exit if exists
2. Write `slot_good` flag file to `/boot` (boot FAT partition) — U-Boot will restore boot counter on next power cycle
3. Write timestamp to sentinel file `/persist/.completed_first_boot`

### ssh-wan-toggle.sh

**Location:** `scripts/ssh-wan-toggle.sh`

Boot-time SSH-on-WAN rule application.

**Logic:** If `/persist/config/ssh-wan-enabled` exists, add nftables rule `iifname "eth0" tcp dport 22 accept` with
comment `SSH-WAN-dynamic`.

### ssh-wan-reload.sh

**Location:** `scripts/ssh-wan-reload.sh`

Runtime SSH-on-WAN toggle (remove and re-add rule).

**Logic:** Find and delete existing `SSH-WAN-dynamic` rule by handle, then re-add if flag file exists. Idempotent.

---

## mise Task Scripts

These are the `.mise/tasks/` scripts invoked via `mise run`.

### flash

**Location:** `.mise/tasks/flash`

Cross-platform disk flasher (macOS + Linux).

| Flag        | Description                                |
|-------------|--------------------------------------------|
| `<disk>`    | Target device (e.g., `/dev/disk4`)         |
| `-i <path>` | Image file (auto-detects if not specified) |
| `-y`        | Skip confirmation                          |

**macOS features:** Converts `/dev/diskN` to `/dev/rdiskN` for unbuffered I/O; refuses to write to boot disk; ejects
after flash.

### serial:capture

**Location:** `.mise/tasks/serial/capture`

Serial console capture wrapper with auto-reconnect.

| Flag   | Default                      | Description       |
|--------|------------------------------|-------------------|
| `-p`   | `/dev/cu.usbserial-DM02496T` | Serial device     |
| `-l`   | `/tmp/rock64-serial.log`     | Log file          |
| `-t`   | `0` (infinite)               | Capture timeout   |
| `--bg` | (flag)                       | Run in background |

Launches `scripts/serial-capture.py` in a `nix-shell` with pyserial.

### serial:shell

**Location:** `.mise/tasks/serial/shell`

Interactive serial console via minicom (1.5 Mbaud, no hardware flow control). Uses `nix build nixpkgs#minicom` to
resolve the minicom binary.

### config/lan-range

**Location:** `.mise/tasks/config/lan-range`

Updates LAN gateway/DHCP configuration across all files.

| Flag             | Default          | Description           |
|------------------|------------------|-----------------------|
| `--gateway-cidr` | `172.20.30.1/24` | Gateway IP and subnet |
| `--dhcp-start`   | `172.20.30.10`   | DHCP pool start       |
| `--dhcp-end`     | `172.20.30.254`  | DHCP pool end         |

Modifies: `modules/networking.nix`, `modules/lan-gateway.nix`, `scripts/os-verification.sh`.
