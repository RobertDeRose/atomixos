# Planned Features

## Project Overview

AtomixOS is a secure, reproducible operating system for single-board computers, built on
NixOS with atomic A/B OTA updates, automatic rollback, and a container-based application
deployment model. The system uses a read-only squashfs rootfs and operator-provisioned
Quadlet containers on a persistent `/data` partition.

## Goals

- Ship a complete, reproducible embedded gateway firmware with zero default credentials
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
- `config.toml` is the single operator input; schema changes must not break existing
  configs
- RAUC bundles are signed; only CA-signed updates are accepted
- Hardware watchdog enforcement is deferred until boot-reliability validation completes

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
- **hawkBit integration**: `useHawkbit` option exists but no operational service is
  configured. Needs server configuration, credentials, and verification tests before
  promotion.
- **Nixstasis client**: Enrollment, tunnel lifecycle, and credential rotation are
  documented but not implemented.
- **USB WiFi**: Kernel WiFi/Bluetooth stacks are disabled. Hardware selection needed
  before enablement.
- **Active watchdog enforcement**: Deferred pending Rock64 boot-reliability validation.
- **Additional `[network]` properties**: Evaluate adding `dns_servers`,
  `dns_search_domains`, `default_gateway`, and `interfaces` to the `[network]`
  section for operator-controlled DNS, default route, and NIC configuration.
  These keys are not currently consumed but may be needed for multi-NIC or
  custom DNS setups.
- **User shell configuration**: Allow operators to set `shell = "zsh"` or
  `shell = "bash"` per user in `[users.<name>]`. Currently admin users default
  to `/bin/zsh` and system accounts to `/bin/sh`, with no config override.
- **Additional `[activation]` options**: Evaluate adding activation controls beyond
  `required`, such as `timeout_seconds` for max wait/check windows,
  `rollback_on_failure` for whether to restore previous config, `restart` for an
  explicit ordered service restart list, `settle_seconds` before checking health,
  `allow_degraded` for services allowed to fail without rollback, and
  `strategy = "rollback" | "keep-failed" | "manual-confirm"`.

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

## Feature Map

### `caddy-authcrunch-cockpit-tutorial`

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
  - Network and volume Quadlet support (completed: `85ec53c`)
  - Bundle file support with `${FILES_DIR}` token substitution (completed)
  - Container, network, volume rendering and sync (completed)
  - Quadlet `.build` support (completed)
- Suggested validation:
  - `first-boot-provision validate` on the tutorial config.toml
  - NixOS VM test importing the tutorial bundle and verifying rendered Quadlet files
  - Manual verification with a real Entra tenant (cannot be automated)
- Delivered in: `docs/src/tutorials/oidc-device-management.md` and
  `example/caddy-oidc/`

### `nixstasis-client`

- Status: planned
- Overview: Implement the Nixstasis enrollment client that registers the device with the
  Nixstasis management server, establishes reverse tunnels, and manages short-lived SSH
  credentials.
- Requirements:
  - Device identifies itself via eth0 MAC address
  - Server checks MAC against approved inventory
  - Approved devices receive and persist a registration key on `/data`
  - Client establishes reverse tunnel for remote SSH sessions
  - Credential rotation for the registration key
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
  - Reverse tunnel enables remote SSH access
  - NixOS VM test covers enrollment and tunnel lifecycle
- Risks and tradeoffs:
  - Depends on Nixstasis server API being stable and documented
  - Tunnel reliability on unstable WAN connections
- Dependencies: None (can start independently)
- Suggested validation:
  - NixOS VM test with mock Nixstasis server
  - Integration test with real Nixstasis instance
- Suggested first workflow command: `/start-feature nixstasis-client`

### `hawkbit-updates`

- Status: planned
- Overview: Configure the `rauc-hawkbit-updater` service for server-push OTA updates,
  replacing the simple HTTP polling model for fleet-scale deployments.
- Requirements:
  - Define hawkBit server configuration and credential provisioning
  - Create systemd unit for `rauc-hawkbit-updater`
  - Integrate with existing RAUC slot management
  - Add `config.toml` support for hawkBit server URL and credentials
