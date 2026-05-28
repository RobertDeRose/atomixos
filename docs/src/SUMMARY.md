# Summary

[Introduction](./introduction.md)

<!-- rumdl-disable MD025 -->

# User Guide

- [Architecture](./architecture.md)
  - [Partition Layout](./architecture/partition-layout.md)
  - [Network Topology](./architecture/network-topology.md)
  - [Update & Rollback Flow](./architecture/update-rollback.md)
  - [Authentication (EN18031)](./architecture/authentication.md)
  - [Nixstasis Enrollment](./architecture/overwatch-enrollment.md)
- [Building](./building.md)
- [Testing](./testing.md)
- [Provisioning](./provisioning.md)
  - [Flashable Disk Image](./provisioning/flash-image.md)
  - [LAN Range Configuration](./provisioning/lan-range.md)
- [Firmware Data Flow](./data-flow.md)
- [Runtime Boundaries](./runtime-boundaries.md)
- [Operational Unknowns](./unknowns.md)

# Tutorials

- [OIDC-Authenticated Device Management](./tutorials/oidc-device-management.md)

# Operations

- [Hardware Testing](./hardware-testing.md)
- [NTP Settings](./operations/ntp-settings.md)

# Specifications

- [Nix Flake Configuration](./specs/nix-flake-config.md)
- [Partition Layout](./specs/partition-layout.md)
- [RAUC Integration](./specs/rauc-integration.md)
- [Boot & Rollback](./specs/boot-rollback.md)
- [Watchdog](./specs/watchdog.md)
- [Update Confirmation](./specs/update-confirmation.md)
- [LAN Gateway](./specs/lan-gateway.md)

# Design

- [Design Decisions](./design-decisions.md)
- [Planned Features](./planned-features.md)
- [Features](./features.md)
  - [Rock64 A/B Image](./features/rock64-ab-image/design.md)
    - [Tasks](./features/rock64-ab-image/tasks.md)
  - [First-Boot Local Provisioning](./features/first-boot-local-provisioning/design.md)
    - [Tasks](./features/first-boot-local-provisioning/tasks.md)
  - [Durable Journald Logs](./features/durable-journald-logs/design.md)
    - [Tasks](./features/durable-journald-logs/tasks.md)
  - [Config Reapply Improvements](./features/config-reapply-improvements/design.md)
    - [Tasks](./features/config-reapply-improvements/tasks.md)
  - [Provisioning API Service](./features/provisioning-api-service/design.md)
    - [Tasks](./features/provisioning-api-service/tasks.md)
  - [Caddy AuthCrunch Cockpit Tutorial](./features/caddy-authcrunch-cockpit-tutorial/design.md)
    - [Tasks](./features/caddy-authcrunch-cockpit-tutorial/tasks.md)
  - [Nixstasis Client](./features/nixstasis-client/design.md)
    - [Tasks](./features/nixstasis-client/tasks.md)

# Reference

- [Task Reference](./reference/tasks.md)
- [Flake Outputs](./reference/flake-outputs.md)
- [Project Structure](./reference/project-structure.md)
- [Code Reference](./code-reference.md)
  - [NixOS Modules](./code-reference/modules.md)
  - [Nix Derivations](./code-reference/derivations.md)
  - [Scripts](./code-reference/scripts.md)
