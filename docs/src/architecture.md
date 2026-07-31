# Architecture

AtomixOS combines several architectural patterns to achieve reliable over-the-air updates on embedded hardware:

- **A/B partition scheme** with paired boot and rootfs slots
- **Read-only squashfs rootfs** with OverlayFS root (squashfs lower + tmpfs upper) for runtime state
- **U-Boot boot-count rollback** with watchdog integration (currently disabled on Rock64 during development)
- **Network isolation** with no IP forwarding between WAN and LAN interfaces
- **EN18031-compliant authentication** with no embedded credentials

This chapter covers each of these in detail. For the rationale behind specific design choices, see [Design
Decisions](./design-decisions.md).

## Immutable Build Policy

Build-stage policy is separate from mutable runtime provisioning. The committed `build.toml` defines schema-owned
settings fixed into NixOS systems, disk images, and update bundles; `/data/config/config.toml` continues to own runtime
operator and application state.

Nix evaluates and validates build policy before constructing artifacts, then maps effective values to existing NixOS
module options. Each configured system exposes byte-identical, read-only policy and provenance at
`/etc/atomixos/build.toml` and `/etc/atomixos/build-metadata.json`. Disk image and RAUC bundle output directories carry
the same files as audit sidecars.

`build.toml` does not own source revision, `flake.lock`, production verification certificates, signing credentials, or
signing trust. Those remain separate release inputs and require their own evidence.
