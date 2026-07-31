# Summary

[Introduction](./introduction.md)

- [Project Overview](./introduction/project-overview.md)
- [Documentation Conventions](./introduction/documentation-conventions.md)

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

# Development

- [Developer Tooling](./development/tooling.md)
- [Feature Lifecycle](./development/feature-lifecycle.md)

# Tutorials

- [OIDC-Authenticated Device Management](./tutorials/oidc-device-management.md)

# Operations

- [Hardware Testing](./hardware-testing.md)
- [NTP Settings](./operations/ntp-settings.md)
- [GitHub Pages Deployment](./operations/github-pages.md)

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
  - [First-Boot Local Provisioning](./features/first-boot-local-provisioning/design.md)
  - [Network Config Extensions](./features/network-config-extensions/design.md)
  - [Activation Options](./features/activation-options/design.md)
  - [Durable Journald Logs](./features/durable-journald-logs/design.md)
  - [Config Reapply Improvements](./features/config-reapply-improvements/design.md)
  - [Provisioning API Service](./features/provisioning-api-service/design.md)
  - [Provisioning API Privilege Separation](./features/provisioning-api-privilege-separation/design.md)
  - [Provisioning API Live Schema Contract](./features/provisioning-api-live-schema-contract/design.md)
  - [Typed Partial Provisioning API](./features/typed-partial-provisioning-api/design.md)
  - [Boot UI HTMX](./features/boot-ui-htmx/design.md)
  - [Caddy AuthCrunch Cockpit Tutorial](./features/caddy-authcrunch-cockpit-tutorial/design.md)
  - [Nixstasis Client](./features/nixstasis-client/design.md)
  - [Build Configuration](./features/build-configuration/design.md)
  - [Watchdog Enforcement](./features/watchdog-enforcement/design.md)
- [Implemented Features](./features/index.md)
  <!-- BEGIN IMPLEMENTED FEATURES -->
  - [First-Boot Local Provisioning](./features/first-boot-local-provisioning/index.md)
  - [Network Config Extensions](./features/network-config-extensions/index.md)
  - [Activation Options](./features/activation-options/index.md)
  - [Caddy AuthCrunch Cockpit Tutorial](./features/caddy-authcrunch-cockpit-tutorial/index.md)
  - [Nixstasis Client](./features/nixstasis-client/index.md)
  - [Provisioning API Privilege Separation](./features/provisioning-api-privilege-separation/index.md)
  - [Provisioning API Live Schema Contract](./features/provisioning-api-live-schema-contract/index.md)
  - [Typed Partial Provisioning API](./features/typed-partial-provisioning-api/index.md)
  - [Boot UI HTMX](./features/boot-ui-htmx/index.md)
  - [Config Reapply Improvements](./features/config-reapply-improvements/index.md)
  - [Build Configuration](./features/build-configuration/index.md)
  <!-- END IMPLEMENTED FEATURES -->

# Reference

- [Build Configuration](./reference/build-configuration.md)
- [Flake Outputs](./reference/flake-outputs.md)
- [Project Structure](./reference/project-structure.md)
- [Tooling](./reference/tooling.md)
- [Code Reference](./code-reference.md)
  - [NixOS Modules](./code-reference/modules.md)
  - [Nix Derivations](./code-reference/derivations.md)
  - [Scripts](./code-reference/scripts.md)
