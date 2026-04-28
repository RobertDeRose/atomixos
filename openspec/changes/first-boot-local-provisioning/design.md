# Design

## Context

The current first-boot path is intentionally permissive: it commits the provisioned slot before production credentials,
application stack configuration, and health requirements necessarily exist. That was a pragmatic development step, but
it leaves production provisioning split across ad hoc files copied into `/data/config/` after boot and does not align
cleanly with the later Nixstasis direction.

The provisioning idea captured in `provision_idea.md` converged on a bounded local first-boot provisioning contract:

- a single `config.toml` artifact
- admin SSH keys as imported access material
- structured Quadlet definitions as the application runtime contract
- explicit health requirements in the same document
- `/data/config/` as the durable home of imported operator configuration

The platform already has a natural day-0 discriminator, but it is only visible in the initrd: the flashed image
contains only slot A, so `boot-b absent` before initrd `systemd-repart` runs means a fresh flash. By the time the
switched-root `first-boot.service` executes, initrd repartitioning has already created `boot-b`, `rootfs-b`, and
`/data`, so the fresh-flash vs reprovision distinction must be detected in initrd and persisted for later consumption.

## Goals / Non-Goals

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

## Decisions

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

**Decision:** `config.toml` uses the canonical shape `container.<name>.<section>`, with `[container.<name>]`
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

### 7. Expose the bootstrap UI only on the LAN bootstrap address

**Decision:** The bootstrap web console binds to the LAN gateway address and port `172.20.30.1:8080`, and the firewall
explicitly allows that TCP port on the LAN interface only.

**Rationale:** The bootstrap UI is intended for local day-0 and reprovisioning workflows, not WAN exposure. Binding it
to the LAN address and allow-listing it only on the LAN interface keeps the surface constrained while still making the
fallback usable without extra manual firewall steps.

**Alternatives considered:**

- **Bind on all interfaces**: rejected because it would expose the bootstrap surface more broadly than intended
- **Require operators to open the firewall manually**: rejected because it makes the fallback path brittle during
  unprovisioned boot

## Risks / Trade-offs

- **[Risk] Bootstrap UI becomes a second management plane** -> Keep it narrowly scoped to upload/generate/apply during
  unprovisioned state only
- **[Risk] Structured TOML diverges from raw Quadlet capabilities** -> Start with a bounded supported subset and render
  deterministically; expand only when real needs appear
- **[Risk] Reprovisioning may surprise operators by ignoring `/boot/config.toml`** -> Document the fresh-flash vs
  reprovision distinction clearly and prefer USB/web for reprovision workflows
- **[Risk] Existing first-boot assumptions in docs/tests drift from the new contract** -> Update specs, docs, and tests
  together as part of the implementation change
- **[Trade-off] Operators cannot paste raw Quadlet files verbatim** -> Accept the translation cost in exchange for a
  structured, validatable provisioning contract

## Migration Plan

1. Introduce initrd fresh-flash detection and persist the result for the switched-root provisioning path.
2. Introduce the new `config.toml` provisioning schema and source-order logic behind the first-boot provisioning path.
3. Persist imported state under `/data/config/`, render the Quadlet files there, and sync them into the active rootful
   and rootless Quadlet paths.
4. Update first-boot validation and confirmation behavior so production slot commit depends on successful provisioning
   import.
5. Add bootstrap UI support as the final fallback when no local seed file exists, bound to the LAN bootstrap address.
6. Update docs and provisioning workflows to describe initrd fresh-flash detection, `/boot` initial seeding, USB
   reprovisioning, and `/data` wipe as the reprovision reset boundary.

Rollback remains straightforward during development: remove the new provisioning-aware commit gate and fall back to the
current unconditional first-boot path. Operationally, reprovisioning remains `wipe /data` plus reboot, after which the
device searches USB seed sources first and then falls back to the local bootstrap console without replaying
`/boot/config.toml`.

## Open Questions

- What exact subset of Quadlet sections and directives should the first implementation support?
- Should the bootstrap UI always offer the generated `config.toml` as a downloadable artifact, or is that optional UX?
