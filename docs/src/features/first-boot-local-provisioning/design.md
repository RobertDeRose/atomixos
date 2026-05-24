# Feature: first-boot-local-provisioning

## Overview

### Why

The current image and first-boot flow still reflect a development-oriented model: first boot can commit the slot before
production access credentials and application stack configuration exist, and provisioning is split across ad hoc files
manually copied into `/data/config/` after boot. This makes fresh installs, reprovisioning, and future Nixstasis
integration less coherent than they need to be.

This change defines a single local first-boot provisioning contract based on `config.toml`, so a freshly flashed or
reprovisioned device can acquire its managed operator users and Quadlet-managed application stack from a well-defined
source order without baking per-device secrets into the base image.

### What Changes

- Add a first-boot local provisioning flow that discovers a single `config.toml` seed from `/boot`, then USB mass
  storage, then a local bootstrap web console
- Define a bounded `config.toml` schema for provisioning managed users, explicit activation requirements, and structured
  Quadlet unit definitions
- Persist the imported provisioning state under `/data/config/`, including the source `config.toml` and rendered
  Quadlet units
- Distinguish initial fresh-flash provisioning from reprovisioning using `boot-b absent` as the discriminator so
  `/boot/config.toml` is a day-0 seed source only
- Redefine the first-boot path so production slot confirmation happens after provisioning import and validation rather
  than unconditionally after Linux boots
- Introduce a constrained local bootstrap web console that can upload or paste an existing `config.toml` when no seed file
  is found

### Capabilities

### New Capabilities

- `first-boot-local-provisioning`: Source discovery, import, validation, reprovisioning behavior, and bootstrap UI for
  local provisioning from `config.toml`

### Modified Capabilities

- `partition-layout`: Clarify that provisioned operator configuration persists under `/data/config/`, and that
  reprovisioning is driven by wiping `/data` while preserving the slot layout
- `update-confirmation`: Change the first-boot contract so production slot confirmation depends on successful local
  provisioning and explicit health requirements rather than unconditional first-boot commit

### Impact

- **Affected code**: `first-boot.service`, `scripts/first-boot.sh`, provisioning tasks/scripts, bootstrap web
  management path, and the runtime consumers of `/data/config/`
- **Affected storage layout**: `/data/config/` becomes the canonical home for imported `config.toml` and rendered
  Quadlet files
- **Affected operational workflows**: fresh flash, reprovisioning, bench setup, and future Nixstasis alignment
- **Security**: preserves the current no-secrets-in-image stance while making first-boot bootstrap behavior an explicit
  part of the device trust model

## Design

### Context

The current first-boot path is intentionally permissive: it commits the provisioned slot before production credentials,
application stack configuration, and health requirements necessarily exist. That was a pragmatic development step, but
it leaves production provisioning split across ad hoc files copied into `/data/config/` after boot and does not align
cleanly with the later Nixstasis direction.

The current first-boot-local-provisioning work converged on a bounded local provisioning contract:

- a single `config.toml` artifact
- operator SSH keys as imported access material
- structured Quadlet definitions as the application runtime contract
- explicit health requirements in the same document
- `/data/config/` as the durable home of imported operator configuration

The platform already has a natural day-0 discriminator, but it is only visible in the initrd: the flashed image
contains only slot A, so `boot-b absent` before initrd `systemd-repart` runs means a fresh flash. By the time the
switched-root `first-boot.service` executes, initrd repartitioning has already created `boot-b`, `rootfs-b`, and
`/data`, so the fresh-flash vs reprovision distinction must be detected in initrd and persisted for later consumption.

### Goals / Non-Goals

**Goals:**

- Define a single local provisioning contract for fresh flash and reprovisioning
- Keep the base image generic and free of per-device secrets
- Persist all imported provisioning state under `/data/config/`
- Use structured TOML to describe Quadlet units without raw multiline blobs or arbitrary output filenames
- Make first-boot production slot confirmation depend on provisioning import and validation
- Keep the bootstrap UI constrained to provisioning upload/generation rather than general management
- Preserve a future path where Nixstasis delivers the same logical payload remotely

