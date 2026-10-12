# Planned Features

## Project Overview

AtomixOS is a secure, reproducible operating system for single-board computers, built on
NixOS with atomic A/B OTA updates, automatic rollback, and a container-based application
deployment model. The system uses a read-only squashfs rootfs and operator-provisioned
Quadlet containers on a persistent `/data` partition.

See the [project overview](./introduction/project-overview.md) for the current audience, scope, and ownership
boundaries. Beads is authoritative for live status, dependencies, claims, and ready-work selection; this page remains
the human-readable roadmap.

## Goals

- Ship complete, reproducible embedded appliance firmware with zero default credentials, using the gateway profile as
  the initial reference use case
- Provide atomic, rollback-safe over-the-air updates for thousands of remote devices
- Allow operators to provision application containers, networks, and volumes via a
  single `config.toml` without touching the base image
- Support EN18031 compliance for network isolation, authentication, and audit
- Support optional Nixstasis-based remote management through enrollment and tunnels
- Deliver a working reference stack (Caddy + AuthCrunch + Cockpit-ws) demonstrating
  OIDC-authenticated device management through config.toml

## Non-Goals

- Desktop or server NixOS distribution
- Multi-architecture support beyond aarch64 (Rock64 RK3328)
- Container orchestration (Kubernetes, Swarm) -- Quadlet is the runtime
- Delta OTA updates (full image writes are the current model)
- On-device web management UI in the base image (remote management can be provided through optional Nixstasis
  integration)
- General-purpose firewall/router functionality (no IP forwarding, ever)

## Global Constraints

- 16 GB eMMC with fixed A/B partition layout; rootfs slot is 1 GB max
- Squashfs root is read-only; all mutable state lives on `/data` (f2fs)
- EN18031: no default credentials, no IP forwarding, key-only SSH
- Provisioned containers must go through the Quadlet safety boundary (rootful=host
  network, rootless=pasta with loopback publish rewrites)
- `config.toml` is the single runtime provisioning input; schema changes must not break existing configs
- Immutable image policy belongs to the planned build-stage `build.toml`, not runtime provisioning
- RAUC bundles are signed; only CA-signed updates are accepted
- Hardware watchdog enforcement is implemented as an opt-in module setting and remains
  disabled in release/deployment profiles until boot-reliability validation completes

## Cross-Cutting Decisions

- `POST /api/config` is the programmatic provisioning endpoint; same validation as the
  web console
- Fresh first-boot `POST /api/config` is intentionally tokenless for programmatic
  provisioning; the bootstrap token is a Boot UI CSRF control for `/apply`, not
  operator authentication
- Provisioned re-apply requires SSH signature authentication; `/api/validate` also
  requires SSH authentication
- Network bootstrap exposure is WAN/LAN before initial provisioning and LAN-only after
  successful provisioning; fleet bootstrap exposure is loopback-only throughout. Runtime
  socket rebinding must use `/run/systemd/system` drop-ins because the rootfs is read-only
- `quadlet-runtime.json` tracks all rendered units (containers, networks, volumes) with
  mode (rootful/rootless) for sync-quadlet
- Network and volume Quadlet units are always rootful
- `${CONFIG_DIR}` and `${FILES_DIR}` tokens in Quadlet values are substituted at render
  time to `/data/config` and `/data/config/files` respectively
- Bundle imports support `files/` directory for operator payload files
- Re-apply uses authentication, not a reset token
- Full `/data` wipe is separate from config re-apply
- WAN TCP `8080` is reserved for bootstrap exposure and cannot be configured as a
  provisioned WAN inbound rule
- The repository development RAUC CA is an explicit development convenience only;
  production fail-closed keyring enforcement remains planned

## Open Questions

- **Cockpit-podman host integration**: `cockpit-podman` must be installed on the host
  (not in the cockpit-ws container) and communicates via cockpit-bridge. On AtomixOS the
  rootfs is read-only squashfs, so cockpit-podman would need to be in the NixOS closure.
  This means the base image must include it, which crosses the "no on-device web
  management" non-goal boundary. Alternative: treat cockpit-podman as an optional NixOS
  module that operators can enable.
- **Nixstasis credential rotation**: Enrollment and the FRP launch boundary are
  implemented in the base-system client integration. Runtime token rotation and
  full real-server tunnel validation remain future Nixstasis integration work.
- **USB WiFi**: Kernel WiFi/Bluetooth stacks are disabled. Hardware selection needed
  before enablement.
- **Active watchdog enforcement in release profiles**: Deferred pending Rock64
  boot-reliability validation.

## Resolved Questions

- **Cockpit-ws authentication boundary**: Resolved by placing Cockpit behind
  Caddy/AuthCrunch and running cockpit-ws with `--local-session`. Caddy is the
  only public authentication and authorization boundary; `/cockpit/*` is
  restricted to `authp/admin`.
