# Flake Outputs

The Nix flake (`flake.nix`) provides the following outputs:

## NixOS Configurations

| Output                            | Description                                                            |
|-----------------------------------|------------------------------------------------------------------------|
| `nixosConfigurations.rock64`      | Real hardware NixOS system (RK3328, eMMC, all service modules)         |
| `nixosConfigurations.rock64-qemu` | QEMU aarch64-virt testing target (virtio devices, custom RAUC backend) |

Both configurations share `modules/base.nix` and all service modules. They differ only in hardware-specific
configuration (kernel drivers, device paths, boot method).

## Packages

All packages target `aarch64-linux`. An `aarch64-darwin` alias is provided so that `nix build .#image` works directly
from macOS when a linux-builder is available (the alias points to the same `aarch64-linux` package set):

| Output                                   | Description                                                       |
|------------------------------------------|-------------------------------------------------------------------|
| `packages.aarch64-linux.squashfs`        | Compressed squashfs root filesystem (~300-400 MB)                 |
| `packages.aarch64-linux.rauc-bundle`     | Signed multi-slot `.raucb` bundle for OTA updates                 |
| `packages.aarch64-linux.boot-script`     | Compiled U-Boot `boot.scr`                                        |
| `packages.aarch64-linux.uboot`           | Custom Rock64 U-Boot package providing the bootloader artifacts   |
| `packages.aarch64-linux.uboot-env-tools` | `fw_printenv` / `fw_setenv` binaries used with the Rock64 SPI env |
| `packages.aarch64-linux.image`           | Flashable eMMC disk image (U-Boot + boot-a + rootfs-a, ~1.2 GB)   |

## Apps

| Output                              | Description                                 |
|-------------------------------------|---------------------------------------------|
| `apps.aarch64-linux.rock64-qemu-vm` | QEMU VM runner (`nix run .#rock64-qemu-vm`) |

## Checks (Tests)

Tests are available for both Linux and macOS:

| Output                    | Description                                                             |
|---------------------------|-------------------------------------------------------------------------|
| `checks.aarch64-linux.*`  | E2E tests running under TCG (software emulation)                        |
| `checks.aarch64-darwin.*` | Same tests running natively on macOS via Apple Virtualization Framework |

Available test names: `rauc-slots`, `rauc-update`, `rauc-rollback`, `rauc-confirm`, `rauc-power-loss`, `rauc-watchdog`,
`firewall`, `initrd-fresh-flash-marker`, `first-boot-provision`, `first-boot-source-discovery`, `forensics-podman-log-path`,
`forensics-rsyslog-path`, `forensics-rsyslog-buffering`, `forensics-shutdown-flush`, `network-isolation`, `ssh-wan-toggle`.

## Overlay

The flake includes an `embeddedOverlay` that strips unnecessary dependencies to reduce closure size:

- `crun` is built without CRIU support (removes `criu` + `python3`, saving ~102 MB)

This overlay is applied to both NixOS configurations via the `overlayModule`.
