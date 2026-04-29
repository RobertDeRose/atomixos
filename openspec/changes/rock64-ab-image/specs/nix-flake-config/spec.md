# Nix Flake Config Spec

## ADDED Requirements

### Requirement: The flake defines Rock64 and QEMU system configurations

The flake SHALL define `nixosConfigurations.rock64` for the real Rock64 hardware target and
`nixosConfigurations.rock64-qemu` for the shared QEMU test target.

#### Scenario: Flake evaluates successfully

- **WHEN** `nix flake check` is run against the repository
- **THEN** the flake evaluates without errors
- **AND** both `nixosConfigurations.rock64` and `nixosConfigurations.rock64-qemu` are present

#### Scenario: System configuration targets `aarch64-linux`

- **WHEN** the Rock64 configuration is built
- **THEN** its system outputs target `aarch64-linux`

### Requirement: The flake produces a read-only squashfs root filesystem

The flake SHALL produce a squashfs image as `packages.aarch64-linux.squashfs`. The image SHALL contain the system
closure required for the appliance baseline and SHALL be sized to fit within the 1 GiB rootfs slot.

#### Scenario: Squashfs image builds successfully

- **WHEN** `nix build .#squashfs` is run
- **THEN** a squashfs image is produced

#### Scenario: Squashfs image fits the slot budget

- **WHEN** the squashfs image is built
- **THEN** the resulting image is no larger than the configured 1 GiB slot limit

### Requirement: The flake produces a signed RAUC bundle and flashable image

The flake SHALL expose a signed RAUC bundle as `packages.aarch64-linux.rauc-bundle` and a flashable device image as
`packages.aarch64-linux.image`.

#### Scenario: RAUC bundle builds successfully

- **WHEN** `nix build .#rauc-bundle` is run
- **THEN** a signed `.raucb` file is produced that passes `rauc info`

#### Scenario: Flashable image builds successfully

- **WHEN** `nix build .#image` is run
- **THEN** a flashable Rock64 disk image is produced containing U-Boot, `boot-a`, and `rootfs-a`

### Requirement: The configuration uses a stripped kernel with modular USB peripheral support

The Rock64 configuration SHALL use a stripped kernel profile with RK3328-required storage, networking, USB host,
watchdog, squashfs, f2fs, and overlay support built in. Optional USB WiFi, Bluetooth, and USB serial support SHALL be
available as modules.

#### Scenario: Kernel boots on Rock64 hardware

- **WHEN** the built kernel and DTB are loaded by U-Boot on a Rock64 board
- **THEN** the kernel boots and detects the required Rock64 hardware path

#### Scenario: Optional USB peripherals load on demand

- **WHEN** a supported USB WiFi, Bluetooth, or serial device is connected
- **THEN** the matching kernel module can be loaded without rebuilding the image

### Requirement: The device image includes the core appliance runtime

The Rock64 configuration SHALL include systemd, Podman, OpenSSH, OpenVPN, chrony, dnsmasq, nftables, and the services
required for the A/B update system, first-boot provisioning flow, and LAN gateway role.

#### Scenario: Core runtime services are available after boot

- **WHEN** the Rock64 boots the built image
- **THEN** systemd is PID 1
- **AND** Podman is available for application workloads
- **AND** SSH, LAN gateway, and update services are present in the system configuration

### Requirement: Local web management is not part of the base image

The base Rock64 image SHALL NOT require Cockpit or Traefik to be built into the system closure.

#### Scenario: Appliance baseline excludes local management stack

- **WHEN** the Rock64 image is built
- **THEN** the core platform remains bootable and manageable without a local Cockpit/Traefik stack in the image itself

### Requirement: The flake exposes a QEMU testing target that shares the core configuration

The `rock64-qemu` target SHALL reuse the shared base system configuration while swapping only the hardware-specific
pieces needed for `aarch64-virt` test execution.

#### Scenario: QEMU target boots successfully

- **WHEN** the QEMU test target is built and run
- **THEN** the system boots with the shared AtomixOS runtime and test harness overrides

#### Scenario: QEMU target stays close to hardware target

- **WHEN** the Rock64 and QEMU configurations are compared
- **THEN** they share the same core service, firewall, and update logic while differing only in hardware/test-specific
  details
