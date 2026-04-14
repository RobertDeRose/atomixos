# AtomixOS

<p align="center"> <img src="AtomixOS.png" alt="AtomixOS logo" width="300" height="300" /> </p>

AtomixOS is a secure, reproducible operating system for single-board computers, built on NixOS with atomic A/B OTA
updates, automatic rollback, and a container-based application deployment model.

<!-- BEGIN mktoc {"min_depth": 2, "max_depth": 4, "wrap_in_details": false} -->

- [Supported Boards](#supported-boards)
- [Features](#features)
- [Architecture](#architecture)
  - [eMMC partition layout (16 GB)](#emmc-partition-layout-16-gb)
  - [Network topology](#network-topology)
  - [Update and rollback flow](#update-and-rollback-flow)
  - [Squashfs rootfs](#squashfs-rootfs)
  - [Authentication (EN18031)](#authentication-en18031)
- [LAN Range Configuration](#lan-range-configuration)
- [Project structure](#project-structure)
- [Building](#building)
  - [With mise (recommended)](#with-mise-recommended)
- [Running E2E Tests](#running-e2e-tests)
  - [Run all tests](#run-all-tests)
  - [Run individual tests](#run-individual-tests)
  - [Test performance: macOS apple-virt vs Linux TCG](#test-performance-macos-apple-virt-vs-linux-tcg)
  - [Interactive debugging](#interactive-debugging)
  - [Running tests directly with Nix](#running-tests-directly-with-nix)
- [Provisioning](#provisioning)
  - [Option 1: Flashable disk image](#option-1-flashable-disk-image)
  - [Option 2: Direct eMMC provisioning](#option-2-direct-emmc-provisioning)
- [mise Task Reference](#mise-task-reference)
- [Flake outputs](#flake-outputs)
- [Versioned Image Naming](#versioned-image-naming)
- [Status](#status)
<!-- END mktoc -->

## Supported Boards

- Rock64 (RK3328, aarch64)

## Features

- **Atomic OTA updates** -- installs to the inactive slot pair while the active slot stays online
- **Automatic rollback** -- uses U-Boot boot-count fallback after repeated failed boots
- **Hardware watchdog** -- reboots hung systems via systemd watchdog integration (if supported by hardware)
- **Local health-check confirmation** -- commits new slots only after service and manifest container checks pass
- **Signed RAUC bundles** -- builds reproducible, signed `.raucb` artifacts from the flake
- **Network isolation boundary** -- keeps LAN clients off the internet; only explicit application-layer proxying is
  allowed
- **EN18031-ready authentication** -- ships without default credentials; per-device credentials are provisioned

## Architecture

### eMMC partition layout (16 GB)

```text
Offset     Size       Content          Filesystem
0          4 MB       U-Boot           raw (idbloader + u-boot.itb)
4 MB       128 MB     boot slot A      vfat (kernel + DTB)
132 MB     128 MB     boot slot B      vfat (kernel + DTB)
260 MB     1 GB       rootfs slot A    squashfs (zstd, 1 MB block)
1284 MB    1 GB       rootfs slot B    squashfs (zstd, 1 MB block)
2308 MB    ~13.3 GB   /persist         f2fs (containers, state, logs)
```

### Network topology

```mermaid
flowchart LR
    WAN["WAN (internet)"] --> ETH0["eth0\nDHCP client\nHTTPS (443)\nOpenVPN (1194)"]
    LAN["LAN (isolated)"] --> ETH1["eth1\nLAN gateway IP (/24)\nDHCP server (dnsmasq)\nNTP server (chrony)"]

    subgraph GATEWAY["Gateway device"]
        ETH0
        CORE["ip_forward = OFF\nno NAT, no routing"]
        ETH1
    end
```

LAN devices get DHCP and NTP but have zero internet access. Application-layer proxying (Traefik, running as a container)
selectively bridges WAN and LAN with authentication.

### Update and rollback flow

```text
1. os-upgrade.service polls update server for new .raucb bundle
2. rauc install writes boot + rootfs to the INACTIVE slot pair
3. RAUC sets U-Boot env: BOOT_ORDER=B A, BOOT_B_LEFT=3
4. Device reboots into new slot
5. U-Boot decrements BOOT_B_LEFT on each boot attempt
6. os-verification.service runs health checks:
   - eth0 has WAN address, eth1 has the configured LAN gateway IP
   - dnsmasq, chronyd running
   - containers from /persist/config/health-manifest.yaml are healthy
   - sustained 60s stability check
7a. All pass  → rauc status mark-good (slot committed)
7b. Any fail  → exit non-zero, boot-count continues to decrement
8. After 3 failed boots → U-Boot falls back to previous good slot
```

The hardware watchdog ensures hung systems reboot within 30s, feeding into the same boot-count rollback path.

### Squashfs rootfs

The read-only root filesystem contains the full NixOS system closure:

- Stripped Linux 6.19 kernel (RK3328 drivers built-in, WiFi/BT as modules)
- systemd, podman, OpenVPN, openssh, chrony, dnsmasq, nftables, RAUC
- python3Minimal for Cockpit's SSH-based Python bridge
- Cockpit itself runs as a pod (`quay.io/cockpit/ws`), not in the rootfs

### Authentication (EN18031)

The image ships with no embedded credentials. During provisioning:

- `/persist/config/admin-password-hash` -- unique sha-512 password hash per device
- `/persist/config/ssh-authorized-keys/admin` -- operator's SSH public key
- `/persist/config/traefik/` -- Traefik static/dynamic config and self-signed TLS certificate
- `/persist/config/health-manifest.yaml` -- container health entries for os-verification

Remote SSH is key-only. Localhost SSH allows password auth so the Cockpit pod can connect to the host. OIDC (Microsoft
Entra via Traefik forward-auth) is the primary web auth when internet is available; the provisioned password is the
LAN/offline fallback.

## LAN Range Configuration

Use the `mise` helper task to update LAN settings across all required files in one command.

```sh
mise run config:lan-range --gateway-cidr 10.50.0.1/24 --dhcp-start 10.50.0.10 --dhcp-end 10.50.0.254
```

This updates:

- `modules/networking.nix` (`eth1` static address)
- `modules/lan-gateway.nix` (DHCP pool, DHCP options, chrony allow subnet)
- `scripts/os-verification.sh` (expected `eth1` IP)
- `.mise/tasks/provision/emmc` (Traefik cert SAN IP and OIDC LAN allowlist CIDR)

After changing the range, rebuild and re-provision:

```sh
mise run check
mise run build:image
mise run provision:image -o atomixos-<series>.img
```

## Project structure

```text
flake.nix                          Main flake (pinned nixpkgs release, aarch64-linux)
flake.lock                         Pinned nixpkgs
mise.toml                          Tool versions, build tasks, hooks

modules/
  base.nix                         Shared NixOS config (systemd, podman, ssh, auth, closure opts)
  hardware-rock64.nix              RK3328 kernel, DTB, eMMC/watchdog drivers
  hardware-qemu.nix                QEMU aarch64-virt target for testing
  networking.nix                   NIC naming (.link files), eth0/eth1 config
  firewall.nix                     nftables rules (WAN/LAN/VPN/FORWARD)
  lan-gateway.nix                  dnsmasq DHCP, chrony NTP, IP forwarding off
  rauc.nix                         RAUC system.conf, slot definitions
  cockpit.nix                      Cockpit pod (quay.io/cockpit/ws) systemd service
  traefik.nix                      Traefik reverse proxy pod systemd service
  watchdog.nix                     systemd watchdog config
  os-verification.nix              Post-update health check service
  os-upgrade.nix                   Update polling + hawkBit toggle
  first-boot.nix                   First-boot RAUC slot commit + sentinel
  openvpn.nix                      OpenVPN recovery tunnel

nix/
  squashfs.nix                     Squashfs image derivation (closureInfo + mksquashfs)
  rauc-bundle.nix                  Multi-slot RAUC bundle derivation
  boot-script.nix                  U-Boot boot.scr compilation
  image.nix                        Flashable eMMC disk image derivation
  tests/                           NixOS VM integration tests (nixos-lib.runTest)
    rauc-slots.nix                 RAUC slot detection + custom backend
    rauc-update.nix                Bundle install + slot switch
    rauc-rollback.nix              Install → mark-bad → rollback
    rauc-confirm.nix               os-verification health check → mark-good
    rauc-power-loss.nix            Crash mid-install, verify recovery
    rauc-watchdog.nix              Watchdog + boot-count rollback
    firewall.nix                   2-node WAN/LAN port allow/deny
    network-isolation.nix          2-node DHCP/NTP/WAN isolation
    ssh-wan-toggle.nix             SSH-on-WAN flag enable/disable

scripts/
  build-squashfs.sh                Squashfs build template (Nix derivation)
  build-rauc-bundle.sh             RAUC bundle build template (Nix derivation)
  build-image.sh                   Disk image assembly template (Nix derivation)
  os-verification.sh               Runtime health check script
  os-upgrade.sh                    Runtime update polling script
  ssh-wan-toggle.sh                SSH-on-WAN flag check
  ssh-wan-reload.sh                SSH-on-WAN runtime reload
  first-boot.sh                    First-boot RAUC mark-good + sentinel
  boot.cmd                         U-Boot A/B boot script source
  fw_env.config                    Redundant U-Boot env storage config

.mise/tasks/config/
  lan-range                        Update LAN gateway/DHCP range across all configs

.mise/tasks/provision/
  image                            Generate flashable .img file
  emmc                             Flash directly to eMMC block device (Linux only)

.mise/tasks/e2e/
  rauc-slots                       Run RAUC slot logic test
  rauc-update                      Run RAUC update install test
  rauc-rollback                    Run RAUC rollback test
  rauc-confirm                     Run os-verification confirmation test
  rauc-power-loss                  Run power-loss simulation test
  rauc-watchdog                    Run watchdog rollback test
  firewall                         Run firewall test
  network-isolation                Run network isolation test
  ssh-wan-toggle                   Run SSH toggle test
  debug                            Interactive QEMU debugging

certs/
  dev.ca.cert.pem                  Development RAUC CA certificate (public)
  dev.signing.cert.pem             Development RAUC signing certificate (public)
  dev.*.key.pem                    Private keys (gitignored)

_typos.toml                        Typos checker config (iif nftables keyword allowlist)
```

## Building

Builds require an aarch64-linux system (native or cross). All outputs target `aarch64-linux`.

### With mise (recommended)

```sh
# Install tools and hooks
mise install

# Check the flake evaluates cleanly
mise run check

# Build individual artifacts
mise run build:squashfs        # result-squashfs/
mise run build:rauc-bundle     # result-rauc-bundle/
mise run build:boot-script     # result-boot-script/
mise run build:image           # result-image/

# Build everything
mise run build
```

## Running E2E Tests

Nine NixOS VM integration tests validate the full RAUC update lifecycle, network security, and rollback behavior. Tests
run on both Linux (TCG software emulation) and macOS (Apple Virtualization Framework). The mise task wrappers
auto-detect the platform and select the correct flake output (`aarch64-linux` or `aarch64-darwin`).

### Run all tests

```sh
mise run e2e
```

### Run individual tests

```sh
mise run e2e:rauc-slots          # RAUC sees all 4 A/B slots after boot
mise run e2e:rauc-update         # Bundle install writes to inactive slot pair, slot switches A→B
mise run e2e:rauc-rollback       # Install to B, mark bad, verify rollback to A
mise run e2e:rauc-confirm        # os-verification health checks pass, slot marked good (~3 min)
mise run e2e:rauc-power-loss     # Crash VM mid-install, verify slot A intact after reboot
mise run e2e:rauc-watchdog       # Freeze systemd to trigger watchdog, verify boot-count rollback
mise run e2e:firewall            # 2-node test: WAN allows HTTPS/VPN, LAN allows SSH/DHCP/NTP
mise run e2e:network-isolation   # 2-node test: LAN gets DHCP/NTP, cannot reach WAN
mise run e2e:ssh-wan-toggle      # Flag file enables/disables SSH on WAN via nftables reload
```

### Test performance: macOS apple-virt vs Linux TCG

On macOS, the nix-darwin `linux-builder` builds the NixOS test closures and the test driver runs QEMU natively on the
Mac host using Apple Virtualization Framework (`apple-virt`) for hardware acceleration. On Linux (e.g. Lima VM), tests
run under TCG software emulation without KVM. Measured wall-clock times:

| Test | macOS (apple-virt) | Linux (TCG, Lima 4 GB) | Speedup |
|---|---|---|---|
| `rauc-slots` | 34s | 132s | 3.9x |
| `rauc-update` | 25s | 137s | 5.5x |
| `rauc-rollback` | 22s | 120s | 5.5x |
| `rauc-confirm` | 95s | 171s | 1.8x |
| `rauc-power-loss` | 46s | 184s | 4.0x |
| `rauc-watchdog` | 57s | 315s | 5.5x |
| `firewall` | 65s | 205s | 3.2x |
| `network-isolation` | 68s | -- | -- |
| `ssh-wan-toggle` | 35s | -- | -- |
| **Total** | **~7.5 min** | **~21 min** (7 tests) | **~3.7x** |

The `rauc-confirm` test has the smallest speedup because most of its runtime is a fixed 60s sustained health check
timer. For CPU-bound tests (boot, install, rollback), apple-virt delivers a consistent 4-5x improvement over TCG.

### Interactive debugging

Launch an interactive QEMU VM with a Python REPL for hands-on debugging:

```sh
# Debug the default test (rauc-slots)
mise run e2e:debug

# Debug a specific test
mise run e2e:debug -t update
mise run e2e:debug -t confirm
mise run e2e:debug -t watchdog

# Keep VM state between runs
mise run e2e:debug -t slots --keep
```

Available test short names: `slots`, `update`, `rollback`, `confirm`, `power-loss`, `watchdog`, `firewall`, `net-iso`,
`ssh-toggle`.

Inside the REPL:

```python
gateway.start()                          # boot the VM
gateway.wait_for_unit("multi-user.target")
gateway.succeed("rauc status")           # run a command
gateway.shell_interact()                 # drop into a root shell
gateway.screenshot("name")              # save a screenshot
# Ctrl+D to exit
```

### Running tests directly with Nix

```sh
# Linux
nix build .#checks.aarch64-linux.rauc-slots --no-link -L

# macOS (requires nix-darwin with linux-builder enabled)
nix build .#checks.aarch64-darwin.rauc-slots --no-link -L
```

## Provisioning

### Option 1: Flashable disk image

Build an `.img` file that can be written to eMMC (or SD card):

```sh
mise run provision:image -o atomixos-<series>.img

# Flash to a disk device (eMMC module via USB/SD adapter)
mise run flash /dev/disk4          # macOS — auto-detects image, uses raw device for speed
mise run flash -i custom.img /dev/disk4   # specify image explicitly
mise run flash -y /dev/mmcblk0     # Linux — skip confirmation prompt
```

The image includes U-Boot, boot slot A (kernel + DTB), and rootfs slot A (squashfs). On first boot, `systemd-repart`
automatically creates and formats the `/persist` partition (f2fs) using all remaining eMMC space.

### Option 2: Direct eMMC provisioning

For factory provisioning with the eMMC attached as a block device (requires Linux + root):

```sh
mise run provision:emmc /dev/mmcblk1 /path/to/uboot /path/to/kernel /path/to/dtb /path/to/squashfs
# Optional: --ssh-key ~/.ssh/id_ed25519.pub
```

This partitions the eMMC, writes U-Boot, deploys the first image to slot A, and pre-creates the persist partition with:

- Admin password (prompted interactively, sha-512 hashed, EN18031 compliant)
- SSH public key (if `--ssh-key` provided)
- Traefik reverse proxy configuration and self-signed TLS certificate
- Health manifest (cockpit-ws, traefik) for os-verification

## mise Task Reference

All tasks are run with `mise run <task>`. Run `mise tasks` to list them.

| Task | Description |
|---|---|
| `check` | Verify flake evaluates cleanly (`nix flake check`) |
| **Build** | |
| `build` | Build all image artifacts (depends on all `build:*` tasks) |
| `build:squashfs` | Build squashfs rootfs → `result-squashfs/` |
| `build:rauc-bundle` | Build signed RAUC bundle → `result-rauc-bundle/` |
| `build:boot-script` | Build U-Boot boot script → `result-boot-script/` |
| `build:image` | Build flashable disk image → `result-image/` |
| **E2E Tests** | |
| `e2e` | Run all 9 integration tests sequentially |
| `e2e:rauc-slots` | RAUC slot detection after boot |
| `e2e:rauc-update` | Bundle install + slot switch A→B |
| `e2e:rauc-rollback` | Install → mark bad → rollback to previous slot |
| `e2e:rauc-confirm` | os-verification health check → mark-good (~3 min) |
| `e2e:rauc-power-loss` | Crash mid-install, verify recovery |
| `e2e:rauc-watchdog` | Watchdog + boot-count rollback |
| `e2e:firewall` | WAN/LAN/VPN port allow/deny (2-node VLAN) |
| `e2e:network-isolation` | DHCP/NTP/WAN isolation (2-node VLAN) |
| `e2e:ssh-wan-toggle` | SSH-on-WAN flag enable/disable |
| `e2e:debug` | Interactive QEMU VM for debugging (`-t <test>`, `--keep`) |
| **Provisioning** | |
| `flash` | Flash image to disk device with dd + progress (macOS/Linux) |
| `provision:image` | Generate flashable `.img` file (builds all artifacts first) |
| `provision:emmc` | Flash directly to eMMC block device (Linux + root only) |
| **Configuration** | |
| `config:lan-range` | Update LAN gateway/DHCP range across all config files |

## Flake outputs

| Output                               | Description                                            |
|--------------------------------------|--------------------------------------------------------|
| `nixosConfigurations.rock64`         | Real hardware NixOS system                             |
| `nixosConfigurations.rock64-qemu`    | QEMU aarch64-virt testing target                       |
| `packages.aarch64-linux.squashfs`    | Compressed squashfs root filesystem                    |
| `packages.aarch64-linux.rauc-bundle` | Signed multi-slot `.raucb` bundle                      |
| `packages.aarch64-linux.boot-script` | Compiled U-Boot `boot.scr`                             |
| `packages.aarch64-linux.image`       | Flashable eMMC disk image (U-Boot + boot-a + rootfs-a) |
| `apps.aarch64-linux.rock64-qemu-vm`  | QEMU VM runner                                         |
| `checks.aarch64-linux.*`             | E2E integration tests (9 tests, see `nix/tests/`)     |
| `checks.aarch64-darwin.*`            | Same tests, run natively on macOS via apple-virt       |

## Versioned Image Naming

The flashable image filename includes the pinned NixOS release series from your flake lock.

- Current pinned input: `nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11"`
- Output image name pattern: `atomixos-<series>.img` (for example, `atomixos-25.11.img`)
- Source of truth: `flake.nix` nixpkgs input ref

When you move to a new series (for example `nixos-26.05`), update `flake.nix`/`flake.lock` and rebuild. The image name
updates automatically everywhere it is produced.

## Status

Implementation is in progress. **99 of 116 tasks complete (85%)**. All core implementation, E2E integration tests, and
software-verifiable tasks are done. Hardware bring-up is underway — NixOS boots to login prompt on Rock64 via serial
console. The remaining 17 tasks require physical hardware testing or network access for container image pulls:

- **Hardware verification (15 tasks)** — require a physical Rock64 board (NIC naming, DHCP/NTP on real
  network, RAUC on-device, provisioning boot, Cockpit SSH bridge, credential verification)
- **Integration tests needing containers (2 tasks)** — Cockpit pod HTTPS verification, confirmation with real
  containers and health manifest

See `openspec/changes/rock64-ab-image/tasks.md` for the full task breakdown.
