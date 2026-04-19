# Watchdog

> Source: `openspec/changes/rock64-ab-image/specs/watchdog/spec.md`

## Requirements

Current status: implementation is present, but the Rock64 runtime watchdog is intentionally disabled during development.
The scenarios below describe the target behavior once re-enabled.

### ADDED: Hardware watchdog via systemd

The RK3328's hardware watchdog (`dw_wdt`) is managed by systemd. If systemd fails to kick the watchdog within the
configured timeout, the hardware forces a reboot.

#### Scenario: Watchdog triggers on hang

- Given `RuntimeWatchdogSec=30s` is configured
- When systemd stops sending keepalives (e.g., PID 1 hang)
- Then the hardware watchdog triggers after 30 seconds
- And the device reboots

### ADDED: Reboot watchdog

A separate reboot watchdog (`RebootWatchdogSec`) prevents the device from hanging during a reboot sequence (e.g.,
waiting for services to stop).

#### Scenario: Reboot hang recovery

- Given `RebootWatchdogSec=10min` is configured
- When a reboot takes longer than 10 minutes
- Then the hardware watchdog forces a hard reset

### ADDED: Configurable timeouts

The watchdog timeouts are set in `modules/watchdog.nix`:

```nix
systemd.settings.Manager = {
  RuntimeWatchdogSec = "30s";
  RebootWatchdogSec = "10min";
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
