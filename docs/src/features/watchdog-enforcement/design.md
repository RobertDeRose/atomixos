<!-- workflow-migration:legacy-markdown-to-beads -->

# Feature: Watchdog Enforcement

## Metadata

- Beads feature root: `atomixos-aua`
- Feature slug: `watchdog-enforcement`
- Design path: `docs/src/features/watchdog-enforcement/design.md`
- Implemented record: `docs/src/features/watchdog-enforcement/index.md`
- Base branch: `dev`
- Status: in progress

## Feature Summary

Add opt-in systemd hardware watchdog enforcement while keeping release profiles disabled until physical Rock64 reboot,
rollback, and soak validation proves the policy safe.

## User Intent

Operators need hung devices to reboot and eventually roll back automatically, but must not accept false-positive reboot
loops or infer physical watchdog correctness from software-only VM simulation.

## User-Facing Behavior

Supported profiles can enable bounded runtime and reboot watchdog settings. Defaults remain disabled. VM tests preserve
rollback simulation, while Rock64 enablement remains blocked on device/driver, hang, boot-count, and soak evidence.

## Requirements

Enabled hardware must expose the expected watchdog device and render `RuntimeWatchdogSec=30s` and
`RebootWatchdogSec=10min`. Watchdog reboots must consume boot attempts and reach rollback after repeated failure without
breaking disabled development and VM profiles.

## Existing Context

The repository already has watchdog options, a boot-count script, U-Boot/RAUC rollback assumptions, and a QEMU watchdog
simulation. Hardware enforcement had been disabled after unstable Rock64 behavior and needed an explicit gated policy.

## Architecture Consistency

The design reuses systemd manager watchdog ownership and the existing boot-count/RAUC rollback chain. It keeps hardware
profile defaults conservative and separates VM simulation from physical acceptance evidence.

## Operational Considerations

Physical tests can deliberately crash or reboot a device and require serial recovery and a known-good slot. Operators
must verify driver/device availability, timing, three-failure rollback, and a 72-hour soak before release enablement.

## Validation Strategy

Use Nix evaluation/module assertions for defaults and rendered settings, retain the `rauc-watchdog` VM check, and execute
recorded physical hang, reboot timing, boot-count rollback, driver availability, and soak procedures on Rock64.

## Implementation Decomposition

Imported tasks cover policy decisions, option surface, Rock64 systemd settings, rollback integration, automated checks,
hardware procedures, docs, and close-out. Beads under `atomixos-aua` preserves three open physical-validation tasks.

## Dependencies and Parallelism

Module and VM validation can proceed independently of hardware execution. Build Configuration delivery owns the
reproducible `build.toml` path for producing a watchdog-enabled test image and blocks physical driver, hang, and first
reboot evidence. Physical driver, hang, rollback, and soak checks share the Rock64 target and must be sequenced from
recoverable smoke tests to prolonged enablement.

## Source

Seeded from `docs/src/planned-features.md` entry `watchdog-enforcement` and
aligned with the existing watchdog boot-count rollback design and RAUC update
confirmation flow.

## Overview

Enable Rock64 hardware watchdog enforcement so a hung systemd userspace reboots
automatically and repeated watchdog-triggered boots feed into the existing
boot-count rollback policy. The feature should make watchdog enforcement an
explicit, auditable platform behavior instead of relying only on passive boot
count recording.

This feature is safety-sensitive. The implementation must preserve developer and
VM workflows by keeping hardware enforcement opt-in. Production Rock64 images can
enable the policy only after physical validation evidence exists.

## Goals

1. Add NixOS configuration for systemd hardware watchdog enforcement on Rock64.
2. Use `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min` for the initial
   enforcement policy.
3. Feed watchdog-triggered reboots into the existing boot-count rollback path.
4. Keep enforcement disabled or explicitly simulated in QEMU where hardware
   watchdog behavior cannot be validated.
5. Document physical validation requirements before enabling enforcement in any
   release image or deployment profile.

## Non-Goals

- Implementing a software-only watchdog replacement.
- Changing the RAUC slot layout or boot-count storage format unless required by
  a verified watchdog integration bug.
- Claiming QEMU validation is equivalent to physical Rock64 watchdog validation.
- Enabling an aggressive policy that risks false-positive reboot loops without
  a hardware soak plan.

## Constraints

- Must not cause false-positive reboot loops during normal operation.
- Must be validated on physical Rock64 hardware before production enablement.
- Must preserve the existing A/B rollback behavior and boot-count recording.
- Must not block local recovery paths if watchdog enforcement is disabled.
- QEMU tests may validate configuration/evaluation and boot-count plumbing, but
  not real hardware watchdog expiry.

