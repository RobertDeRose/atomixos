# Planned Features

## Project Overview

AtomixOS is a secure, reproducible operating system for single-board computers, built on
NixOS with atomic A/B OTA updates, automatic rollback, and a container-based application
deployment model. The system uses a read-only squashfs rootfs and operator-provisioned
Quadlet containers on a persistent `/data` partition.

See the [project overview](./introduction/project-overview.md) for the current audience, scope, and ownership
boundaries. After migration, Beads is authoritative for live status, dependencies, claims, and ready-work selection;
this page remains the human-readable roadmap.

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
- Bootstrap exposure is WAN/LAN before initial provisioning and LAN-only after
  successful provisioning; runtime socket rebinding must use `/run/systemd/system`
  drop-ins because the rootfs is read-only
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
  only until initial provisioning completes, then rebinding the bootstrap socket
  to LAN through runtime systemd drop-ins and preserving WAN exposure while an
  initial promotion marker is pending.
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
- Live execution state is queried through Beads; this page retains concise direction and historical context.
- Completed features move into [Implemented Features](./features/index.md).

## Feature Map

### Rock64 A/B Image (`rock64-ab-image`)

- Status: partially completed
- Overview: Provides the initial Rock64 reference image, read-only squashfs root, A/B RAUC update path, rollback,
  gateway profile, and validation harness.
- Remaining work: Physical-device network, update, authentication, and watchdog validation remains open; the generic
  appliance platform must not assume all future hardware uses the Rock64 layout or gateway profile.
- Delivered so far: Flashable image and bundle outputs, boot-count rollback, QEMU checks, core networking, provisioning,
  and the initial Rock64 hardware bring-up path.

### First-Boot Local Provisioning (`first-boot-local-provisioning`)

- Status: completed
- Overview: Imports a complete `config.toml` from the initial boot partition, USB media, or the constrained local web
  console, validates it, persists desired state under `/data/config`, and confirms the slot only after provisioning.
- Delivered in: `modules/first-boot.nix`, `scripts/first-boot.sh`, the provisioning package, and first-boot VM checks.

### Durable Journald Logs (`durable-journald-logs`)

- Status: partially completed
- Overview: Separates bounded slot-local Tier 0 forensic events from volatile journald and batched persistent logs under
  `/data/logs`.
- Remaining work: Redesign and validate the initrd forensic path and complete the associated hardening regression
  coverage.

### Provisioning API Service (`provisioning-api-service`)

- Status: partially completed
- Overview: Replaces the one-shot provisioning importer with the long-lived Litestar service and shared validation,
  rendering, promotion, activation, rollback, and asynchronous job pipeline.
- Dependencies: `first-boot-local-provisioning`, `config-reapply-improvements`
- Remaining work: Close the retained full-build, config round-trip, and rootfs closure-budget validation tasks.

### Network Config Extensions (`network-config-extensions`)

- Status: completed
- Overview: Adds validated DNS, search-domain, default-route, and Ethernet interface configuration to the shared atomic
  config apply and rollback path while preserving the isolated gateway defaults.
- Dependencies: `config-reapply-improvements`
- Delivered in: The config schema and parser, derived network state, runtime application, rollback coverage, and
  operator documentation.

### Activation Options (`activation-options`)

- Status: completed
- Overview: Adds bounded activation timeout, settle, restart, degraded-service, and rollback policy to the shared config
  apply path without enabling arbitrary commands or unsafe systemd unit control.
- Dependencies: `config-reapply-improvements`
- Delivered in: The config schema and parser, `activation-policy.json`, runtime activation handling, tests, and docs.

### Caddy AuthCrunch Cockpit Tutorial (`caddy-authcrunch-cockpit-tutorial`)

- Status: completed
- Overview: Provides a comprehensive tutorial section in the documentation with a
  fully working `config.toml` bundle deploying Caddy with the AuthCrunch plugin for
  Microsoft Entra OIDC authentication, JWT token generation with OIDC group-to-role
  mapping, and Cockpit-ws for container management. The tutorial demonstrates the full
  power of the config.toml provisioning system including containers, networks, volumes,
  and bundle files.
- Requirements:
  - Working `config.toml` with all required sections (users, network, health, containers)
  - AuthCrunch container (`ghcr.io/authcrunch/authcrunch`) as rootful with host networking
  - Caddyfile configuring Microsoft Entra OIDC provider, authentication portal, and
    authorization policies
- OIDC group mapping to local roles: `authp/admin` (sudoless admin) and `authp/user`
  (generic user) based on Entra security group membership
