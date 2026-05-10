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
- `quadlet-runtime.json` tracks all rendered units (containers, networks, volumes) with
  mode (rootful/rootless) for sync-quadlet
- Network and volume Quadlet units are always rootful
- `${CONFIG_DIR}` and `${FILES_DIR}` tokens in Quadlet values are substituted at render
  time to `/data/config` and `/data/config/files` respectively
- Bundle imports support `files/` directory for operator payload files
- Re-apply uses authentication, not a reset token
- Full `/data` wipe is separate from config re-apply

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

## Resolved Questions

- **Cockpit-ws authentication boundary**: Resolved by placing Cockpit behind
  Caddy/AuthCrunch and running cockpit-ws with `--local-session`. Caddy is the
  only public authentication and authorization boundary; `/cockpit/*` is
  restricted to `authp/admin`.

## Feature Map

### `caddy-authcrunch-cockpit-tutorial`

- Status: in-progress
- Overview: Create a comprehensive tutorial section in the documentation that provides a
  fully working `config.toml` bundle deploying Caddy with the AuthCrunch plugin for
  Microsoft Entra OIDC authentication, JWT token generation with OIDC group-to-role
  mapping, and Cockpit-ws for container management. The tutorial demonstrates the full
  power of the config.toml provisioning system including containers, networks, volumes,
  and bundle files.
- Requirements:
  - Working `config.toml` with all required sections (admin, firewall, health, containers)
  - AuthCrunch container (`ghcr.io/authcrunch/authcrunch`) as rootful with host networking
  - Caddyfile configuring Microsoft Entra OIDC provider, authentication portal, and
    authorization policies
  - OIDC group mapping to local roles: `authp/admin` (sudoless admin) and `authp/user`
    (generic user) based on Entra security group membership
  - JWT token generation with configurable lifetime and signing key
  - Cockpit-ws container (`quay.io/cockpit/ws`) for device/container management, built
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
  - SAML or non-Entra OIDC providers (tutorial focuses on Entra)
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
  - Quadlet `.build` support (new: required for custom cockpit-ws image)
- Suggested validation:
  - `first-boot-provision validate` on the tutorial config.toml
  - NixOS VM test importing the tutorial bundle and verifying rendered Quadlet files
  - Manual verification with a real Entra tenant (cannot be automated)
- Suggested first workflow command: `/start-feature caddy-authcrunch-cockpit-tutorial`

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