- **Provisioning API foundation**: Resolved by replacing the monolithic
  first-boot provisioner with the `atomixos-provision` Python package, Litestar
  API service, SSH signature authentication, single-flight apply jobs, live
  OpenAPI schema, crash-safe config promotion, activation health checks, and
  rollback handling. Future changes should build on the same validate, render,
  promote, activate, and rollback pipeline instead of adding parallel mutation
  paths.
- **Bootstrap API and UI auth split**: Resolved by keeping programmatic first-boot
  `/api/config` unauthenticated while requiring the Boot UI bootstrap token for
  browser form submission. After provisioning, unauthenticated mutation routes are
  unavailable and re-apply requires SSH signatures.
- **Bootstrap exposure lifecycle**: Resolved by keeping WAN bootstrap exposure
  only for the default network transport until initial provisioning completes,
  then rebinding that socket to LAN through runtime systemd drop-ins. Fleet
  transport is loopback-only from first boot and never installs the WAN rule or
  LAN rebind.
- **User shell configuration**: Resolved by supporting
  `[users.<name>].shell = "bash" | "sh" | "zsh"`. Admin users still default to
  zsh and system users default to bash when no override is set.
- **Additional `[network]` properties**: Resolved by supporting `dns_servers`,
  `dns_search_domains`, `default_gateway`, and `interfaces` for host resolver,
  default route, and Ethernet interface configuration through the existing
  validate, render, promote, activate, and rollback pipeline.
- **Additional `[activation]` options**: Resolved by supporting
  `timeout_seconds`, `settle_seconds`, `restart`, `allow_degraded`, and
  `strategy = "rollback"` through rendered `/data/config/activation-policy.json`.
  `keep-failed`, `manual-confirm`, and platform-managed unit restarts remain
  deferred to preserve the current fail-closed rollback boundary.

## Roadmap Conventions

- Directory names use stable `<slug>` identities.
- Detailed intent belongs in each feature's `design.md`.
- Each feature is represented by one Beads epic with lifecycle and implementation tasks beneath it.
- Live execution state is queried through Beads; this page retains concise direction only.
- Completed features leave this page; their records live in [Implemented Features](./features/index.md).

## Feature Map

### Rock64 A/B Image (`rock64-ab-image`)

- Overview: Provides the initial Rock64 reference image, read-only squashfs root, A/B RAUC update path, rollback,
  gateway profile, and validation harness.
- Remaining work: Physical-device network, update, authentication, and watchdog validation remains open; the generic
  appliance platform must not assume all future hardware uses the Rock64 layout or gateway profile.

### Durable Journald Logs (`durable-journald-logs`)

- Overview: Separates bounded slot-local Tier 0 forensic events from volatile journald and batched persistent logs under
  `/data/logs`.
- Remaining work: Redesign and validate the initrd forensic path and complete the associated hardening regression
  coverage.

### RAUC Production Keyring Policy (`rauc-production-keyring-policy`)

- Overview: Make RAUC production images fail closed unless a production keyring is
  configured, while keeping development and test images explicit about using the
  repository development CA.
- Requirements:
  - Default production behavior must require `atomixos.rauc.keyringCert`
  - Development/test images must explicitly opt into the repository development CA
  - VM tests must set the development opt-in where needed
  - Documentation must show production and development keyring examples
- Constraints:
  - Must not break local VM development workflows
  - Must preserve RAUC signed-bundle verification
  - Must keep release image configuration auditable from Nix options
- Non-goals:
  - Replacing RAUC
  - Managing production CA issuance or rotation server-side
- Success criteria:
  - A release image without `keyringCert` fails evaluation or build
  - Development images continue to build only with an explicit dev-keyring opt-in
  - Docs clearly state that the repository dev CA is never acceptable for production OTA
- Risks and tradeoffs:
  - Existing ad hoc test images may need option updates
  - Operators need a documented CA provisioning workflow before release builds
- Dependencies: RAUC module options from `provisioning-api-service`
- Suggested validation: Nix evaluation tests for both fail-closed and dev opt-in modes
- Suggested first workflow command: `/start-feature rauc-production-keyring-policy`

### USB WiFi (`usb-wifi`)

- Overview: Enable WiFi support for selected USB WiFi hardware.
- Requirements:
  - Select supported USB WiFi chipset and firmware
  - Enable kernel WiFi and Bluetooth stacks
  - Add WiFi NIC to systemd `.link` naming
  - Define WiFi role (WAN backup? LAN extension?)
- Constraints:
  - Must not increase rootfs closure beyond 1 GB slot limit
  - Firmware must be redistributable
- Non-goals: Access point mode (initially)
- Success criteria: WiFi interface comes up and connects to configured network
- Risks and tradeoffs:
  - Firmware blob licensing and size
  - WiFi reliability on embedded hardware
  - Unclear network role
- Dependencies: Hardware selection
- Suggested validation: Hardware test with selected adapter
- Suggested first workflow command: `/start-feature usb-wifi`
