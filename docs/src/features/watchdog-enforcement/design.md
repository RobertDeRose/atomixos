<!-- workflow-migration:legacy-markdown-to-beads -->

# Design — Watchdog Enforcement

## Metadata

- Beads feature root: `atomixos-aua`
- Feature slug: `watchdog-enforcement`
- Design path: `docs/src/features/watchdog-enforcement/design.md`
- Implemented record: `docs/src/features/watchdog-enforcement/index.md`
- Base branch: `dev`
- Status: delivered

## Feature Summary

Finish opt-in systemd hardware watchdog enforcement without enabling it in release profiles by default. The onboard
RK3328 and external UCC2946 paths have passed physical Rock64 device, ownership, and timeout validation; the onboard
RK3328 path has also passed induced-reboot validation. External reset timing, rollback, and soak evidence are deferred
to the RAUC OTA validation campaign. Build-time configuration is owned by the separate Build
Configuration feature; runtime `config.toml` does not control watchdog policy.

## User Intent

Operators need hung devices to reboot and newly updated, still-unconfirmed slots to roll back after repeated failed
boots. They must not accept false-positive reboot loops or infer physical watchdog correctness from software-only VM
simulation.

The user made these specification decisions during review:

- Missing or unusable watchdog hardware fails open: normal boot continues with a warning and does not, by itself, fail
  update verification or trigger rollback.
- Watchdog enablement and timeout values belong to a reusable build-stage `build.toml`, not runtime `config.toml`.
- `30s` runtime and `10min` reboot timeouts are defaults when build settings are omitted.
- A bounded hardware spike must select a safe, repeatable systemd-hang injection method before destructive physical
  tests proceed.

## Goals

1. Preserve the existing opt-in `atomixos.watchdog.enableHardware` module boundary and default-disabled behavior.
2. Use `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min` as the default enabled policy.
3. Verify that enabled-but-unavailable hardware fails open with an observable warning.
4. Verify that watchdog resets on a newly updated, unconfirmed slot consume U-Boot boot attempts and cause fallback
   after three failed attempts.
5. Record physical Rock64 evidence for watchdog presence and reboot timing before release enablement; record rollback
   and 72-hour soak evidence during the RAUC OTA validation campaign.

## Non-Goals

- Runtime watchdog configuration through provisioning `config.toml`.
- A software-only watchdog replacement.
- Changing the RAUC slot layout or boot-count storage format unless physical validation reveals a defect.
- Claiming QEMU validation is equivalent to physical Rock64 watchdog validation.
- Enabling watchdog enforcement in release or deployment profiles before physical acceptance passes.
- Designing the generic `build.toml` parser, schema framework, or Nix invocation contract; those belong to Build
  Configuration.

## User-Facing Behavior

A supported image build can opt into hardware watchdog enforcement through the Build Configuration interface. Set
`watchdog.backend = "internal"` for the onboard RK3328 DesignWare device or `backend = "external"` for the example TI
UCC2946/I2C-expander path. Omitted watchdog timeout settings use `30s` and `10min`. Set
`watchdog.enable_hardware = false` to disable enforcement; the backend remains a required build-policy field but has no
runtime effect. Disabled builds retain current VM, development, and Rock64 behavior.

When enforcement is enabled but systemd cannot use a watchdog device, the system continues booting and emits a warning.
The absence does not independently fail update verification, mark a slot bad, or trigger rollback.

Release and deployment profiles remain disabled until the hardware checklist records successful presence and reboot
evidence. External reset timing, rollback, and soak evidence are tracked as deferred RAUC OTA validation work.

## Requirements

### Functional Requirements

- Use the canonical `atomixos.watchdog.enableHardware` NixOS option and the build-policy backend enum (`internal` or
  `external`).
- Render `RuntimeWatchdogSec` and `RebootWatchdogSec` only when hardware enforcement is enabled.
- Default enabled values to `30s` and `10min`.
- Consume build-stage watchdog settings supplied by the Build Configuration feature; do not read provisioning
  `config.toml`.
- Continue booting and emit a warning when enabled hardware is unavailable or unusable.
- Run `watchdog-boot-count` only on RAUC-enabled systems; disabled non-RAUC profiles must not install or run unrelated
  U-Boot boot-count integration.
- On physical Rock64, prove that a newly updated slot which repeatedly hangs before `os-verification` can call
  `rauc status mark-good` consumes `BOOT_*_LEFT` attempts and falls back after three failures.

### Quality Requirements