- JWT token generation with configurable lifetime and signing key
- Cockpit-ws container (`quay.io/fedora/fedora`) for device/container management, built
  from a custom Containerfile that adds Cockpit management modules
- Caddy-gated Cockpit local session: Caddy restricts `/cockpit/*` to `authp/admin`,
  and cockpit-ws runs `--local-session` behind the proxy -- eliminates double
  authentication
- Quadlet `.build` support for building custom container images from Containerfiles
- Podman module integration so operators can manage provisioned pods from Cockpit
- Quadlet network definition for inter-container communication
- Quadlet volume definition for persistent Caddy state
- Bundle `files/` directory with Caddyfile and cockpit.conf
- Clear documentation of Azure App Registration prerequisites
- Clear documentation of how to swap the Caddyfile identity provider block for Google
  or another OIDC provider
- Clear documentation of the authentication flow and role-based access
- Constraints:
  - Must use only config.toml features that exist today or are added as part of this
    feature (containers, networks, volumes, builds, bundle files,
    `${CONFIG_DIR}`/`${FILES_DIR}` tokens)
- Caddy must be rootful (needs host network for ports 80/443)
- Cockpit-ws uses `--local-session` behind Caddy/AuthCrunch (no double auth)
- Must not require changes to the AtomixOS base image or schema beyond `.build`
  support
- Tutorial values (tenant ID, client ID, domain) must use obvious placeholders
- Non-goals:
  - Modifying the AtomixOS base image to include Cockpit or cockpit-podman
  - Production-hardening the example (certificate pinning, secret rotation, HA)
  - SAML providers (tutorial focuses on OIDC)
- Success criteria:
  - An operator can copy the tutorial config, substitute their Azure/domain values, flash
    a device, and have a working OIDC-authenticated Caddy + Cockpit stack
- The tutorial config passes `first-boot-provision validate`
- Role mapping is demonstrated: Entra group A gets admin, group B gets user
- The tutorial clearly explains the powerful host socket mounts used by the admin
  Cockpit container
- Risks and tradeoffs:
  - **Cockpit local-session risk**: Cockpit does not perform a second login. Caddy must
    remain the only public entry point and `/cockpit/*` must remain admin-only.
- **AuthCrunch version churn**: AuthCrunch/caddy-security evolves rapidly; Caddyfile
  syntax may change between versions.
- **Entra group claim configuration**: Requires Azure portal configuration (Token
  Configuration > Add groups claim) that is outside AtomixOS control.
- **Cockpit package drift**: Container-installed Cockpit modules may not match host
  service versions exactly; native host packaging can be added later if needed.
- Dependencies:
  - Network and volume Quadlet support, already delivered in commit 85ec53c
  - Bundle file support with `${FILES_DIR}` token substitution (completed)
  - Container, network, volume rendering and sync (completed)
  - Quadlet `.build` support (completed)
- Suggested validation:
  - `first-boot-provision validate` on the tutorial config.toml
  - NixOS VM test importing the tutorial bundle and verifying rendered Quadlet files
  - Manual verification with a real Entra tenant (cannot be automated)
- Delivered in: `docs/src/tutorials/oidc-device-management.md` and
  `example/caddy-oidc/`

### Nixstasis Client (`nixstasis-client`)

- Status: completed
- Overview: AtomixOS can include the Nixstasis enrollment client from the
  Nixstasis flake as immutable base-system code. The module renders client
  configuration, persists identity and remote-access SSH keys under
  `/data/nixstasis`, and runs registration/polling services that tolerate WAN or
  server outages without blocking local recovery.
- Requirements:
  - Device identifies itself via eth0 MAC address
  - Server checks MAC against approved inventory
  - Approved devices receive and persist a device UUID and runtime token at
    `/data/nixstasis/id`
  - Client launches FRP remote-access sessions from heartbeat responses
  - Nixstasis-managed SSH keys remain separate from provisioned operator keys
- Constraints:
  - Must survive container-layer failures (lives in rootfs, not a container)
  - Must work with key-only SSH authentication model
  - Must not require default credentials
- Non-goals:
  - Hosting web management UI on the device
  - Fleet orchestration logic (server-side concern)
- Success criteria:
  - Device enrolls with Nixstasis server using MAC-based eligibility
  - Registration key persists across reboots and updates
  - FRP launch boundary is validated when the mock API requests remote access
  - NixOS VM test covers enrollment, identity reuse, polling, and outage behavior
