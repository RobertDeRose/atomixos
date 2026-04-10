# Watchdog Spec

## ADDED Requirements

### Requirement: Hardware watchdog is enabled via systemd

The NixOS configuration SHALL enable the RK3328 hardware watchdog via systemd's `RuntimeWatchdogSec` setting. systemd
SHALL kick the watchdog at the configured interval. If systemd stops kicking (hang, panic, deadlock), the hardware
watchdog SHALL reset the device.

#### Scenario: Watchdog fires on system hang

- **WHEN** the system hangs (kernel panic, deadlock, or systemd becomes unresponsive) for longer than the configured
  watchdog timeout
- **THEN** the hardware watchdog triggers a hard reset of the device

#### Scenario: Normal operation does not trigger watchdog

- **WHEN** the system is running normally with systemd healthy
- **THEN** systemd kicks the watchdog before the timeout expires and no reset occurs

### Requirement: Reboot watchdog prevents reboot hangs

The NixOS configuration SHALL set `RebootWatchdogSec` to ensure that if a reboot sequence itself hangs, the hardware
watchdog forces a hard reset.

#### Scenario: Hung reboot is recovered

- **WHEN** a reboot command is issued but the shutdown sequence hangs
- **THEN** the reboot watchdog fires after the configured timeout and forces a hard reset

### Requirement: Watchdog timeout is configured appropriately

`RuntimeWatchdogSec` SHALL be set to `30s` and `RebootWatchdogSec` SHALL be set to `10min`. These values SHALL be
configurable in the NixOS module.

#### Scenario: Watchdog configuration values are applied

- **WHEN** the device boots and systemd reads its configuration
- **THEN** `RuntimeWatchdogSec` is `30s` and `RebootWatchdogSec` is `10min` as reported by `systemctl show -p
  RuntimeWatchdogUSec -p RebootWatchdogUSec`

### Requirement: Watchdog reset interacts with boot-count rollback

When the hardware watchdog triggers a reset, the subsequent reboot SHALL go through U-Boot's normal boot sequence, which
decrements the boot attempt counter. This means repeated watchdog-triggered resets on a bad image lead to automatic
rollback.

#### Scenario: Watchdog reset leads to rollback after repeated failures

- **WHEN** a new image causes the system to hang on every boot attempt, triggering the watchdog each time
- **THEN** U-Boot's boot counter decrements to zero and the device rolls back to the previous working slot
