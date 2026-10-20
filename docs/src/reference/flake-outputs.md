# Flake Outputs

Every output `flake.nix` provides. Direct Git-backed Nix commands evaluate the committed `build.toml`; supported `mise`
tasks add an ignored local overlay through `scripts/nix-with-build-config.sh` (see
[Build Configuration](build-configuration.md#supported-command-contract)).

## Library

| Output                                         | Description                                               |
|------------------------------------------------|-----------------------------------------------------------|
| `lib.effectiveBuildConfiguration`              | Validated values, canonical policy, hash, and provenance  |
| `lib.effectiveBuildConfiguration.policySHA256` | Preflight-friendly hash of the canonical effective policy |

## NixOS Configurations

| Output                               | Description                                                                  |
|--------------------------------------|------------------------------------------------------------------------------|
| `nixosConfigurations.rock64`         | Rock64 hardware system (RK3328, eMMC, all service modules)                   |
| `nixosConfigurations.cm3`            | Radxa CM3 on the CM3 IO Board (RK3566, eMMC, all service modules)            |
| `nixosConfigurations.rock64-qemu`    | QEMU aarch64-virt testing target (virtio devices, custom RAUC backend)       |
| `nixosConfigurations.bundle-test-vm` | Interactive QEMU target for testing provisioning bundles and forwarded ports |

Each configuration combines the `overlayModule`, `modules/base.nix`, `modules/build-configuration.nix`, and one
hardware module: `modules/hardware-rock64.nix` for `rock64`, `modules/hardware-cm3.nix` for `cm3`, and
`modules/hardware-qemu.nix` for both VM targets.
`bundle-test-vm` also adds the NixOS `qemu-vm.nix` module, VM resources, serial autologin, and forwarded service ports.

## Packages

All packages target `aarch64-linux`. `packages.aarch64-darwin` is an alias of the same `aarch64-linux` set, so
`nix build .#<board>` works from macOS when a Linux builder is configured.

There is one package per board: `packages.aarch64-linux.rock64` and `packages.aarch64-linux.cm3`. Building it (for
example `nix build .#cm3`) links the shipped artifacts (`image`, `rauc-bundle`, `uboot`, `uboot-env-tools`,
`boot-script`) into their own subdirectories of `result/`. Every artifact, including the intermediate `squashfs` and
`boot-partition` that are already inside the image and bundle, is also an attribute of the board package, so it can be
built alone, for example `nix build .#cm3.image`.

| Attribute (`.#<board>.…`) | Description                                                      |
|---------------------------|------------------------------------------------------------------|
| `image`                   | Flashable eMMC disk image (U-Boot + boot-a + rootfs-a, 1170 MiB) |
| `rauc-bundle`             | Signed multi-slot `.raucb` bundle for OTA updates                |
| `squashfs`                | Compressed squashfs root filesystem, at most 1 GiB               |
| `boot-script`             | Compiled U-Boot `boot.scr`                                       |
| `boot-partition`          | Boot-slot vfat shared by the image and RAUC bundle builds        |
| `uboot`                   | Board U-Boot with the RAUC bootmeth, persistent environment, UMS |
| `uboot-env-tools`         | `fw_printenv` / `fw_setenv` built from the same U-Boot source    |

Rock64 keeps its U-Boot environment in SPI NOR; the CM3 keeps two redundant copies in the eMMC boot gap. See
[Nix Derivations](../code-reference/derivations.md).

## Apps

| Output                              | Description                                 |
|-------------------------------------|---------------------------------------------|
| `apps.aarch64-linux.rock64-qemu-vm` | QEMU VM runner (`nix run .#rock64-qemu-vm`) |
| `apps.aarch64-linux.bundle-test-vm` | Interactive bundle-test VM runner           |

## Checks

| Output                    | Description                                                                        |
|---------------------------|------------------------------------------------------------------------------------|
| `checks.aarch64-linux.*`  | VM tests under TCG (software emulation, no KVM needed) plus evaluation-only checks |
| `checks.aarch64-darwin.*` | The same tests, with the test driver running natively on macOS                     |

VM tests:

- RAUC: `rauc-slots`, `rauc-update`, `rauc-rollback`, `rauc-confirm`, `rauc-power-loss`, `rauc-watchdog`
- Provisioning: `first-boot-provision`, `first-boot-source-discovery`, `initrd-fresh-flash-marker`,
  `provisioning-export`, `rootless-storage`
- Nixstasis: `nixstasis-client`, `nixstasis-module`, `fleet-bootstrap`
- Networking: `firewall`, `network-isolation`, `ssh-wan-toggle`, `chrony-wan-recovery`
- Logging: `forensics-podman-log-path`, `forensics-rsyslog-path`, `forensics-rsyslog-buffering`,
  `forensics-shutdown-flush`
- Platform: `kernel-security`, `interface-naming`, `watchdog-module`, `watchdog-missing-device`

Evaluation and command checks: `boot-partition-size`, `boot-script`, `build-config-workflow`, `build-configuration`,
`cm3-board`, `device-tree-overlay`, `e2e-launcher`, `lan-defaults`, `os-upgrade-query`, `partition-layout`,
`uboot-scripts`. `boot-script` and `interface-naming` exist only for `aarch64-linux`. `uboot-scripts` runs the compiled
`boot.scr` and the `START_UMS` `PREBOOT` in a U-Boot sandbox, because U-Boot only parses those scripts at boot time.

`mise run check` runs hk checks and the docs build, not Nix evaluation or builds. `.github/workflows/nix.yml` evaluates
each runner's platform with `./scripts/nix-with-build-config.sh flake check --no-build --system <system>`, and its
`uboot-scripts` job builds `checks.aarch64-linux.uboot-scripts`; it does not run VM tests. Run
`./scripts/nix-with-build-config.sh flake check` locally to build the checks compatible with the current host, or use a
target-specific `nix build .#checks.<system>.<name>` when execution evidence is required. On macOS, VM checks use the
Darwin test driver while the Linux guest is built by the configured Linux builder.

## Overlay

`embeddedOverlay` strips unnecessary dependencies to reduce the closure size. It builds `crun` without CRIU support,
which removes `criu` and `python3` (about 102 MB). `overlayModule` applies it to all four NixOS configurations.