- Default-disabled profiles must not render active systemd manager watchdog settings.
- Normal operation must not enter false-positive reboot loops.
- Physical testing must preserve serial recovery and a known-good slot.
- Warning behavior for missing hardware must be observable and testable without making availability depend on the
  watchdog device.
- Physical evidence must distinguish compile-time `DW_WATCHDOG` support from runtime `dw_wdt` registration and
  `/dev/watchdog` availability.

### Compatibility and Migration Requirements

- Keep the established Nix option name `atomixos.watchdog.enableHardware`; do not introduce
  `atomixos.watchdog.enforceHardware`.
- Preserve the custom-backend, two-attempt `rauc-watchdog` VM simulation.
- Preserve the physical U-Boot ownership model: U-Boot decrements `BOOT_*_LEFT`; Linux observes the value and may reset
  it only by marking a slot good.
- Existing direct Nix module overrides remain an implementation/development interface. The supported operator-facing
  build contract and validation rules are defined by Build Configuration.

## Existing Context

`modules/watchdog.nix` already defines the canonical enable switch and timeout defaults, conditionally renders systemd
manager settings, and installs the boot-count helper. `nix/tests/watchdog-module.nix` evaluates disabled, enabled, and
custom values. `nix/tests/rauc-watchdog.nix` simulates rollback with a QEMU watchdog and custom file-backed counter.

The Rock64 kernel configuration includes DesignWare watchdog support. Physical validation now proves runtime
registration and device ownership for both the onboard and external paths, and an induced reset for the onboard path.
The hardware checklist still tracks external reset timing, rollback, and soak evidence separately.

The current boot-count service is imported by the base module even when RAUC is disabled. This coupling must be removed
while preserving the RAUC-enabled U-Boot and custom-backend paths.

## Proposed Design

### Configuration Ownership

Build Configuration (`build-configuration`) introduces and owns the build-stage `build.toml` contract. Its first
consumer is watchdog policy. It maps validated watchdog settings into the existing NixOS options before image,
squashfs, and RAUC bundle construction. Watchdog Enforcement does not introduce a parallel parser or runtime mutation
path.

### Systemd Watchdog Ownership

Systemd PID 1 remains the sole owner of hardware watchdog kicks. AtomixOS does not add a heartbeat daemon. On the
Rock64, build policy selects either the onboard RK3328 DesignWare watchdog or the external UCC2946 path. The
onboard path uses the kernel `dw_wdt` driver and `/dev/watchdog-internal`; the external path uses `gpio-wdt` over the
I2C GPIO expander at address `0x41` on bus 1 and `/dev/watchdog-external`. When enabled, manager settings use the
configured build values, defaulting to:

- `RuntimeWatchdogSec=30s`
- `RebootWatchdogSec=10min`

If systemd cannot acquire a usable watchdog, boot continues. The manager's diagnostic or a minimal explicit check must
produce a warning that identifies the unavailable enforcement. This condition alone does not alter
`os-verification.service` or RAUC slot state.

### Boot-Count Ownership

Physical Rock64 rollback remains U-Boot-owned. U-Boot selects a slot and decrements its remaining attempts before Linux
starts. `watchdog-boot-count` observes and logs that state; it does not decrement U-Boot variables.

The acceptance scenario is intentionally narrow: an update boots into a still-unconfirmed slot, the selected safe hang
method stops watchdog kicks before `os-verification` marks the slot good, and three watchdog-reset attempts exhaust the
slot counter. Hangs after a slot is already confirmed are not claimed to cause A/B rollback.

The custom QEMU backend remains a faster simulation: its helper decrements a two-attempt file-backed counter and changes
the simulated primary slot.

### Physical Validation Sequence

1. Complete Build Configuration and produce a watchdog-enabled test image.
2. In parallel:
   - confirm `dw_wdt` registration and `/dev/watchdog` availability;
   - run a bounded spike to select and document a recoverable hang-injection method.
3. Prepare a known-good fallback, install the physical-test update into the inactive slot, and use the spike-approved
   test-only fixture to keep that slot unconfirmed and stop kicks automatically before `mark-good`. Verify that reset
   starts within 35 seconds of confirmed kick cessation (the 30-second timeout plus 5 seconds of measurement and serial
   tolerance), capture serial reset evidence, and record one consumed boot attempt.
4. Execute the three-attempt, still-unconfirmed-slot rollback procedure.
5. Run the watchdog-enabled image under normal workload for 72 hours and record that no false reset occurred.

## Architecture Consistency

### Existing Patterns Reused

- NixOS options and systemd manager settings in `modules/watchdog.nix`.
- U-Boot RAUC bootmeth ownership of physical boot attempts.
- The existing custom-backend VM simulation for deterministic automated coverage.
- Build-time image policy rather than mutable runtime changes to the read-only base system.

