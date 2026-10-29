# Scripts

Scripts in `scripts/` and `.mise/tasks/` implement the build templates, runtime services, and developer tasks.

## Build Scripts

These templates run inside Nix derivations. Nix substitutes `@name@` placeholders at build time.

### build-squashfs.sh

Builds the squashfs rootfs from a NixOS closure. Called by `nix/squashfs.nix`.

| Input             | Description                                |
|-------------------|--------------------------------------------|
| `@systemClosure@` | Path to `system.build.toplevel`            |
| `@closureInfo@`   | Closure info (contains `store-paths` file) |
| `@maxSize@`       | Maximum image size in bytes                |

Copies the store paths into a pseudo-root, adds init symlinks and mount-point directories, runs `mksquashfs` with zstd
level 19, and fails if the image exceeds `@maxSize@`.

### build-rauc-bundle.sh

Builds the signed RAUC bundle. Called by `nix/rauc-bundle.nix`.

| Input                            | Description                            |
|----------------------------------|----------------------------------------|
| `@bootPartition@`                | Shared boot-slot filesystem derivation |
| `@squashfs@`                     | Squashfs image directory               |
| `@signingCert@` / `@signingKey@` | RAUC signing credentials               |
| `@version@`                      | Bundle version string                  |
| `@compatible@`                   | The board's RAUC compatible string     |
| `@board@`                        | Board name used for the bundle file    |

Copies `boot.vfat` and `rootfs.squashfs`, writes `manifest.raucm`, and signs with `rauc bundle`.

### build-image.sh

Assembles the flashable disk image. Called by `nix/image.nix`.

| Input             | Description                 |
|-------------------|-----------------------------|
| `@bootPartition@` | Shared boot-slot filesystem |
| `@squashfs@`      | Squashfs image              |
| `@uboot@`         | U-Boot package              |
| `@imageName@`     | Output filename             |

Creates a sparse image, writes `idbloader.img` at sector 64 and `u-boot.itb` at sector 16384, creates the GPT from the
shared partition layout, and writes `boot.vfat` to `boot-a` and the squashfs to `rootfs-a`. Slot B and `/data` are
created by initrd `systemd-repart` on first boot.

### boot.cmd

U-Boot boot script source, compiled to `boot.scr` by `nix/boot-script.nix`. It runs after the RAUC bootmeth has
selected a slot and decremented its tries. A `START_UMS=1` request is normally handled earlier, by U-Boot's `PREBOOT`
(`nix/uboot-start-ums.nix`); the script handles it too for boards whose U-Boot or saved environment predates that
`PREBOOT`, because RAUC bundles update `boot.scr` but never U-Boot.

1. Echo `AtomixOS build: <buildId>` on the serial console.
2. Default `devnum` to `0` when U-Boot did not set it.
3. If `START_UMS=1`, clear it, save the environment, and run `ums` so the OTG port exposes the full eMMC.
4. On Rock64 only, if the reset button (Linux `gpiochip3` line 4, U-Boot GPIO `100`) is held for 5 seconds, run `ums`.
   CM3 builds leave the recovery pin empty.
5. On Rock64, override `ramdisk_addr_r=0x08000000` so the initrd does not overlap the relocated kernel; the CM3 keeps
   the U-Boot default.
6. Read the RAUC bootmeth variables for the selected boot and root partitions, then set `rauc.slot` and
   `atomixos.lowerdev`.
7. Load `Image`, the board's DTB, and `initrd` from the boot partition. If any load fails, print the first failing file
   and `reset`, so the decremented try counter falls back instead of booting a stale initrd.