- Risks and tradeoffs:
  - Depends on Nixstasis server API being stable and documented
  - Tunnel reliability on unstable WAN connections
- Dependencies: None (can start independently)
- Suggested validation:
  - NixOS VM test with mock Nixstasis server
  - Integration test with real Nixstasis instance
- Delivered in: `modules/nixstasis.nix`, `nix/tests/nixstasis-client.nix`, and
  `docs/src/features/nixstasis-client/`

### Fleet Bootstrap via Nixstasis (`fleet-bootstrap-via-nixstasis`)

- Status: planned; Beads root `atomixos-mol-efd`
- Design: [Fleet Bootstrap via Nixstasis](./features/fleet-bootstrap-via-nixstasis/design.md)
- Overview: Add an explicit build-time fleet transport that keeps the existing provisioning API on loopback until the
  device is approved by Nixstasis and receives a short-lived remote-access lease. The server selects a bounded plain
  HTTP FRP route to `127.0.0.1:8080` and submits the existing complete config/bundle pipeline; no new AtomixOS
  provisioning command or direct `/data` mutation path is added.
- Requirements:
  - Keep `bootstrap_transport = "network"` as the standalone/personal/development default
  - Require explicit `[provisioning]` and `[nixstasis]` policy for fleet images
  - Bind the fleet bootstrap API to loopback and suppress pending WAN/LAN rebind exposure
  - Consume the upstream bounded route-profile capability tracked by Nixstasis `nixstasis-255`
  - Preserve existing staging, validation, activation, rollback, bundle, and SSH-signature contracts
- Dependencies: delivered Nixstasis route profiles `nixstasis-255`, Host rewriting `nixstasis-fss`, server-side bundle
  delivery `nixstasis-4gg`, and the existing `build-configuration`, `nixstasis-client`, and `provisioning-api-service`
  foundations
- Suggested validation: strict build-policy evaluator tests, socket/firewall NixOS checks, mock enrollment/route-profile
  VM coverage, and documentation/link validation

### RAUC Production Keyring Policy (`rauc-production-keyring-policy`)

- Status: planned
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

### Provisioning API Privilege Separation (`provisioning-api-privilege-separation`)

- Status: completed
- Overview: Split the network-facing provisioning API process from privileged host
  mutation work. The web process should run unprivileged, stage validated
  candidates in tmpfs, and hand them to a root systemd path-triggered worker for
  config promotion, service activation, firewall changes, and socket rebinding.
- Requirements:
  - Run the Litestar/uvicorn service as an unprivileged user
  - Define a minimal staged manifest contract for apply/recover/activate actions
  - Preserve single-flight apply semantics and job progress reporting
  - Preserve first-boot bootstrap behavior and SSH-signed reapply behavior
  - Ensure staged inputs are verified and scoped to `/data/config`
- Constraints:
  - Must work with read-only rootfs and mutable `/data`
  - Must avoid adding DB, Redis, or heavyweight IPC dependencies
  - Must not regress first-boot operator workflow
- Non-goals:
  - Full multi-tenant authorization model
  - Remote fleet orchestration
- Success criteria:
  - Compromise of the HTTP process does not directly grant root shell or arbitrary
    filesystem mutation
- Apply/recover/rollback paths still pass existing Python and Nix VM tests
- Systemd hardening is documented and enforced in the service unit
- Risks and tradeoffs:
  - Staging boundary adds implementation and test complexity
  - Progress reporting needs a simple result handoff contract
- Dependencies: `provisioning-api-service`
- Suggested validation: VM test proving unprivileged service can provision via the root worker
- Delivered by running the bootstrap API as `atomixos-provision`, staging
  validated candidate jobs under `/run/atomixos-provision`, applying them through
  a root `systemd.path`/oneshot worker, and documenting the result/queue lock
  handoff in the runtime boundary docs.

### Provisioning API Live Schema Contract (`provisioning-api-live-schema-contract`)

- Status: completed
- Overview: Treat the live OpenAPI schema exposed by the provisioning service as a
  supported client contract, not incidental framework output.
- Requirements:
  - Keep API routes documented with accurate request bodies, headers, responses, and
    error shapes
- Exclude Boot UI/static routes from the API schema unless deliberately documented
- Add tests that assert schema coverage for new API endpoints
- Preserve operation IDs and domain tags for client generation
- Constraints:
  - Live schema exposure is intentional for online clients
  - Must not expose inaccurate write-only implementation routes
  - Must keep schema generation dependency-light
- Non-goals:
  - Replacing `config.toml` as the canonical import/export artifact
  - Adding OAuth/JWT solely for docs access