## Current Behavior

AtomixOS already records watchdog/boot-count related state and has VM coverage
for boot-count rollback behavior. Hardware watchdog enforcement itself remains
deferred; systemd is not yet configured to actively trigger hardware watchdog
reboots with the planned runtime and reboot watchdog timers.

## Proposed Design

### NixOS Option Surface

Add a narrow platform option for hardware watchdog enforcement, for example:

- `atomixos.watchdog.enforceHardware`
- `atomixos.watchdog.runtimeWatchdogSec`
- `atomixos.watchdog.rebootWatchdogSec`

Defaults must keep VM, development, and Rock64 images safe: hardware enforcement
is off unless explicitly enabled. Rock64 production profiles can opt in after
hardware validation. The option names and defaults should follow existing module
style if `modules/watchdog.nix` already exposes a watchdog namespace.

### Rock64 Enforcement

When explicitly enabled on Rock64, render systemd manager settings equivalent to:

- `RuntimeWatchdogSec=30s`
- `RebootWatchdogSec=10min`

The implementation should rely on systemd's hardware watchdog integration rather
than a custom userspace heartbeat daemon unless the Rock64 watchdog driver
requires additional setup.

### Boot-Count Rollback Integration

Watchdog-triggered reboots should be indistinguishable from other failed boots
for the existing boot-count rollback logic. The QEMU `rauc-watchdog` test uses a
custom RAUC backend and a two-attempt boot-count file to keep the VM fast and
deterministic. Physical U-Boot/Rock64 validation should use the real `BOOT_*_LEFT`
environment counter; the current documented target is three consecutive failed
boots before U-Boot falls back to the previous slot.

### VM And Hardware Validation Split

QEMU validation can cover:

- option evaluation
- rendered systemd manager configuration
- existing boot-count rollback behavior still passing
- disabled hardware enforcement in VM profiles unless explicitly overridden
- the simulated `rauc-watchdog` rollback path with its custom two-attempt counter

Physical Rock64 validation must cover:

- systemd hang causes reboot within the configured runtime watchdog window
- repeated watchdog reboots increment boot-count state
- rollback occurs after the configured consecutive failure threshold
- normal 72-hour soak does not trigger false watchdog reboots

## Documentation Impact

- `docs/src/planned-features.md`: update status and delivered behavior at closeout.
- `docs/src/architecture/update-rollback.md`: document watchdog-triggered rollback.
- `docs/src/hardware-testing.md`: add physical watchdog validation and soak steps.
- Beads root `atomixos-aua`: track validation gaps and close-out.
- Existing watchdog specs/docs under `docs/src/specs/` or module references, if present.

## Validation

- Nix evaluation test for watchdog option defaults and Rock64 enforcement settings.
- Existing `rauc-watchdog` VM check remains passing.
- Optional VM assertion that QEMU profiles do not enable unsupported hardware
  enforcement by default.
- Physical Rock64 test: systemd hang triggers reboot within 30 seconds.
- Physical Rock64 test: three consecutive watchdog reboots trigger automatic slot
  rollback.
- Physical Rock64 72-hour soak with enforcement enabled and no false triggers.

## Success Criteria

1. Rock64 can opt into systemd hardware watchdog enforcement.
2. A systemd hang reboots the device within 30 seconds on physical hardware.
3. Three consecutive watchdog reboots trigger automatic slot rollback.
4. Normal operation does not trigger false-positive reboots during a 72-hour soak.
5. VM checks continue to validate non-hardware boot-count rollback behavior.

## Risks And Tradeoffs

- Aggressive watchdog timing can cause reboot loops on slow or overloaded boots.
- Hardware-only validation means final production confidence depends on physical
  Rock64 test execution.
- Systemd watchdog settings may interact with kernel/driver availability; module
  configuration must fail safely if the watchdog device is unavailable.
- Making enforcement opt-in may delay production coverage, but avoids enabling an
  unsafe policy before hardware evidence exists.

## Resolved Decisions

- Hardware watchdog enforcement remains opt-in. This feature should add the
  module switch and validation/docs, not enable active enforcement by default.
- QEMU validation and physical Rock64 validation are intentionally separate. QEMU
  may validate rendered settings and simulated rollback; only hardware testing can
  prove watchdog expiry timing and false-positive behavior.
- Physical Rock64 rollback validation uses the U-Boot `BOOT_*_LEFT` behavior
  documented as three attempts. The existing VM test remains a faster custom-backend
  simulation with a two-attempt counter.

## Open Questions

1. Which physical test mechanism should simulate a systemd hang without risking
   persistent device lockout?