**Non-Goals:**

- Implement remote Nixstasis provisioning in this change
- Introduce a generic provisioning engine such as cloud-init
- Make compose the device runtime contract
- Turn the bootstrap web console into a long-lived management surface
- Solve every future application stack abstraction beyond the bounded `config.toml` contract

### Decisions

### 1. Use a single config.toml provisioning contract

**Decision:** Local provisioning is driven by a single `config.toml` contract. The importer and bootstrap path may also
accept a supported archive bundle that carries that same `config.toml` plus optional `files/` payloads.

**Rationale:** The device needs a narrow contract, not a generic provisioning engine. Keeping one logical contract makes
fresh flash, USB reprovisioning, bootstrap upload, and eventual Nixstasis delivery easier to reason about, while the
optional archive wrapper gives the importer a safe way to carry auxiliary files.

**Alternatives considered:**

- **Cloud-init / NoCloud**: rejected as too broad and too open-ended for an appliance-oriented provisioning boundary
- **Multiple independent files under `/data/config/`**: rejected because it encourages drift and weakens validation
- **Compose file as the primary artifact**: rejected because it does not cover credentials or health expectations and is
  not the preferred runtime primitive

### 2. Treat /boot as a day-0 seed source only

**Decision:** Fresh-flash detection happens in initrd before `systemd-repart` creates slot B. Initrd persists a marker
that the switched-root provisioning path consumes later. First boot searches provisioning sources in this order on a
fresh flash: `/boot/config.toml`, then USB, then bootstrap web console. Reprovisioning skips `/boot` entirely.

**Rationale:** `/boot` is convenient on a freshly flashed device because only slot A exists and the operator can place a
seed file alongside the flashed image. But replaying `/boot/config.toml` on every later reprovision would make stale
seed material unexpectedly authoritative. Using `boot-b absent` as the discriminator still gives the desired behavior,
but the check must happen in initrd where that condition is actually true.

**Alternatives considered:**

- **Always search `/boot` first**: rejected because stale seeds could silently replay after `/data` is wiped
- **USB first always**: rejected because it makes fresh flash more cumbersome than necessary
- **Sentinel file to detect fresh flash**: rejected because `boot-b absent` is simpler and based on the actual disk
  layout rather than mutable state

### 3. Represent Quadlet as structured TOML, not raw embedded blobs

**Decision:** `config.toml` uses the canonical shape `containers.container.<name>.<section>`, with `[containers.container.<name>]`
declaring `privileged = true|false` and the OS owning the rootful vs rootless runtime details.

**Rationale:** This preserves the Quadlet runtime model while keeping the provisioning artifact structured and
validatable. The device can deterministically derive the rendered filename, active path, and runtime mode from the
container name plus its privilege setting. Arrays in TOML cleanly map to repeated Quadlet directives.

**Alternatives considered:**

- **`content = """..."""` raw Quadlet blobs**: rejected because multiline embedded INI text is harder to validate and less
  appliance-friendly
- **Generic file-write envelope**: rejected because it reintroduces arbitrary paths and permissions into the contract
- **Compose as canonical config**: rejected because the device runtime should stay systemd + podman + Quadlet oriented

### 4. Keep health requirements explicit in the provisioning artifact

**Decision:** Health expectations are explicitly declared in `config.toml` rather than inferred from every rendered
Quadlet unit.

**Rationale:** Not every declared unit is necessarily health-critical, and implicit inference creates ambiguity for
future helper units, one-shot setup units, or optional services. Explicit health requirements make the first-boot and
update confirmation paths testable and predictable.

**Alternatives considered:**

- **Infer health targets from all declared units**: rejected because it couples runtime shape too tightly to health
  policy and makes optional/helper units awkward

### 5. Use /data/config as the canonical persisted provisioning boundary