- Constraints:
  - Must coexist with polling mode (operator chooses one)
  - Must not break existing `os-upgrade.service` behavior
  - Credentials must not be embedded in the base image
- Non-goals:
  - Running a hawkBit server (server-side concern)
  - Delta updates
- Success criteria:
  - Device registers with hawkBit server and receives push updates
  - RAUC install and slot management work identically to polling mode
  - NixOS VM test with mock hawkBit server
- Risks and tradeoffs:
  - hawkBit server availability becomes a deployment dependency
  - Additional credential management complexity
- Dependencies: None
- Suggested validation: NixOS VM test with mock hawkBit DDI API
- Suggested first workflow command: `/start-feature hawkbit-updates`

### `rauc-production-keyring-policy`

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
- Dependencies: RAUC module options from provisioning API service foundation
- Suggested validation: Nix evaluation tests for both fail-closed and dev opt-in modes
- Suggested first workflow command: `/start-feature rauc-production-keyring-policy`

### `provisioning-api-privilege-separation`

- Status: planned
- Overview: Split the network-facing provisioning API process from privileged host
  mutation helpers. The web process should run unprivileged and call a narrow,
  auditable helper for config promotion, service activation, firewall changes, and
  socket rebinding.
- Requirements:
  - Run the Litestar/uvicorn service as an unprivileged user
  - Define a minimal privileged helper interface for apply/recover/activate actions
  - Preserve single-flight apply semantics and job progress reporting
  - Preserve first-boot bootstrap behavior and SSH-signed reapply behavior
  - Ensure helper inputs are validated and scoped to `/data/config`
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
  - Helper boundary adds implementation and test complexity
  - Progress reporting may need a simple IPC contract
- Dependencies: Provisioning API foundation
- Suggested validation: VM test proving unprivileged service can provision via helper
- Suggested first workflow command: `/start-feature provisioning-api-privilege-separation`

### `provisioning-api-live-schema-contract`

- Status: planned
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
- Dependencies: Provisioning API foundation
- Suggested validation: Python tests against `/schema/openapi.json`
- Suggested first workflow command: `/start-feature provisioning-api-live-schema-contract`

### `typed-partial-provisioning-api`

- Status: planned
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
- Dependencies: Provisioning API foundation, live schema contract
- Suggested validation: Python tests for typed patch-to-full-state conversion plus VM
  tests for at least one user and one container partial update
- Suggested first workflow command: `/start-feature typed-partial-provisioning-api`

### `boot-ui-htmx`

- Status: planned
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
- Dependencies: Provisioning API foundation
- Suggested validation: Python route tests and manual browser test in VM
- Suggested first workflow command: `/start-feature boot-ui-htmx`

### `watchdog-enforcement`

- Status: deferred
- Overview: Enable hardware watchdog enforcement with `RuntimeWatchdogSec=30s` and
  `RebootWatchdogSec=10min` on Rock64.
- Requirements:
  - Complete Rock64 boot-reliability validation
  - Enable systemd manager watchdog settings
  - Verify watchdog-triggered reboots feed into boot-count rollback
- Constraints:
  - Must not cause false-positive reboot loops during normal operation
  - Must be validated on physical hardware before enabling
- Non-goals: Software-only watchdog
- Success criteria:
  - Watchdog reboots device within 30s of systemd hang
  - 3 consecutive watchdog reboots trigger automatic slot rollback
  - No false triggers during normal 72-hour soak test
- Risks and tradeoffs:
  - Aggressive timeout may cause false triggers on slow boots
  - Cannot be fully validated in QEMU
- Dependencies: Physical hardware availability for soak testing
- Suggested validation: 72-hour soak test on physical Rock64
- Suggested first workflow command: `/start-feature watchdog-enforcement`

### `usb-wifi`

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

### `config-reapply-improvements`

- Status: planned
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
- Suggested first workflow command: `/start-feature config-reapply-improvements`
