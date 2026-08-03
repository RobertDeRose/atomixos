# Watchdog

> Source: `docs/src/features/watchdog-enforcement/design.md`

## Requirements

Current status: Rock64 runtime watchdog enforcement is opt-in and intentionally disabled by default. Both the onboard
RK3328 DesignWare path and the external TI UCC2946 path have passed physical device and ownership validation; the
internal path has also passed induced-reboot validation. Rollback and 72-hour soak evidence remain deferred to RAUC OTA
testing.

### Hardware watchdog enforcement remains opt-in

The RK3328 hardware watchdog (`dw_wdt`) and the external UCC2946 path are available, but systemd manager watchdog
settings are enabled only when `atomixos.watchdog.enableHardware = true`.

#### Scenario: Watchdog triggers on hang

- Given the current Rock64 image boots
- Then AtomixOS leaves `RuntimeWatchdogSec` unset
- And the opt-in target remains `RuntimeWatchdogSec=30s`

### Reboot watchdog

A separate reboot watchdog (`RebootWatchdogSec`) remains disabled by default in committed policy. It is available in
opt-in images; release-profile enablement remains gated on RAUC rollback and soak validation.

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
backend = "external"
runtime_timeout = "30s"
reboot_timeout = "10min"
```

The fields map to `enableHardware`, `backend`, `runtimeWatchdogSec`, and `rebootWatchdogSec` respectively. `backend`
accepts `internal` for the RK3328 DesignWare watchdog or `external` for the UCC2946 path through the I2C GPIO
expander. Runtime values must resolve to 10 seconds–5 minutes; reboot values must resolve to 1–10 minutes. The
committed defaults remain:

Build-time selection examples are:

```toml
# Onboard watchdog
[watchdog]
enable_hardware = true
backend = "internal"

# Or the external SOM watchdog:
# backend = "external"

# Or disable enforcement completely:
# enable_hardware = false
```

The full committed document must retain both `enable_hardware` and `backend`; a partial `build.dev.toml` overlay may
contain only the fields being tested. With `enable_hardware = false`, systemd leaves all watchdog manager settings
unset, and the external always-running device-tree node is not included. The backend value is retained only so a future
enablement is explicit.

The committed defaults remain:

- **Runtime**: 30 seconds -- aggressive enough to catch hangs quickly, long enough to avoid false triggers during normal
  operation
- **Reboot**: 10 minutes -- generous because clean shutdown may need time to stop containers

Accepted policy is not proof that a physical watchdog implements the exact requested value. Systemd may select the
nearest timeout supported by the driver and device. Physical validation must record the programmed hardware timeout and
confirm observed reset timing before release enablement.

### Internal RK3328 watchdog path

The Rock64's onboard Synopsys DesignWare watchdog is selected with `backend = "internal"`. Its device-tree overlay
supplies the RK3328 TOP interval table, and the image exposes it to systemd as `/dev/watchdog-internal`.

### External SOM watchdog path

The SOM watchdog is a TI UCC2946 driven through a four-bit I2C GPIO expander at address `0x41` on I2C bus 1. The
expander's GPIO0 is held low to enable the watchdog and GPIO1 is toggled for `WDI`. The kernel `gpio-pca953x` and
`gpio-wdt` drivers expose this path as `/dev/watchdog-external`; systemd selects that stable udev alias when hardware
watchdog enforcement is enabled. The external device-tree node is included only when both the external backend and
hardware enforcement are selected. The legacy userspace `i2cset` kicker is not used.

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

The `watchdog-boot-count` package and service exist only on RAUC-enabled profiles. RAUC-enabled U-Boot and custom-backend
profiles retain the helper; non-RAUC profiles do not carry or run update rollback integration.

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