**Decision:** All imported provisioning-derived operator configuration lives under `/data/config/`, including the source
`config.toml`, admin access material, and rendered Quadlet files.

**Rationale:** This keeps the purpose of `/data` legible: `/data/config` for operator/provisioner state, `/data/logs`
for diagnostics, `/data/containers` for runtime container state, and `/data/rauc` for lifecycle/update state.

**Alternatives considered:**

- **Scatter files across `/data`**: rejected because it weakens the reprovision boundary and makes imported state harder
  to reason about
- **Keep Quadlet units outside `/data/config/`**: rejected because they are provisioned operator intent, not transient
  runtime state

### 5a. Sync rendered Quadlet units into the active Quadlet paths at boot

**Decision:** Provisioning renders canonical Quadlet files under `/data/config/quadlet/`, then a dedicated boot-time
sync path copies rootful units into `/etc/containers/systemd/` and rootless app units into the managed app user's
Quadlet path, reloads systemd, and starts rendered services.

**Rationale:** `/data/config/quadlet/` remains the durable operator-intent boundary, while the standard rootful and
rootless Quadlet discovery paths are still what the running system consumes. This keeps imported configuration
persistent without treating the active runtime paths as the source of truth.

**Alternatives considered:**

- **Write only to `/etc/containers/systemd/`**: rejected because it hides provisioned state outside the canonical
  `/data/config/` persistence boundary
- **Invent a custom generator input path**: rejected because the standard system path already exists and keeps the change
  smaller

### 6. Make production first-boot commit provisioning-aware

**Decision:** Production first boot should import and validate provisioning state before the slot is marked good.

**Rationale:** A device that merely boots Linux but has no valid admin credentials or application stack is not actually
ready for production use. This change redefines the production first-boot path from "Linux came up" to "minimum
provisioned state exists and is coherent."

Imported SSH keys and rendered Quadlet state live under `/data/config/`, and both can be consumed in the same boot.
That keeps the first-boot flow smaller and avoids introducing an extra reboot boundary before the device becomes
debuggable.

**Alternatives considered:**

- **Keep unconditional first-boot commit forever**: rejected because it bakes a development convenience into the
  production lifecycle contract
- **Require remote phone-home before commit**: rejected because local provisioning and confirmation should not depend on
  external availability

### 7. Narrow the bootstrap endpoint after provisioning

**Decision:** Before initial provisioning completes, the bootstrap web console listens on WAN and LAN interfaces. After
the first valid config is applied, LAN settings rebind the systemd socket to the configured LAN gateway address and port
`8080`; subsequent recovery and reprovisioning use authenticated API calls on the LAN endpoint only.

**Rationale:** Fresh devices may not have a known LAN address yet, so day-0 provisioning must be reachable on either
interface. Once the operator-provided LAN config is active, narrowing the socket to the LAN gateway address removes WAN
exposure from the long-lived recovery surface.

**Alternatives considered:**

- **Always bind only on LAN**: rejected because it makes first provisioning brittle before LAN settings are known
- **Require operators to open the firewall manually**: rejected because it makes the fallback path brittle during
  unprovisioned boot

### 7a. Applied configs should be shown and downloadable

**Decision:** When the bootstrap web console applies an uploaded or pasted `config.toml`, the UI should show the final
applied `config.toml` back to the operator and offer a direct download action for that exact artifact.

**Rationale:** The applied file is the actual operator-facing provisioning contract. Showing the final TOML immediately
after apply makes the bootstrap flow easier to audit, makes the state reusable for later devices or reprovisioning, and
avoids treating the form submission as a write-only UX.

**Alternatives considered:**

- **Apply silently and show only success/failure**: rejected because it hides the final contract the device actually
  accepted
- **Offer download only as an optional later enhancement**: rejected because the applied artifact is useful immediately
  in the same provisioning session

### Risks / Trade-offs

- **\[Risk\] Bootstrap UI becomes a second management plane** -> Keep it narrowly scoped to upload/paste/apply during
  unprovisioned state only