- Success criteria:
  - Generated clients can submit config, poll jobs, validate config, and handle errors
    using the live schema
- CI fails when a new API route lacks schema assertions
- Risks and tradeoffs:
  - Litestar defaults may need explicit overrides for raw binary endpoints
  - Schema tests add maintenance cost but prevent client drift
- Dependencies: `provisioning-api-service`
- Suggested validation: Python tests against `/schema/openapi.json`
- Delivered by adding focused OpenAPI schema assertions for public route coverage, operation
  IDs, domain tags, binary config upload bodies, auth headers, response schemas, error schemas,
  and Boot UI/static route exclusion.

### Typed Partial Provisioning API (`typed-partial-provisioning-api`)

- Status: completed
- Overview: Add typed partial configuration endpoints for common operations while
  preserving `config.toml` and bundles as the canonical import/export/backup format.
  Partial changes must always produce a full desired state and reuse the existing
  validate, render, promote, activate, and rollback pipeline.
- Requirements:
  - Add typed endpoints for users, network/LAN settings, container services, volumes,
    and firewall inbound rules in priority order
- Load current desired state, apply the typed patch, validate the full result, render
  a candidate, promote atomically, activate, and roll back on failure
- Return async jobs with progress just like full config submission
- Preserve config export/backup semantics after partial changes
- Constraints:
  - Must not mutate derived files directly under `/data/config`
  - Must not introduce a database or divergent state store
  - Must keep full config import behavior authoritative
- Non-goals:
  - Arbitrary JSON patch over internal rendered state
  - Fleet-level orchestration
- Success criteria:
  - Partial updates and full config imports converge on the same on-disk desired state
  - Failed partial updates roll back identically to failed full imports
  - Live OpenAPI accurately documents each typed endpoint
- Risks and tradeoffs:
  - More API surface increases schema and validation maintenance
  - Some edits may require restart ordering or health semantics not yet modeled
- Dependencies: `provisioning-api-service`, `provisioning-api-live-schema-contract`
- Suggested validation: Python tests for typed patch-to-full-state conversion plus VM
  tests for at least one user and one container partial update
- Delivered by adding authenticated partial endpoints for users, network, containers,
  container networks, container volumes, and config export. Partial mutations produce full
  canonical `config.toml` candidates and reuse the existing async validation, render,
  promotion, activation, rollback, and job pipeline.

### Boot UI HTMX (`boot-ui-htmx`)

- Status: completed
- Overview: Redesign the first-boot Boot UI as a small server-rendered HTMX interface
  while preserving the current upload/paste provisioning flow and bootstrap CSRF token
  controls.
- Requirements:
  - Keep first-boot UI available only before provisioning completes
  - Preserve upload and paste config paths
  - Show async job progress using the returned job URL
  - Reuse server-rendered fragments; no SPA/Vite dependency
  - Maintain Host/Origin/Referer protections and bootstrap token checks
- Constraints:
  - Must fit embedded rootfs constraints
  - Must not add a separate frontend build pipeline unless justified
  - Must not introduce unauthenticated post-provision mutation paths
- Non-goals:
  - Full on-device management UI
  - Replacing programmatic `/api/config`
- Success criteria:
  - Operator can provision from desktop and mobile browsers
  - UI reflects validation/apply progress and final forwarding URL
  - UI tests cover first-boot only exposure and CSRF failure paths
- Risks and tradeoffs:
  - More UI affordances increase bootstrap attack surface if not carefully scoped
  - HTMX fragments must stay aligned with API/job behavior
- Dependencies: `provisioning-api-service`
- Suggested validation: Python route tests and manual browser test in VM
- Delivered by making `/apply` submit asynchronous provisioning jobs, rendering
  first-boot-only job status fragments, preserving bootstrap CSRF and browser
  origin checks, and keeping Boot UI routes excluded from live OpenAPI.

### Build Configuration (`build-configuration`)

- Status: delivered locally
- Beads root: `atomixos-mol-0ws`
- Design: [Build Configuration](./features/build-configuration/design.md)
- Implemented record: [Build Configuration delivery](./features/build-configuration/index.md)
- Overview: Add a versioned build-stage `build.toml` contract for immutable image policy, with watchdog settings as the
  first consumer and an ignored `build.dev.toml` overlay for local experiments.
- Requirements:
  - Keep committed `build.toml` complete, strict, and reproducible
  - Automatically apply local overrides in supported `mise` build/check workflows with a conspicuous warning
  - Reject unknown or malformed policy before artifacts build
  - Embed effective non-secret policy and provenance in systems, images, and update bundles
