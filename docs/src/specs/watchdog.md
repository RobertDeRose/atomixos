# Watchdog

> Source: `docs/src/features/rock64-ab-image/design.md#watchdog`

## Requirements

Current status: implementation hooks are present, but Rock64 runtime watchdog enforcement is opt-in and intentionally
disabled by default until physical boot-reliability validation approves active enforcement. The scenarios below define the
current default behavior and the opt-in target settings.

### ADDED: Hardware watchdog target is deferred

The RK3328 hardware watchdog (`dw_wdt`) target is documented, but systemd manager watchdog settings are enabled only when
`atomixos.watchdog.enableHardware = true`.

#### Scenario: Watchdog triggers on hang

- Given the current Rock64 image boots
- Then AtomixOS leaves `RuntimeWatchdogSec` unset
- And the opt-in target remains `RuntimeWatchdogSec=30s`

### ADDED: Reboot watchdog

A separate reboot watchdog (`RebootWatchdogSec`) remains disabled by default until Rock64 boot reliability validation
approves active watchdog enforcement.

#### Scenario: Reboot hang recovery

- Given the current Rock64 image boots
- Then AtomixOS leaves `RebootWatchdogSec` unset
- And the opt-in target remains `RebootWatchdogSec=10min`

### ADDED: Configurable timeouts

Immutable build policy configures the existing `atomixos.watchdog.*` NixOS options:

```toml
version = 1

[watchdog]
enable_hardware = false
runtime_timeout = "30s"
reboot_timeout = "10min"
```

The fields map to `enableHardware`, `runtimeWatchdogSec`, and `rebootWatchdogSec` respectively. Runtime values must
resolve to 10 seconds–5 minutes; reboot values must resolve to 1–10 minutes. The committed defaults remain:

- **Runtime**: 30 seconds -- aggressive enough to catch hangs quickly, long enough to avoid false triggers during normal
  operation
- **Reboot**: 10 minutes -- generous because clean shutdown may need time to stop containers

Accepted policy is not proof that a physical watchdog implements the exact requested value. Systemd may select the
nearest timeout supported by the driver and device. Physical validation must record the programmed hardware timeout and
confirm observed reset timing before release enablement.

### ADDED: Missing hardware fails open with a warning

When hardware enforcement is enabled but systemd does not hold a usable watchdog device,
`watchdog-device-check.service` logs an actionable warning and exits successfully. The device continues booting; the
missing watchdog alone does not fail update verification or mutate RAUC slot state.

#### Scenario: Enabled policy has no watchdog device

- Given `atomixos.watchdog.enableHardware = true`
- And no watchdog character device exists
- When the system reaches `multi-user.target`
- Then `watchdog-device-check.service` reports that hardware enforcement is unavailable
- And boot continues without changing RAUC slot state

### ADDED: Watchdog interacts with boot-count rollback

A watchdog reboot is indistinguishable from any other abnormal reboot from U-Boot's perspective. Each watchdog-triggered
reboot:

1. Decrements the boot counter for the current slot
2. If the counter reaches 0, the slot is skipped
3. The previous working slot boots instead

The intended hardware behavior is that a systemd hang on a newly updated slot triggers automatic rollback after 3
watchdog-triggered failed boots. The rollback timing includes watchdog expiry plus the time needed for each reboot and
slot-selection attempt.

The QEMU `rauc-watchdog` check uses a custom RAUC backend and a two-attempt boot-count file to keep the simulation fast.
Physical Rock64 validation uses the U-Boot `BOOT_*_LEFT` environment counter documented above.

#### Scenario: Watchdog-triggered rollback

- Given slot B was just installed
- And slot B causes a systemd hang on every boot
- Then the watchdog reboots 3 times (30s each)
- And `BOOT_B_LEFT` decrements from 3 to 0
- And U-Boot falls back to slot A