- **\[Risk\] Structured TOML diverges from raw Quadlet capabilities** -> Start with a bounded supported subset and render
  deterministically; expand only when real needs appear
- **\[Risk\] Reprovisioning may surprise operators by ignoring `/boot/config.toml`** -> Document the fresh-flash vs
  reprovision distinction clearly and prefer USB/web for reprovision workflows
- **\[Risk\] Existing first-boot assumptions in docs/tests drift from the new contract** -> Update specs, docs, and tests
  together as part of the implementation change
- **\[Trade-off\] Operators cannot paste raw Quadlet files verbatim** -> Accept the translation cost in exchange for a
  structured, validatable provisioning contract

### Migration Plan

1. Introduce initrd fresh-flash detection and persist the result for the switched-root provisioning path.
2. Introduce the new `config.toml` provisioning schema and source-order logic behind the first-boot provisioning path.
3. Persist imported state under `/data/config/`, render the Quadlet files there, and sync them into the active rootful
   and rootless Quadlet paths.
4. Update first-boot validation and confirmation behavior so production slot commit depends on successful provisioning
   import.
5. Add bootstrap UI support as the final fallback when no local seed file exists, then rebind to the LAN bootstrap
   address after provisioning.
6. Update docs and provisioning workflows to describe initrd fresh-flash detection, `/boot` initial seeding, USB
   reprovisioning, and `/data` wipe as the reprovision reset boundary.

Rollback remains straightforward during development: remove the new provisioning-aware commit gate and fall back to the
current unconditional first-boot path. Operationally, reprovisioning remains `wipe /data` plus reboot, after which the
device searches USB seed sources first and then falls back to the local bootstrap console without replaying
`/boot/config.toml`.

### Open Questions

- What exact subset of Quadlet sections and directives should the first implementation support?

## Requirements

### first-boot-local-provisioning

#### ADDED Requirements

### Requirement: First boot discovers a local provisioning seed in priority order

On an unprovisioned device, the provisioning flow SHALL search for a `config.toml` seed in a fixed priority order. The
system SHALL detect the fresh-flash case in initrd before `systemd-repart` creates slot B. On a fresh flash where
`boot-b` is absent at that stage, the system SHALL search `/boot/config.toml` first, then an attached USB mass storage
device containing `config.toml`, and finally fall back to a local bootstrap web console if no seed is found.

#### Scenario: Fresh flash uses boot partition seed first

- **WHEN** the device boots for the first time after a fresh flash and initrd detects that `boot-b` is absent before
  repartitioning
- **THEN** the provisioning flow checks `/boot/config.toml` before searching removable USB storage or starting the
  bootstrap web console

#### Scenario: USB seed is used when no boot seed exists

- **WHEN** the device is unprovisioned, `boot-b` is absent, and `/boot/config.toml` is missing
- **THEN** the provisioning flow searches attached USB mass storage for `config.toml` before starting the bootstrap web
  console

#### Scenario: Bootstrap console starts when no seed is found

- **WHEN** the device is unprovisioned and no `config.toml` is found on either `/boot` or attached USB mass storage
- **THEN** the device starts a local bootstrap web console for interactive provisioning

### Requirement: Reprovisioning skips boot partition seed replay

If the device is reprovisioned by wiping `/data` after the slot layout already exists, the provisioning flow SHALL
distinguish that state from a fresh flash by using the initrd-detected fresh-flash marker. When the marker indicates
that slot B already existed before repartitioning, `/boot/config.toml` SHALL NOT be used as a provisioning seed, and
reprovisioning SHALL use USB seed discovery followed by the bootstrap web console.

#### Scenario: Reprovisioned device ignores boot partition seed

- **WHEN** the device boots with `/data` empty after a reprovision reset and the initrd fresh-flash marker indicates
  that slot B already existed
- **THEN** the provisioning flow skips `/boot/config.toml` and searches USB mass storage before starting the bootstrap
  web console

#### Scenario: Wiping /data returns the device to provisioning mode