- Non-goals: Runtime provisioning settings, secrets, arbitrary Nix fragments, or multiple profile layers
- Dependencies: None; delivery unblocks the physical Watchdog Enforcement validation chain
- Suggested validation: Nix evaluation checks, command-level wrapper tests, artifact provenance checks, and strict docs
- Delivered: strict version-1 policy and local-overlay validation, watchdog option mapping, immutable system and artifact
  provenance, `-dev` identity, configuration-aware `mise` routing, and failure-safe retained artifact replacement

### Watchdog Enforcement (`watchdog-enforcement`)

- Status: delivered; external reset timing, RAUC rollback, and soak validation remain deferred to the OTA campaign
- Overview: Add opt-in hardware watchdog enforcement with build-time selection of the onboard or external watchdog,
  `RuntimeWatchdogSec=30s`, and `RebootWatchdogSec=10min`, while keeping Rock64 release profiles disabled by default.
- Requirements:
  - Reuse the existing opt-in systemd manager watchdog settings
  - Keep active enforcement disabled by default
  - Continue booting with a warning if enabled watchdog hardware is unavailable
  - Complete Rock64 boot-reliability validation before release-profile enablement
  - Verify that watchdog resets on a newly updated, unconfirmed slot consume U-Boot attempts and cause fallback
- Constraints:
  - Must not cause false-positive reboot loops during normal operation
  - Must be validated on physical hardware before enabling
- Non-goals: Software-only watchdog or runtime `config.toml` control
- Success criteria:
  - With the default 30-second timeout, watchdog reset begins within 35 measured seconds of confirmed kick cessation
  - Three consecutive watchdog resets before slot confirmation trigger automatic fallback
  - No false triggers occur during a normal 72-hour soak test
- Risks and tradeoffs:
  - Aggressive timeout may cause false triggers on slow boots
  - Fail-open missing-device behavior preserves availability but requires observable warnings
  - Physical behavior cannot be fully validated in QEMU
- Dependencies: `build-configuration`, a sacrificial Rock64, serial recovery, and hardware soak availability
- Suggested validation: module evaluation checks, `rauc-watchdog` VM check, and ordered physical reboot, rollback, and
  72-hour soak evidence
- Delivered so far: `atomixos.watchdog.*` options, internal/external build-time selection, default-disabled behavior,
  fail-open checks, physical device and ownership validation for both paths, internal induced-reboot validation, and
  hardware validation instructions.

### USB WiFi (`usb-wifi`)

- Status: deferred
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

### Config Reapply Improvements (`config-reapply-improvements`)

- Status: completed
- Overview: Harden the existing config re-apply path (`POST /api/config` on the
  always-running bootstrap server) with authentication, atomic replacement, and
  rollback-on-failure. The basic re-apply mechanism already works: any POST overwrites
  `/data/config` and triggers `quadlet-sync` to restart services.
- Requirements:
  - Authentication guard on the re-apply endpoint (not a reset token)
  - Atomic replacement of `/data/config` (write to temp, swap on success)
  - Validate new config before replacing old config
  - Rollback to previous config if new config's services fail to start
- Constraints:
  - Must not touch `/data` outside of `/data/config`
  - Must not break the existing unguarded first-provision flow on fresh devices
  - Authentication mechanism must work on LAN-local without external dependencies
- Non-goals:
  - Full `/data` wipe (separate operation)
  - Partial config updates (always full replacement)
  - Changing the existing provisioning flow for fresh devices
- Success criteria:
  - Unauthenticated POST to `/api/config` is rejected on an already-provisioned device
  - Authenticated POST atomically replaces config and restarts services
  - Crash during replacement leaves previous config intact
  - Failed service startup triggers automatic rollback to previous config
- Risks and tradeoffs:
  - Container state (volumes, data) may be inconsistent after rollback
  - Service downtime during re-apply is unavoidable
  - Authentication mechanism choice affects operational complexity
- Dependencies: None (existing mechanism works; this is hardening)
- Suggested validation: NixOS VM test with sequential config imports, crash simulation,
  and rollback verification
- Delivered by adding the canonical versioned `config.toml` schema, managed-user
  materialization, SSH-signature authentication for provisioned-device re-apply,
  crash-safe candidate promotion, activation health checks, rollback on failure,
  and docs/tests for the updated re-apply contract. A managed-user reboot VM test
  remains deferred pending persistent VM disk support.