### Invariants Preserved

- Hardware enforcement is disabled by default.
- Runtime provisioning state remains bounded to `config.toml` concerns and does not mutate immutable image policy.
- Missing watchdog hardware does not remove local recovery access.
- Only a newly updated, unconfirmed slot is expected to roll back through boot-attempt exhaustion.
- QEMU evidence is never presented as physical watchdog evidence.

### New Decisions Introduced

- Build Configuration is a blocking feature dependency and owns `build.toml`.
- Missing hardware has explicit fail-open semantics with warning-only observability.
- Non-RAUC profiles do not run or carry the watchdog boot-count integration.
- Physical hang-method selection is a bounded spike with safety prerequisites and exit criteria.

### Architecture Documentation Changes

`docs/src/architecture/update-rollback.md` must state the unconfirmed-slot boundary, U-Boot decrement ownership, and
fail-open missing-device behavior. `docs/src/unknowns.md` must distinguish compiled kernel support from physically
verified runtime availability.

## Operational Considerations

Physical tests can deliberately reset or strand a device. They require a sacrificial Rock64, attached serial console,
recovery media, a known-good slot, saved U-Boot environment state, and an operator able to restore the device. The hang
method spike must stop without destructive execution if those prerequisites are absent.

The selected method must be repeatable, stop watchdog kicks without corrupting persistent state, preserve a recovery
path, and produce identifiable serial evidence. It must define a test-only startup fixture that prevents the updated
slot from being marked good and triggers before `os-verification` can confirm it; that fixture must not enter a
production profile. The current Rock64 fixture, `run0 kill -STOP 1`, has now been physically validated and remains
board-specific rather than a general production command.

## Documentation Impact

| Documentation concern      | Exact page                                             | Create or update                 | Planned change                                                                           | Owning Beads task                                   |
|----------------------------|--------------------------------------------------------|----------------------------------|------------------------------------------------------------------------------------------|-----------------------------------------------------|
| Architecture               | `docs/src/architecture/update-rollback.md`             | Update                           | Clarify U-Boot ownership, unconfirmed-slot rollback, and fail-open behavior              | `atomixos-aua.8`                                    |
| Build usage                | `docs/src/building.md`                                 | Update after dependency delivery | Link the supported watchdog `build.toml` settings and defaults                           | `atomixos-mol-0ws` / `atomixos-aua.8`               |
| Hardware operations        | `docs/src/hardware-testing.md`                         | Update                           | Add the selected safe method, prerequisites, evidence fields, and ordered execution      | Hardware implementation children / `atomixos-aua.8` |
| Development validation     | `docs/src/testing.md`                                  | Update                           | Keep exact module and VM commands and distinguish their evidence limits                  | `atomixos-aua.8`                                    |
| Reference contract         | `docs/src/specs/watchdog.md`                           | Update                           | Record canonical options, defaults, fail-open behavior, and physical acceptance boundary | `atomixos-aua.8`                                    |
| Operational unknowns       | `docs/src/unknowns.md`                                 | Update                           | Separate compiled driver support from runtime hardware proof                             | `atomixos-aua.8`                                    |
| Roadmap                    | `docs/src/planned-features.md`                         | Update                           | Record Build Configuration dependency and current physical gates                         | `atomixos-aua.8`                                    |
| Feature navigation         | `docs/src/features/index.md` and `docs/src/SUMMARY.md` | Update at delivery               | Add the implemented record only after delivery                                           | `atomixos-aua.8`                                    |
| Implemented feature record | `docs/src/features/watchdog-enforcement/index.md`      | Create during close-out          | Preserve delivery, evidence, limitations, and audit history                              | `atomixos-aua.8`                                    |

No introduction page is needed; this feature changes build reference, architecture, testing, and operator procedures.

## Validation Strategy

### Automated

- `nix build "path:$PWD#checks.aarch64-linux.watchdog-module" --no-link`
- `nix build "path:$PWD#checks.aarch64-darwin.watchdog-module" --no-link`
- `mise run e2e:rauc-watchdog`
- Coverage that disabled non-RAUC profiles do not install or start `watchdog-boot-count`.
- Coverage that enabled missing-device behavior continues booting and emits a warning.
- Build Configuration's watchdog schema/default/integration checks.
- `uv run scripts/check-docs.py`
- Repository-wide `mise run check` before delivery.

Use the host-appropriate Nix output. Record remote-builder or hardware limitations rather than treating an unexecuted
check as evidence.

### Physical Rock64

