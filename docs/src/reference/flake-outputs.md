# Flake Outputs

The Nix flake (`flake.nix`) provides the following outputs. Direct Git-backed Nix commands evaluate committed
`build.toml`; supported `mise` tasks supply ignored local overrides through their wrapper.

## Library

| Output                                         | Description                                              |
|------------------------------------------------|----------------------------------------------------------|
| `lib.effectiveBuildConfiguration`              | Validated values, canonical policy, hash, and provenance |
| `lib.effectiveBuildConfiguration.policySHA256` | Preflight-friendly hash of canonical effective policy    |

## NixOS Configurations

| Output                               | Description                                                                  |
|--------------------------------------|------------------------------------------------------------------------------|
| `nixosConfigurations.rock64`         | ROCK64 hardware NixOS system (RK3328, eMMC, all service modules)             |
| `nixosConfigurations.cm3`            | Radxa CM3 + CM3 IO Board hardware NixOS system (RK3566)                      |
| `nixosConfigurations.rock64-qemu`    | QEMU aarch64-virt testing target (virtio devices, custom RAUC backend)       |
| `nixosConfigurations.bundle-test-vm` | Interactive QEMU target for testing provisioning bundles and forwarded ports |

All four configurations receive the effective build policy and share `modules/base.nix`. ROCK64 and CM3 have distinct
hardware modules; both VM targets use `modules/hardware-qemu.nix`; and `bundle-test-vm` adds interactive VM resources,
login behavior, and forwarded service ports.

## Packages

All packages target `aarch64-linux`. An `aarch64-darwin` alias is provided so `nix build .#image-<board>` works directly
from macOS when a linux-builder is available (the alias points to the same `aarch64-linux` package set):

| Output                                       | Description                                                       |
|----------------------------------------------|-------------------------------------------------------------------|
| `packages.aarch64-linux.squashfs`            | Compressed squashfs root filesystem (~300-400 MB)                 |
| `packages.aarch64-linux.rauc-bundle`         | Signed multi-slot `.raucb` bundle for OTA updates                 |
| `packages.aarch64-linux.boot-script`         | Compiled U-Boot `boot.scr`                                        |
| `packages.aarch64-linux.uboot`               | Custom Rock64 U-Boot package providing the bootloader artifacts   |
| `packages.aarch64-linux.uboot-env-tools`     | `fw_printenv` / `fw_setenv` binaries used with the Rock64 SPI env |
| `packages.aarch64-linux.image-rock64`        | Flashable ROCK64 eMMC image (U-Boot + boot-a + rootfs-a)          |
| `packages.aarch64-linux.image-cm3`           | Flashable CM3 IO Board eMMC image                                 |
| `packages.aarch64-linux.image`               | Legacy alias for `image-rock64`                                   |
| `packages.aarch64-linux.rauc-bundle-cm3`     | CM3-specific signed OTA bundle                                    |
| `packages.aarch64-linux.rauc-bundle-rock64`  | Alias for ROCK64 signed OTA bundle                                |
| `packages.aarch64-linux.boot-partition`      | Shared boot-slot vfat used by image and RAUC bundle builds        |
| `packages.aarch64-linux.squashfs-cm3`        | CM3 squashfs root filesystem                                      |
| `packages.aarch64-linux.boot-script-cm3`     | CM3 U-Boot `boot.scr`                                             |
| `packages.aarch64-linux.boot-partition-cm3`  | CM3 boot-slot vfat used by `image-cm3` and `rauc-bundle-cm3`      |
| `packages.aarch64-linux.uboot-cm3`           | Radxa CM3 IO U-Boot (redundant eMMC env, RAUC bootmeth, UMS)      |
| `packages.aarch64-linux.uboot-env-tools-cm3` | `fw_printenv` / `fw_setenv` binaries used with the CM3 eMMC env   |

## Apps

| Output                              | Description                                 |
|-------------------------------------|---------------------------------------------|
| `apps.aarch64-linux.rock64-qemu-vm` | QEMU VM runner (`nix run .#rock64-qemu-vm`) |
| `apps.aarch64-linux.bundle-test-vm` | Interactive bundle-test VM runner           |

## Checks (Tests)

Tests are available for both Linux and macOS:

| Output                    | Description                                                             |
|---------------------------|-------------------------------------------------------------------------|
| `checks.aarch64-linux.*`  | E2E tests running under TCG (software emulation)                        |
| `checks.aarch64-darwin.*` | Same tests running natively on macOS via Apple Virtualization Framework |

Available test names: `build-configuration`, `build-config-workflow`, `rauc-slots`, `rauc-update`, `rauc-rollback`,
`rauc-confirm`, `rauc-power-loss`, `rauc-watchdog`, `firewall`, `initrd-fresh-flash-marker`, `first-boot-provision`,
`first-boot-source-discovery`, `kernel-security`, `rootless-storage`, `watchdog-module`, `watchdog-missing-device`, `forensics-podman-log-path`,
`forensics-rsyslog-path`, `forensics-rsyslog-buffering`, `forensics-shutdown-flush`, `network-isolation`, `ssh-wan-toggle`.

`mise run check` runs hk formatting, linting, and documentation checks, not Nix evaluation or builds.
The separate `.github/workflows/nix.yml` workflow evaluates each runner's platform with
`./scripts/nix-with-build-config.sh flake check --no-build --system <system>`; it does not execute VM tests.
Run `./scripts/nix-with-build-config.sh flake check` locally to build checks compatible with the current host,
or use a target-specific `nix build` command when execution evidence is required. On macOS, VM checks use the
Darwin test driver while the Linux guest remains built by the configured Linux builder.

## Overlay

The flake includes an `embeddedOverlay` that strips unnecessary dependencies to reduce closure size:

- `crun` is built without CRIU support (removes `criu` + `python3`, saving ~102 MB)

This overlay is applied to all four NixOS configurations via the `overlayModule`.
