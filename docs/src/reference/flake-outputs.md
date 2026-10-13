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

All packages target `aarch64-linux`. An `aarch64-darwin` alias is provided so `nix build .#<board>` works directly from
macOS when a linux-builder is available (the alias points to the same `aarch64-linux` package set).

There is one package per board, `packages.aarch64-linux.<board>` with `<board>` = `rock64` or `cm3`. Building it (for
example `nix build .#cm3`) links the shipped artifacts (`image`, `rauc-bundle`, `uboot`, `uboot-env-tools`, `boot-script`)
into their own subdirectories of `result/`. Every artifact, including the intermediate `squashfs` and `boot-partition`
that are already inside the image and bundle, is also an attribute of the board package, so it can be built alone, for
example `nix build .#cm3.image`:

| Attribute (`.#<board>.…`) | Description                                                 |
|---------------------------|-------------------------------------------------------------|
| `image`                   | Flashable eMMC image (U-Boot + boot-a + rootfs-a)           |
| `rauc-bundle`             | Signed multi-slot `.raucb` bundle for OTA updates           |
| `squashfs`                | Compressed squashfs root filesystem (~300-400 MB)           |
| `boot-script`             | Compiled U-Boot `boot.scr`                                  |
| `boot-partition`          | Boot-slot vfat shared by the image and RAUC bundle builds   |
| `uboot`                   | Board U-Boot (RAUC bootmeth, persistent env, UMS recovery)  |
| `uboot-env-tools`         | `fw_printenv` / `fw_setenv` matching the board's env layout |

ROCK64 keeps its environment in SPI NOR; CM3 keeps two redundant copies in the eMMC boot gap.

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
