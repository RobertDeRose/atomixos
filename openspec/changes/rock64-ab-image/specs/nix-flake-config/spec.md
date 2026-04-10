# Nix Flake Config Spec

## ADDED Requirements

### Requirement: NixOS flake defines Rock64 system configuration

The flake SHALL define a `nixosConfigurations.rock64` output that targets the Rock64 board (aarch64-linux, Rockchip
RK3328). The configuration SHALL include systemd, podman, Cockpit (with podman module), openssh, OpenVPN, chrony,
dnsmasq, nftables, and all dependencies required for the A/B update system and LAN gateway role.

#### Scenario: Flake evaluates successfully

- **WHEN** `nix flake check` is run against the repository
- **THEN** the flake evaluates without errors and `nixosConfigurations.rock64` is present

#### Scenario: System configuration targets aarch64-linux

- **WHEN** the Rock64 NixOS configuration is built
- **THEN** all outputs are compiled for the `aarch64-linux` platform

### Requirement: Flake produces squashfs root filesystem image

The flake SHALL produce a squashfs image as a package output (`packages.aarch64-linux.squashfs`). The image SHALL
contain the complete root filesystem including kernel modules, Cockpit, OpenVPN, chrony, dnsmasq, and all system
services. The image SHALL be read-only.

#### Scenario: Squashfs image builds successfully

- **WHEN** `nix build .#squashfs` is run
- **THEN** a squashfs image file is produced in the `result/` symlink

#### Scenario: Squashfs image fits within slot size

- **WHEN** the squashfs image is built
- **THEN** the resulting image SHALL be no larger than 200 MB

### Requirement: Flake produces signed multi-slot RAUC bundle

The flake SHALL produce a signed RAUC bundle (`.raucb`) as a package output (`packages.aarch64-linux.rauc-bundle`). The
bundle SHALL contain both the boot partition image (kernel + DTB) and the squashfs rootfs image, and SHALL be signed
with the project CA key.

#### Scenario: RAUC bundle builds successfully

- **WHEN** `nix build .#rauc-bundle` is run
- **THEN** a `.raucb` file is produced that passes `rauc info` validation and contains both boot and rootfs images

#### Scenario: RAUC bundle is signed

- **WHEN** the RAUC bundle is inspected with `rauc info`
- **THEN** the bundle shows a valid signature chain rooted at the project CA

### Requirement: Stripped kernel with modular USB peripheral support

The NixOS configuration SHALL use a custom kernel configuration stripped to only RK3328-required drivers built-in
(eMMC/dw_mmc, ethernet/stmmac, USB host/dwc2/xhci, watchdog/dw_wdt, squashfs, f2fs). USB WiFi drivers (rtlwifi,
ath9k_htc, mt76), USB Bluetooth drivers (btusb), and USB serial drivers (ftdi, cp210x) SHALL be built as modules (`=m`)
and included in the squashfs.

#### Scenario: Kernel boots on Rock64 hardware

- **WHEN** the built kernel and DTB are loaded by U-Boot on a Rock64 board
- **THEN** the kernel boots successfully and detects eMMC, watchdog, ethernet, and USB hardware

#### Scenario: WiFi module loads on demand

- **WHEN** a supported USB WiFi dongle is plugged into the Rock64
- **THEN** the appropriate kernel module is loaded and a wlan interface appears

#### Scenario: Bluetooth module loads on demand

- **WHEN** a supported USB Bluetooth dongle is plugged into the Rock64
- **THEN** the btusb kernel module is loaded and the Bluetooth controller is available

### Requirement: Cockpit is included in the rootfs as a system service

The NixOS configuration SHALL include Cockpit with the podman module as a system service managed by systemd. Cockpit
SHALL start automatically on boot and provide web-based system management and container management.

#### Scenario: Cockpit is accessible after boot

- **WHEN** the Rock64 boots the built image
- **THEN** Cockpit is running as a systemd service and accessible via HTTPS through Traefik

#### Scenario: Cockpit podman module shows containers

- **WHEN** a user accesses Cockpit's container management interface
- **THEN** Cockpit displays podman containers running on the device with the ability to start, stop, and inspect them

### Requirement: OpenVPN is included in the rootfs as a system service

The NixOS configuration SHALL include OpenVPN as a system service for recovery management access via VPN tunnel.

#### Scenario: OpenVPN service is available after boot

- **WHEN** the Rock64 boots and OpenVPN is configured
- **THEN** the OpenVPN service is running and creates a tun0 interface when a VPN connection is established

### Requirement: System includes core services

The NixOS configuration SHALL enable systemd, podman (for container workloads), and openssh (for remote access). These
services SHALL start automatically on boot.

#### Scenario: Core services are running after boot

- **WHEN** the Rock64 boots the built image
- **THEN** systemd is PID 1, `podman` is available on PATH, and `sshd` is listening

### Requirement: QEMU testing target is available

The flake SHALL define a `nixosConfigurations.rock64-qemu` output that shares the majority of the Rock64 configuration
but targets `aarch64-virt` for QEMU testing. The QEMU target SHALL be bootable via `./result/bin/run-vm` or equivalent.

#### Scenario: QEMU VM boots successfully

- **WHEN** `nix build .#rock64-qemu-vm` is run and the resulting VM script is executed
- **THEN** the NixOS system boots in QEMU with systemd, podman, Cockpit, and other services available

#### Scenario: QEMU target shares configuration with hardware target

- **WHEN** the Rock64 and rock64-qemu configurations are compared
- **THEN** they share the same service configuration, firewall rules, and application setup, differing only in
  hardware-specific settings (kernel, DTB, device paths)
