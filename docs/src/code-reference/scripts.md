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
| `@initrd@`                       | Initrd package (contains `initrd`)                     |
| `@dtbPath@`                      | Relative DTB path (e.g., `rockchip/rk3328-rock64.dtb`) |
| `@squashfs@`                     | Squashfs image directory                               |
| `@bootScript@`                   | Compiled U-Boot script (`boot.scr`)                    |
| `@signingCert@` / `@signingKey@` | RAUC signing credentials                               |
| `@version@`                      | Bundle version string                                  |

**Steps:** Create 128 MB vfat with kernel + initrd + DTB + boot.scr (mtools), generate manifest, sign with `rauc bundle`.

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

**Steps:** Create sparse image, write U-Boot at raw offsets, create GPT with slot A partitions (`boot-a`, `rootfs-a`),
create the slot A vfat boot partition with mtools, and write squashfs to `rootfs-a`. Slot B and `/data` are created by
initrd `systemd-repart` on first boot.

---

## Runtime Scripts

These scripts run on the device at runtime, invoked by systemd services.

### watchdog-boot-count.sh

**Location:** `scripts/watchdog-boot-count.sh`

Records watchdog boot-count state and rollback decisions for the configured
RAUC bootloader backend.

**Responsibilities:**

1. Detect the active bootloader mode from `ATOMIXOS_RAUC_BOOTLOADER`
2. For the `custom` backend, decrement `/var/lib/rauc/boot-count.<slot>` on boot
3. Mark the failed slot bad and switch primary when the count is exhausted
4. For the `uboot` backend, read the post-boot `BOOT_*_LEFT` value via `fw_printenv`
5. Emit journal-visible lifecycle lines through normal stdout

### boot.cmd

**Location:** `scripts/boot.cmd`

U-Boot boot script loaded after RAUC bootmeth selects the slot and decrements the boot-count. Compiled to `boot.scr` by
`mkimage`.

**Key logic:**

1. Echo build ID (squashfs store hash) to console for identification
2. If the reset button (Linux `gpiochip3` line 4, U-Boot GPIO `100`) is held low for 10 seconds, run `ums 0 mmc 1`
   so the Rock64 OTG port exposes the full eMMC to a host computer
3. Auto-detect boot device number from `devnum`
4. Override `ramdisk_addr_r=0x08000000` (avoids kernel overlap)
5. Read RAUC bootmeth variables for selected boot/root partitions
6. Set `rauc.slot` and `atomixos.lowerdev`
7. Load kernel/initrd/DTB from the selected boot partition, set `root=fstab`, and `booti`

**Console:** `ttyS2,1500000` (Rock64 UART2)

### fw_env.config

**Location:** `scripts/fw_env.config`

Configuration for `fw_setenv` / `fw_printenv` (userspace U-Boot env tools). The installed Rock64 config points to the
single SPI flash environment exposed through `/dev/mtd0`.

| Entry       | Device      | Offset     | Size     | Erase size |
|-------------|-------------|------------|----------|------------|
| Primary env | `/dev/mtd0` | `0x140000` | `0x2000` | `0x1000`   |

The old raw eMMC environment offsets are not used.

### os-verification.sh

**Location:** `scripts/os-verification.sh`

Post-update health check. Runs after every boot (except first).

**Checks performed:**

1. RAUC slot status -- skip if already committed
2. `dnsmasq.service` is active
3. `chronyd.service` is active
4. `eth0` has a WAN IP
5. `eth1` has the provisioned gateway IP, falling back to `172.20.30.1`
6. Provisioned required units from `/data/config/health-required.json` are active
7. Sustained 60s check (every 5s): all service, network, and required-unit checks still pass
8. On success: `rauc status mark-good`

**Logging:** Emits progress and failure details through normal service output,
which is captured by `journald` and forwarded to `/data/logs` by `rsyslog`.

**Dependencies:** `rauc`, `jq`, `systemctl`, `ip`

### os-upgrade.sh

**Location:** `scripts/os-upgrade.sh`

OTA update polling script. Checks for new RAUC bundles and installs them.

**Environment:** `OS_UPGRADE_URL` (update server base URL)

**Steps:**

1. Get current version from `rauc status` and compact lowercase 12-hex device ID from eth0 MAC
2. Query `$URL/api/v1/updates/latest` with version and device headers
3. If newer version found: download to `/data/config/bundles/`, `rauc install`, reboot
4. Non-fatal on network errors (timer retries later)

**Forensics:** Emits Tier 0 install and managed reboot markers, but avoids noisy
polling or "no update" chatter in the durable forensic log.

### first-boot.sh

**Location:** `scripts/first-boot.sh`

First-boot provisioning/import/bootstrap flow plus boot confirmation.

**Steps:**

1. Check for `/data/.completed_first_boot` and exit if it already exists
2. Discover provisioning input from fresh-flash `/boot/config.toml`, USB media, or the LAN bootstrap console
3. Validate and import the config into `/data/config/`
4. Render and sync rootful and rootless Quadlet units
5. Restart Quadlet sync, LAN apply, and provisioned firewall apply services; fail before slot confirmation if LAN or
   firewall apply fails
6. Mark the current RAUC slot good when RAUC is enabled
7. Write timestamp to `/data/.completed_first_boot`

### ssh-wan-toggle.sh

**Location:** `scripts/ssh-wan-toggle.sh`

Boot-time SSH-on-WAN rule application.

**Logic:** If `/data/config/ssh-wan-enabled` exists, add nftables rule `iifname "eth0" tcp dport 22 accept` with
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