- Confirmed onboard `dw_wdt` registration, the 16-cell TOP table, and `/dev/watchdog-internal` ownership.
- Confirmed the external UCC2946/PCA9536-compatible path, `/dev/watchdog-external` ownership, and configured timeout.
- Recorded an internal watchdog-triggered reset with a fresh serial U-Boot sequence and SSH recovery.
- Record three consumed attempts and fallback from a newly updated, unconfirmed slot.
- Record 72 hours under normal workload without an unexpected watchdog reset.

## Implementation Decomposition

Beads is authoritative for executable work. Delivered slices include the Build Configuration consumer, RAUC-only
boot-count integration, fail-open missing-device behavior, the bounded Rock64 hang fixture, both physical watchdog paths,
and the internal induced-reboot test. Remaining slices are:

1. Execute and record external watchdog reset timing.
2. Execute and record three-attempt rollback on an unconfirmed update slot.
3. Execute and record the 72-hour soak.

Physical evidence-only tasks need not create repository commits. Any defect found during execution becomes a separate
bounded implementation task with tests, documentation impact, and a commit. The remaining physical gates are external
reset timing, RAUC rollback, and the 72-hour soak.

## Dependencies and Parallelism

- Build Configuration (`atomixos-mol-0ws`) supplied the supported build interface used for physical acceptance.
- Device confirmation and hang-method selection are complete; the internal reboot test is complete.
- External reset timing and rollback remain part of the RAUC OTA campaign; rollback remains a prerequisite for the
  72-hour soak.
- Every implementation child remains traceable through Beads and the feature design.

## Rollout and Migration

No existing profile is automatically enabled. Build defaults remain disabled, so existing images and runtime
`config.toml` files retain behavior. Release-profile enablement is a later explicit decision after all physical evidence
is recorded.

## Risks and Tradeoffs

- Fail-open behavior preserves availability but can leave a misconfigured build without promised watchdog protection;
  warning observability is therefore required.
- A configurable build policy increases qualification combinations; Build Configuration owns validation and support
  boundaries.
- Physical testing is destructive and slow, especially the 72-hour soak.
- Keeping enforcement opt-in delays production coverage but avoids unsafe reboot loops.

## Rejected Alternatives

- Runtime `config.toml`: rejected because watchdog policy belongs to immutable image construction, not provisioning.
- Embedding a one-off watchdog build parser in this feature: rejected in favor of reusable Build Configuration.
- Fail-closed missing-device behavior: rejected by user decision; boot and update verification continue.
- Custom heartbeat daemon: rejected because systemd already owns hardware watchdog integration.
- Treating `kill -STOP 1` as a portable hang test: rejected; it is documented only as the validated fixture for the
  current Rock64 test image and requires serial/recovery prerequisites.

## Open Questions

None for specification readiness. The exact hang-injection mechanism is an implementation spike outcome, and the
supported `build.toml` schema and timeout validation policy are Build Configuration decisions.

## Deferred Decisions

- Enabling watchdog enforcement in release/deployment profiles.
- Supporting additional hardware watchdog devices beyond the validated Rock64 reference.
- Qualification policy for non-default timeout combinations, owned by Build Configuration.

## Planning Record

### Questions Asked and Answers

- Missing watchdog device: continue booting with a warning; do not affect update verification or rollback.
- Runtime versus build configuration: do not use provisioning `config.toml`; create reusable build-stage `build.toml`.
- Feature scope: Build Configuration is a separate prerequisite feature with watchdog as its first consumer.
- Physical hang method: resolve it through a bounded, recoverable Rock64 hardware spike.

### Assumptions

- A sacrificial Rock64, serial console, recovery media, and operator are available before physical execution.
- Build Configuration will define a reproducible way to map `build.toml` into Nix evaluation.

### Design Changes During Planning

- Reconciled stale proposed option names and implementation claims with the existing module.
- Narrowed rollback claims to newly updated, unconfirmed slots and corrected decrement semantics.
- Added explicit physical execution and soak ownership instead of treating instructions as evidence.
- Added fail-open missing-device semantics and RAUC-only boot-count service ownership.
- Replaced runtime provisioning configuration with the separate Build Configuration dependency.

### Source Material

- `docs/src/planned-features.md`
- `docs/src/specs/watchdog.md`
- `docs/src/architecture/update-rollback.md`
- `docs/src/hardware-testing.md`
- `docs/src/testing.md`
- `modules/watchdog.nix`
- `scripts/watchdog-boot-count.sh`
- `nix/tests/watchdog-module.nix`
- `nix/tests/rauc-watchdog.nix`
- Beads root `atomixos-aua` and its lifecycle/implementation graph