- **WHEN** `/data` is wiped or reformatted on a device whose slot layout already includes `boot-b`
- **THEN** the next boot re-enters the local provisioning flow rather than treating the device as already provisioned

### Requirement: config.toml defines bounded provisioning data

The local provisioning artifact SHALL be a single `config.toml` file containing only the bounded appliance provisioning
contract: managed users, provisioned LAN and WAN firewall inbound policy, optional LAN/NTP settings, optional OS
upgrade settings, explicit activation requirements, and structured Quadlet definitions. The accepted structure SHALL be
defined by a machine-readable schema that the import path validates before semantic normalization.

#### Scenario: Minimum valid config.toml includes admin access and stack definition

- **WHEN** a `config.toml` file is accepted for import
- **THEN** it includes at least one admin user SSH key, optional `[network.firewall.inbound]` tables, at least one
  Quadlet-defined application or service unit, and explicit activation requirements

### Requirement: Provisioning renders firewall and LAN runtime state

The device SHALL render accepted provisioning input into JSON runtime state under `/data/config/`. Firewall inbound state
SHALL be written to `/data/config/firewall-inbound.json` as optional `wan` and `lan` objects, each containing optional
`tcp` and `udp` arrays of integer ports in `1..65535`. If the `lan` object is omitted or contains no ports, LAN remains
open by default. If the `lan` object contains any ports, those ports SHALL be appended to the platform-required LAN
ports. LAN state SHALL be written to `/data/config/lan-settings.json` with the validated gateway CIDR, gateway IP,
subnet CIDR, netmask, DHCP range, DNS domain, hostname pattern, and gateway aliases. Optional OS upgrade state SHALL be
written to `/data/config/os-upgrade.json` when `[os_upgrade]` is present.

#### Scenario: Firewall inbound config is bounded

- **WHEN** provisioning imports `[network.firewall.inbound.wan]` or `[network.firewall.inbound.lan]` with TCP or UDP ports
- **THEN** the persisted firewall JSON contains only normalized integer port arrays under those scopes
- **AND** `provisioned-firewall-inbound.service` applies those ports to the matching interface rules for WAN and LAN

#### Scenario: LAN range excludes gateway

- **WHEN** provisioning imports `[network.dnsmasq]` with a gateway CIDR and DHCP range
- **THEN** the DHCP range is rejected unless it is inside the gateway `/24`, ordered, and excludes the gateway IP

### Requirement: config.toml expresses containers as structured TOML

The `config.toml` format SHALL represent Quadlet units as structured TOML tables rather than raw embedded multiline
Quadlet blobs. The canonical identity shape SHALL be `containers.container.<name>.<section>`, with a required
`[containers.container.<name>]` table that declares `privileged = true|false`. The device SHALL derive the rendered filename,
active path, and runtime mode from the container name plus that privilege flag.

#### Scenario: Structured Quadlet tables map to rendered unit files

- **WHEN** the provisioning flow reads `[containers.container.traefik.Container]`
- **THEN** it treats that table as the `Container` section of the rendered `traefik.container` Quadlet unit under the
  canonical `/data/config/quadlet/` path

#### Scenario: TOML arrays render to repeated Quadlet directives

- **WHEN** a structured Quadlet table contains an array value such as `Network = ["frontend", "backend"]`
- **THEN** the rendered Quadlet unit contains repeated directives for that key rather than a single joined value

### Requirement: Imported provisioning state persists under /data/config

All persisted provisioning-derived configuration SHALL live under `/data/config/`. This SHALL include the imported
`config.toml`, the admin SSH authorized key material, and the rendered Quadlet unit files.

#### Scenario: Imported provisioning state is stored under /data/config

- **WHEN** the provisioning flow successfully imports a `config.toml` seed
- **THEN** the resulting durable operator configuration is written under `/data/config/`

### Requirement: Newly imported provisioning is usable without an extra reboot

