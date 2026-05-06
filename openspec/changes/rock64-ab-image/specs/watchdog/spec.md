# Watchdog Spec

## ADDED Requirements

### Requirement: Hardware watchdog target is defined but deferred

The NixOS configuration SHALL keep RK3328 hardware watchdog manager settings disabled for the current release while
Rock64 boot reliability is validated. The deferred target settings are `RuntimeWatchdogSec=30s` and
`RebootWatchdogSec=10min`.

#### Scenario: Watchdog fires on system hang

- **WHEN** the current release boots
- **THEN** `RuntimeWatchdogSec` is not set by the AtomixOS watchdog module

#### Scenario: Normal operation does not trigger watchdog

- **WHEN** boot-stability validation approves active watchdog enforcement
- **THEN** the deferred target is to set `RuntimeWatchdogSec=30s`

### Requirement: Reboot watchdog target is deferred

The NixOS configuration SHALL not set `RebootWatchdogSec` in the current release. The deferred target is `10min`.

#### Scenario: Hung reboot is recovered

- **WHEN** the current release boots
- **THEN** `RebootWatchdogSec` is not set by the AtomixOS watchdog module

### Requirement: Watchdog timeout is configured appropriately

The deferred target values SHALL remain documented as `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min`.

#### Scenario: Watchdog configuration values are applied

- **WHEN** the device boots the current release
- **THEN** the watchdog module leaves `systemd.settings.Manager = { }`

### Requirement: Watchdog reset interacts with boot-count rollback

When the hardware watchdog triggers a reset, the subsequent reboot SHALL go through U-Boot's normal boot sequence, which
decrements the boot attempt counter. This means repeated watchdog-triggered resets on a bad image lead to automatic
rollback.

#### Scenario: Watchdog reset leads to rollback after repeated failures

- **WHEN** a new image causes the system to hang on every boot attempt, triggering the watchdog each time
- **THEN** U-Boot's boot counter decrements to zero and the device rolls back to the previous working slot