8. Set the kernel command line (NixOS `boot.kernelParams`, the board's base arguments, and `root=fstab`) and `booti`.
   If `booti` returns, `reset`.

Console: `console=ttyS2,1500000` (UART2 on both boards).

## Runtime Scripts

These scripts run on the device, started by the systemd units in [NixOS Modules](modules.md).

### first-boot.sh

First-boot provisioning and slot confirmation, run by `first-boot.service`.

1. Exit if `/data/.completed_first_boot` exists.
2. Find provisioning input: a valid existing `/data/config/config.toml`, then `/boot/config.toml` on a fresh flash,
   then `config.toml` on USB media (searched by label and partition label), and otherwise wait for the bootstrap web
   console.
3. Validate the config and import it into `/data/config/`.
4. Apply managed users, then render and sync rootful and rootless Quadlet units and restart LAN apply and provisioned
   firewall apply. A failed LAN or firewall apply, or a failed sync with required units, stops before slot
   confirmation.
5. When RAUC is enabled, seed a missing SPI boot environment and mark the current slot good.
6. Write a timestamp to `/data/.completed_first_boot`.

### os-verification.sh

Health check before committing a slot, run by `os-verification.service` on every boot after the first. Needs `rauc`,
`jq`, `systemctl`, and `ip` on `PATH`.

1. Read the RAUC slot status; refuse to continue if it cannot be parsed.
2. Check that `dnsmasq.service` and `chronyd.service` are active.
3. Check that `lan-gateway-apply.service` and `provisioned-firewall-inbound.service` did not fail.
4. Check `wan`: a missing interface or failed networkd configuration fails; a missing address only warns.
5. Check that `lan` has the provisioned gateway IP, or `172.20.30.1` without provisioned LAN settings.
6. Check that every unit in `/data/config/health-required.json` is active, rootful or rootless.
7. Repeat all checks every 5 seconds for 60 seconds (`ATOMIXOS_VERIFICATION_CHECK_INTERVAL`,
   `ATOMIXOS_VERIFICATION_SUSTAIN_DURATION`).
8. Run `rauc status mark-good` for the booted slot. This runs on every healthy boot, which restores the tries U-Boot
   used.

Any failure exits non-zero and leaves the slot uncommitted. Output goes to the journal and on to `/data/logs`.

### os-upgrade.sh

Update polling, run by `os-upgrade.service`.

| Variable                     | Purpose                                           |
|------------------------------|---------------------------------------------------|
| `ATOMIXOS_OS_UPGRADE_CONFIG` | Provisioned JSON config path                      |
| `ATOMIXOS_RAUC_BUNDLE_DIR`   | Download directory (default `/data/rauc/bundles`) |

1. Read the current version and RAUC compatible from `rauc status`, and the device ID: the `wan` MAC as 12 lowercase
   hex digits.
2. Query `<update URL>/api/v1/updates/latest` with the `X-Device-ID`, `X-Current-Version`, and `X-Compatible` headers.
3. Skip a response whose `compatible` names another board.
4. If the response names a newer `version` and a `bundle_url`, download the bundle, run `rauc install`, and reboot.
5. Exit successfully on network errors; the timer retries later.

### watchdog-boot-count.sh

Logs boot-count and rollback state for the configured RAUC backend, run by `watchdog-boot-count.service`.

1. Read the backend from `ATOMIXOS_RAUC_BOOTLOADER`.
2. For the `custom` backend, decrement `/var/lib/rauc/boot-count.<slot>`, and mark the slot bad and switch the primary
   slot when the count is exhausted.
3. For the `uboot` backend, read the post-boot `BOOT_*_LEFT` value with `fw_printenv`.
4. Print lifecycle lines to stdout for the journal.

### quadlet-sync.sh

Syncs rendered rootful and rootless Quadlet units and starts them, run by `quadlet-sync.service`.

### apply-users.py

Creates managed local users from `/data/config/users.json` with the right groups, and locks users that were removed from
the config. Runs on every boot and after a config re-apply.

### lan-gateway-apply.py

Renders the provisioned LAN settings from `/data/config/lan-settings.json`: the `lan` address drop-in, dnsmasq and
chrony LAN configuration, and host entries. Fallback values come from `defaults/lan.json`.

### provisioned-firewall-inbound.py

Applies `/data/config/firewall-inbound.json` as nftables rules tagged `ATOMIXOS_PROVISIONED_INBOUND`. Ports must be
integers from 1 to 65535. Provisioned `lan` ports replace the default-open LAN rule and always include the
platform-required LAN ports.

### ssh-wan-toggle.sh and ssh-wan-reload.sh

If `/data/config/ssh-wan-enabled` exists, add `iifname "wan" tcp dport 22 accept` with comment `SSH-WAN-dynamic`.
The reload script first deletes any existing `SSH-WAN-dynamic` rule by handle, so it can run repeatedly.

### boot-storage-debug.sh

Prints boot storage state, including `/etc/fw_env.config`, to the journal.

### atomixos_provision

Litestar provisioning service package in `scripts/atomixos_provision/`, used by first boot and by later re-apply.

| Module                                                     | Responsibility                                                     |
|------------------------------------------------------------|--------------------------------------------------------------------|
| `app.py`                                                   | Wires the Litestar application                                     |
| `settings.py`                                              | Loads environment-backed settings                                  |
| `deps.py`                                                  | Litestar dependency providers                                      |
| `domain/*/controller.py`                                   | Route handlers for the `auth`, `config`, `jobs`, and `system` APIs |
| `domain/config/coordinator.py`                             | Direct-versus-staged submission and admission policy               |
| `domain/config/service.py`                                 | Config apply and validate facade                                   |
| `schemas.py`                                               | Typed API response shapes                                          |
| `exceptions.py`                                            | Maps domain errors to API response bodies                          |
| `provision.py`, `bundle.py`, `quadlet.py`, `activation.py` | Safe apply pipeline                                                |
| `export_worker.py`                                         | UUID export requests, privileged snapshots, atomic results, expiry |
| `ui.py`                                                    | First-boot browser Boot UI and its static images                   |

`POST /api/config` is asynchronous and returns a job URL. The job reports provisioning steps, service deployment and
status events, the final result, and rollback status.

The `atomixos-provision` CLI also provides these maintenance commands:

| Command                                               | Purpose                                                                  |
|-------------------------------------------------------|--------------------------------------------------------------------------|
| `serve`                                               | Run the socket-activated Litestar service                                |
| `validate PATH`                                       | Validate a TOML file or supported bundle                                 |
| `import SOURCE CONFIG_ROOT`                           | Import a source through the maintenance path                             |
| `apply-staged CONFIG_ROOT`                            | Consume one or all queued jobs as the root worker                        |
| `finalize-staged CONFIG_ROOT`                         | Recover and finalize jobs left by an interrupted worker                  |
| `export-worker [--finalize]`                          | Drain fixed-path export requests or finalize interrupted exports as root |
| `recover CONFIG_ROOT`                                 | Recover an interrupted atomic promotion                                  |
| `sync-quadlet CONFIG_ROOT QUADLET_DIR [ROOTLESS_DIR]` | Sync rendered Quadlet units                                              |
| `check-health CONFIG_ROOT`                            | Check required provisioned services                                      |
| `complete-initial CONFIG_ROOT`                        | Finish initial promotion after first-boot checks                         |

Operators export bundles with the authenticated `GET /api/config/export` operation. The root-only `export-worker`
command is started by systemd and takes no config, request-directory, or output-path arguments; `--finalize` records
interrupted exports without starting new work. The behavior of exported bundles is described in
[Privileged bundle export](../provisioning.md#export-a-configuration).

### run-e2e-check.sh

Shared launcher for the named E2E tasks. It validates its check and description arguments, selects the host check
namespace, optionally enters Lima, runs the check or the interactive driver, filters known SQLite lock noise, and
reports a consistent result. The files under `.mise/tasks/e2e/` hold the task metadata and delegate here.

### Developer scripts

| Script                      | Purpose                                                                                   |
|-----------------------------|-------------------------------------------------------------------------------------------|
| `build.sh`                  | `mise run build --board <board>`: atomic build that retains the last two builds per board |
| `nix-with-build-config.sh`  | Adds the local `build.dev.toml` overlay to Nix commands                                   |
| `enable-docs-deployment.py` | `mise run docs:deployment:enable`: configures GitHub Pages through `gh`                   |

## mise Task Scripts

File tasks in `.mise/tasks/`, run with `mise run <task>`. Tasks defined inline in `mise.toml`, including the docs
tasks, are listed in the [Developer Tooling](../development/tooling.md#tasks).

### flash

Flashes an image to a disk (macOS and Linux).

| Argument             | Description                                                                     |
|----------------------|---------------------------------------------------------------------------------|
| `[disk]`             | Target device (for example `/dev/disk4` on macOS, `/dev/sdb` on Linux)          |
| `-i, --image <path>` | Image file (default `.gcroots/<board>/current/image`)                           |
| `--board <board>`    | `rock64` or `cm3`; required when several boards are built and no image is given |
| `-y, --yes`          | Skip the confirmation prompt                                                    |

Without `--image` or `--board` it flashes the only board that has a build, and never guesses between boards, because the
wrong image writes the wrong bootloader. On macOS it writes to `/dev/rdiskN` for unbuffered I/O, refuses to write to
the boot disk, and ejects the disk when done. On Linux it only writes unused removable or USB whole disks, and checks
the target again just before `dd`.

### flash:maskrom

Flashes an image to the CM3 eMMC over Rockchip Maskrom with `rkdeveloptool`, resolved through the flake's pinned
nixpkgs (`nix build --inputs-from . nixpkgs#rkdeveloptool`). It needs no working U-Boot, so it recovers a board whose
bootloader is broken.

| Flag                 | Default                          | Description                  |
|----------------------|----------------------------------|------------------------------|
| `-i, --image <path>` | `.gcroots/<board>/current/image` | Image file                   |
| `--board <board>`    | `cm3`                            | Board in Maskrom mode        |
| `-y, --yes`          | Off                              | Skip the confirmation prompt |

It checks the board's loader against `loaders/SHA256SUMS` and requires exactly one Rockchip USB device with the board's
SoC ID (`0x350a` for the RK3566). It downloads `loaders/rk356x_spl_loader_ddr1056_v1.10.111.bin` unless a loader is
already running, then waits until `rkdeveloptool rfi` can read the eMMC. The RK3566 still reports `Maskrom` in
`rkdeveloptool ld` once the loader runs, so the task probes the eMMC rather than the reported mode. It then writes the
image from sector 0 with `rkdeveloptool wl 0` and resets the board. With this loader, `rkdeveloptool rl` returns filler
past the first 32 MiB, so verify a flash from the booted system rather than by reading it back over USB.

### serial:capture

Captures the board's serial console (UART2, 1.5 Mbaud) with minicom, resolved through `nix build nixpkgs#minicom`.

| Flag                | Default                             | Description                                                          |
|---------------------|-------------------------------------|----------------------------------------------------------------------|
| `-p, --port <path>` | Auto-detected `/dev/cu.usbserial-*` | Serial device                                                        |
| `-l, --log <path>`  | `/tmp/rock64-serial.log`            | Log file                                                             |
| `--bg`              | Off                                 | Run in the background, replacing any running capture; prints the PID |

### serial:shell

Interactive serial console with minicom at 1.5 Mbaud. Takes the same `-p` flag; its `-l` log
defaults to `/tmp/rock64-serial-<buildid>-<timestamp>.log`.

### config:lan-range

Updates the built-in fallback LAN gateway and DHCP fields in `defaults/lan.json`, which the Nix modules, Python
services, and boot-time scripts all read. To change the LAN on a running device, set `[network.dnsmasq]` or
`[network.interfaces.lan]` in `config.toml` instead.

| Flag             | Default          | Description           |
|------------------|------------------|-----------------------|
| `--gateway-cidr` | `172.20.30.1/24` | Gateway IP and subnet |
| `--dhcp-start`   | `172.20.30.10`   | DHCP pool start       |
| `--dhcp-end`     | `172.20.30.254`  | DHCP pool end         |

### e2e:*

One task per E2E check (`e2e:rauc-slots` through `e2e:ssh-wan-toggle`) plus `e2e:debug` for interactive QEMU
debugging. Each delegates to `scripts/run-e2e-check.sh`.
