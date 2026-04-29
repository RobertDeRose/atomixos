# Proposal

## Why

- Rock64 devices need a robust OTA update model that keeps the previous system bootable while a new image is written and
  verified.
- The device is also the LAN isolation boundary for downstream legacy equipment, so networking, authentication, and
  recovery behavior must be explicit parts of the platform design.
- Early exploration included an on-device Cockpit/Traefik management path and password-oriented fallback flows, but the
  implemented platform moved to a smaller appliance baseline: Podman stays on-device for workloads, while remote web
  management is expected to live in the Nixstasis environment instead of the device image itself.

## What Changes

- Introduce a NixOS flake that builds the Rock64 system, flashable image, signed RAUC bundle, and QEMU test target
- Implement an A/B layout with per-slot boot partitions, squashfs rootfs slots, and `/data` created on first boot by
  initrd `systemd-repart`
- Use RAUC plus U-Boot bootmeth for slot switching and rollback, with `rauc status mark-good` used for confirmation
- Keep Podman, OpenVPN, OpenSSH, chrony, dnsmasq, nftables, and the update client in the device image
- Remove the local Cockpit/Traefik management stack from the final device design while preserving application workloads
  through Podman
- Use SSH-key-only operator access, locked local passwords, and `_RUT_OH_` as a physical serial recovery path
- Support provisioning-aware first boot through the bounded `config.toml` contract defined by the
  `first-boot-local-provisioning` follow-on change
- Keep the update client swappable between the default `os-upgrade` polling path and a future hawkBit path

## Capabilities

### New Capabilities

- `nix-flake-config`: Rock64/QEMU flake outputs, stripped kernel, core runtime services, and build artifacts
- `partition-layout`: Flashable image layout with U-Boot raw region, slot A in the image, and slot B plus `/data`
  provisioned on first boot
- `rauc-integration`: RAUC system configuration, signed multi-slot bundle building, slot definitions, and update client
  integration
- `boot-rollback`: U-Boot boot-count logic and RAUC-driven slot confirmation / rollback behavior
- `watchdog`: Hardware-watchdog-oriented design, with QEMU validation and hardware re-enablement tracked separately
- `update-confirmation`: Local `os-verification` health checks before committing updated slots
- `lan-gateway`: Deterministic NIC naming, DHCP/NTP on LAN, nftables policy, and no packet forwarding between WAN and
  LAN

### Follow-on Changes

- `first-boot-local-provisioning`: Refines the day-0 and reprovisioning flow, the `config.toml` contract, and the
  `/data/config/` persistence boundary
- `durable-journald-logs`: Defines the current runtime log durability model and the still-incomplete initrd forensic
  redesign

## Impact

- **Affected code**: `flake.nix`, shared/system modules, image and bundle derivations, U-Boot boot script, RAUC config,
  first-boot/update services, and QEMU tests
- **Affected storage layout**: raw U-Boot region, per-slot boot/rootfs partitions, and durable operator/runtime state on
  `/data`
- **Affected operations**: flash/build workflow, first boot, update confirmation, rollback, LAN gateway bring-up, and
  remote recovery
- **Security**: no embedded login credentials, key-only operator access, WAN SSH disabled by default, and no default
  packet forwarding between networks
