# Architecture

AtomixOS combines several architectural patterns to achieve reliable over-the-air updates on embedded hardware:

- **A/B partition scheme** with paired boot and rootfs slots
- **Read-only squashfs rootfs** with OverlayFS root (squashfs lower + tmpfs upper) for runtime state
- **U-Boot boot-count rollback** with watchdog integration (currently disabled on Rock64 during development)
- **Network isolation** with no IP forwarding between WAN and LAN interfaces
- **EN18031-compliant authentication** with no embedded credentials

This chapter covers each of these in detail. For the rationale behind specific design choices, see [Design
Decisions](./design-decisions.md).