When a new `config.toml` is imported on an unprovisioned boot, the device SHALL continue first boot without requiring an
extra reboot before relying on the imported SSH authorized keys or other persisted provisioning-derived runtime state.

#### Scenario: Imported config is usable in the same boot

- **WHEN** the device imports a new `config.toml` from `/boot`, USB, or the bootstrap web console
- **THEN** it applies the imported SSH keys and runtime configuration during that same boot

### Requirement: Rendered Quadlet configuration is activated through the standard system path

Rendered Quadlet files SHALL remain canonically stored under `/data/config/quadlet/`, and the boot process SHALL sync
them into the active Quadlet path for their runtime mode before starting provisioned services. Rootful units SHALL sync
under `/etc/containers/systemd/`, while rootless application units SHALL sync under the managed app user's Quadlet path.

#### Scenario: Imported Quadlet files are synced into the active system path

- **WHEN** provisioning has rendered Quadlet files under `/data/config/quadlet/`
- **THEN** the system syncs rootful and rootless units into their respective active Quadlet paths, reloads systemd, and
  starts the rendered services from those active paths

### Requirement: First boot blocks on required runtime apply steps

The first-boot completion gate SHALL require a discovered `config.toml` to import and validate successfully, then apply
the rendered runtime state before committing the RAUC slot. `lan-gateway-apply.service` and
`provisioned-firewall-inbound.service` failures SHALL prevent the completion sentinel and RAUC `mark-good`. Quadlet sync
failure SHALL be fatal when `/data/config/health-required.json` names required provisioned units.

#### Scenario: Runtime apply failure prevents slot commit

- **WHEN** a discovered `config.toml` imports and validates successfully
- **AND** LAN gateway apply or provisioned firewall apply fails
- **THEN** first boot does not write the completion sentinel
- **AND** the RAUC slot is not marked good

#### Scenario: Required Quadlet failure prevents slot commit

- **WHEN** a discovered `config.toml` imports and validates successfully
- **AND** Quadlet sync fails while health requirements name provisioned units
- **THEN** first boot does not write the completion sentinel
- **AND** the RAUC slot is not marked good

### Requirement: Quadlet runtime constraints are explicit

Provisioned containers SHALL be rendered into canonical Quadlet files before activation. Rootful containers require
`privileged = true` and SHALL be forced to `Network=host`. Rootless containers SHALL run as the managed app user, use
`Network=pasta`, and have non-loopback published ports rewritten to `127.0.0.1`. Runtime metadata SHALL be persisted to
`/data/config/quadlet-runtime.json`.

#### Scenario: Rootless published ports bind to loopback

- **WHEN** a rootless provisioned container declares `PublishPort = ["10080:80"]`
- **THEN** the rendered Quadlet contains `PublishPort=127.0.0.1:10080:80`

#### Scenario: Privileged containers use host networking

- **WHEN** a provisioned container declares `privileged = true`
- **THEN** the rendered Quadlet contains `Network=host`

### Requirement: Bootstrap web console supports config upload

When no provisioning seed file is found, the device SHALL start a constrained local bootstrap web console. The console
SHALL support uploading an existing `config.toml` or supported config bundle.

#### Scenario: Applied config is shown back to the operator after apply

- **WHEN** an operator uploads or pastes a valid `config.toml`
- **THEN** the bootstrap UI shows the final applied `config.toml` content back to the operator

#### Scenario: Applied config can be downloaded after apply

- **WHEN** an operator uploads or pastes a valid `config.toml`
- **THEN** the bootstrap UI offers a direct download for that final applied `config.toml`

### Requirement: Bootstrap endpoint supports programmatic config import

The bootstrap service SHALL expose a constrained local API endpoint that accepts a complete `config.toml` payload or a
supported config bundle for programmatic local import using the same validation and persistence path as the web console.
The programmatic endpoint SHALL be `POST /api/config` and return a JSON async job response for accepted submissions, or
a JSON validation-error response for rejected submissions. First-boot programmatic clients SHALL NOT require the Boot UI
CSRF token; provisioned reapply clients SHALL use SSH signature authentication.

