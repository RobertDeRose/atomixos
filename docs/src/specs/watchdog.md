# Watchdog

> Source: `openspec/changes/rock64-ab-image/specs/watchdog/spec.md`

## Requirements

Current status: implementation hooks are present, but the Rock64 runtime watchdog is intentionally disabled during
development. The scenarios below define the current release behavior and the deferred target settings.

### ADDED: Hardware watchdog target is deferred

The RK3328 hardware watchdog (`dw_wdt`) target is documented, but systemd manager watchdog settings are not enabled in
the current release.

#### Scenario: Watchdog triggers on hang

- Given the current Rock64 image boots
- Then AtomixOS leaves `RuntimeWatchdogSec` unset
- And the deferred target remains `RuntimeWatchdogSec=30s`

### ADDED: Reboot watchdog

A separate reboot watchdog (`RebootWatchdogSec`) remains deferred until Rock64 boot reliability validation approves active
watchdog enforcement.

#### Scenario: Reboot hang recovery

- Given the current Rock64 image boots
- Then AtomixOS leaves `RebootWatchdogSec` unset
- And the deferred target remains `RebootWatchdogSec=10min`

### ADDED: Configurable timeouts

The watchdog timeouts are set in `modules/watchdog.nix`:

```nix
systemd.settings.Manager = {
  # RuntimeWatchdogSec = "30s";
  # RebootWatchdogSec = "10min";
};
```

- **Runtime**: 30 seconds -- aggressive enough to catch hangs quickly, long enough to avoid false triggers during normal
  operation
- **Reboot**: 10 minutes -- generous because clean shutdown may need time to stop containers

### ADDED: Watchdog interacts with boot-count rollback

A watchdog reboot is indistinguishable from any other abnormal reboot from U-Boot's perspective. Each watchdog-triggered
reboot:

1. Decrements the boot counter for the current slot
2. If the counter reaches 0, the slot is skipped
3. The previous working slot boots instead

This means a systemd hang on a newly updated slot will trigger automatic rollback within 3 watchdog cycles
(approximately 90 seconds total).

#### Scenario: Watchdog-triggered rollback

- Given slot B was just installed
- And slot B causes a systemd hang on every boot
- Then the watchdog reboots 3 times (30s each)
- And `BOOT_B_LEFT` decrements from 3 to 0
- And U-Boot falls back to slot A