#### Scenario: Programmatic upload returns an async job

- **WHEN** a local client POSTs `config.toml` to `/api/config`
- **THEN** the bootstrap service validates the payload and accepts an apply job
- **AND** the response is JSON containing `job_id`, initial `state`, and `job_url`

### Requirement: Bootstrap endpoint narrows after initial provisioning

Before initial provisioning completes, the bootstrap API socket SHALL be reachable on WAN and LAN interfaces so operators
can provision a device before LAN settings are known. After a valid provisioning config is applied, the service SHALL
rebind to the configured LAN gateway IP and remain available only from the LAN interface for authenticated local recovery
or reprovisioning. The first-boot web console SHALL be hidden after provisioning.

#### Scenario: Bootstrap console listens on WAN and LAN before provisioning

- **WHEN** the device starts the bootstrap web console
- **THEN** it is reachable on the bootstrap port from WAN and LAN interfaces until initial provisioning completes

#### Scenario: Bootstrap API remains available after provisioning

- **WHEN** a valid provisioning config has already been applied
- **THEN** the bootstrap API continues listening on the LAN bootstrap endpoint for authenticated recovery or
  reprovisioning
- **AND** the bootstrap API is no longer reachable from WAN

#### Scenario: Bootstrap console is hidden after provisioning

- **WHEN** a valid provisioning config has already been applied
- **THEN** the unauthenticated first-boot console is not served

#### Scenario: Existing config.toml can be uploaded through the bootstrap console

- **WHEN** an operator opens the bootstrap web console on an unprovisioned device
- **THEN** the console allows uploading an existing `config.toml` or supported config bundle for local import

#### Scenario: Programmatic client can upload config.toml directly

- **WHEN** a local client POSTs a complete `config.toml` payload or supported config bundle to the bootstrap API endpoint
- **THEN** the bootstrap service validates and imports it through the same path used by the web console upload flow

### partition-layout

#### MODIFIED Requirements

### Requirement: /data partition survives updates

The /data partition SHALL NOT be modified by RAUC updates or rootfs slot switches. It SHALL persist across all
updates and rollbacks. Provisioned operator configuration SHALL be stored under `/data/config/`, and wiping `/data`
SHALL reset the device to an unprovisioned state without removing the existing slot layout.

#### Scenario: Data survives an A/B slot switch

- **WHEN** a file is written to /data, then an update switches the active slot from A to B
- **THEN** the file is still present and unmodified on /data after the slot switch

#### Scenario: Wiping /data preserves slot layout but resets provisioning state

- **WHEN** `/data` is reformatted on a device whose `boot-b` and `rootfs-b` partitions already exist
- **THEN** the device retains its slot layout but re-enters the unprovisioned first-boot provisioning flow on the next
  boot

### update-confirmation

#### Update Confirmation Modified Requirements

### Requirement: Manifest-driven container health checks

If `/data/config/config.toml` exists, the confirmation service SHALL treat the explicit health requirements imported
from that provisioning artifact as the source of truth for required application units. The confirmation service SHALL
verify that each required container or service reaches its expected healthy running state before the slot can be
committed. If no valid provisioning state exists on a production first boot, the slot SHALL remain uncommitted.

#### Scenario: Provisioned health requirements define required units

- **WHEN** the confirmation service runs on a provisioned device with a valid imported `config.toml`
- **THEN** it reads the explicit health requirements derived from that provisioning state to determine which units must
  be healthy before committing the slot

#### Scenario: Missing provisioning state blocks production first-boot commit

- **WHEN** the device is in the production first-boot path and no valid local provisioning state has been imported
- **THEN** the slot remains uncommitted rather than being marked good unconditionally

## Source Metadata

```yaml
schema: spec-driven
created: 2026-04-27
```

## Source

Converted from `openspec/changes/first-boot-local-provisioning/` during the OpenSpec-to-feature-spec migration.
