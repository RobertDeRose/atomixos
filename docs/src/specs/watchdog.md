# Watchdog

Acceptance contract for hardware watchdog enforcement. The settings are in
[Build Configuration](../reference/build-configuration.md#watchdog-backend-selection), and the module is described in
[NixOS Modules](../code-reference/modules.md#watchdognix).

## Requirements

### Hardware watchdog enforcement is opt-in on Rock64

The onboard SoC watchdog and, on Rock64, the external UCC2946 path are available. On Rock64, systemd watchdog manager
settings are set only when `watchdog.enable_hardware = true` in build policy (`atomixos.watchdog.enableHardware`). The
committed `build.toml` leaves enforcement off. The CM3 is the exception: see
[Boot stalls reset the CM3](#boot-stalls-reset-the-cm3).

#### Scenario: Default image leaves the watchdog unset

- Given a Rock64 image built from the committed `build.toml`
- When it boots
- Then systemd's `RuntimeWatchdogSec`, `RebootWatchdogSec`, and `WatchdogDevice` are unset

#### Scenario: Enabled image arms the watchdog

- Given `watchdog.enable_hardware = true` with the default timeouts
- When the image boots on hardware with the selected watchdog
- Then systemd sets `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min`
- And `WatchdogDevice` is the selected backend's device

### Configurable timeouts

Build policy sets `watchdog.runtime_timeout` (default `30s`) and `watchdog.reboot_timeout` (default `10min`) within the
accepted ranges listed in [Build Configuration](../reference/build-configuration.md#version-1-schema). The runtime
timeout catches a hung system quickly without false triggers during normal operation. The reboot timeout is generous
because a clean shutdown may need time to stop containers.

An accepted value is not proof that the hardware uses it exactly. systemd may pick the nearest timeout the driver and
device support, so check the programmed value on the target board.

### Backends expose stable device paths

`watchdog.backend = "internal"` exposes the onboard Synopsys DesignWare watchdog as `/dev/watchdog-internal`.
`watchdog.backend = "external"` exposes the Rock64 external SOM watchdog as `/dev/watchdog-external`; its device-tree
overlay is included only when both the external backend and enforcement are selected, so a disabled build never arms
the external hardware. The CM3 always uses its internal watchdog. Systemd is the only watchdog owner; no userspace
`i2cset` kicker is used. The hardware behind each backend is described in
[Watchdog Backend Selection](../reference/build-configuration.md#watchdog-backend-selection).

#### Scenario: CM3 ignores the external backend

- Given a CM3 build with `watchdog.enable_hardware = true` and `backend = "external"`
- When the configuration is evaluated
- Then the build warns that the CM3 IO Board has no external watchdog
- And systemd uses `/dev/watchdog-internal`

### Boot stalls reset the CM3

The CM3 U-Boot starts the RK3566 watchdog before every kernel and feeds it whenever U-Boot is running, including at the
prompt and during `ums`. Its 44-second request rounds up to the 44.7-second hardware period. The board module sets
`atomixos.watchdog.bootloaderStarted`, which:

1. adds `watchdog.open_timeout=180` (`atomixos.watchdog.openTimeoutSec`) to the kernel command line, so the kernel feeds
   the running watchdog for at most 180 seconds after its driver registers, unless systemd opens it first;
2. turns systemd enforcement on whatever `watchdog.enable_hardware` says, with the build policy's timeouts and
   `/dev/watchdog-internal`.

The initrd's systemd does not open the watchdog, so the open timeout covers the kernel and the whole initrd. It must be
longer than the slowest first-boot initrd, which creates slot B and formats `/data`.

#### Scenario: A kernel stalls before its watchdog driver registers

- Given a CM3 slot whose kernel stops before the watchdog driver registers, without panicking
- When U-Boot boots that slot
- Then the watchdog resets the board within 44.7 seconds of U-Boot's last feed
- And the reset spends one of the slot's boot tries

#### Scenario: A boot stalls before stage-2 systemd

- Given a CM3 slot whose kernel or initrd stalls after the watchdog driver registers
- When U-Boot boots that slot
- Then the kernel stops feeding the watchdog 180 seconds after the driver registers
- And the watchdog resets the board up to 44.7 seconds later
- And after three stalled tries U-Boot boots the other slot without a manual reset

#### Scenario: Normal CM3 boot hands the watchdog to systemd

- Given a CM3 image built from the committed `build.toml`, where `enable_hardware = false`
- When it boots, including its first boot
- Then PID 1 holds `/dev/watchdog-internal` with `RuntimeWatchdogSec` and `RebootWatchdogSec` from build policy
- And the board is not reset

Rock64's U-Boot does not start a watchdog, and Rock64 kernels carry no `watchdog.open_timeout`.

### Missing hardware fails open with a warning

When enforcement is enabled but systemd holds no usable watchdog device, `watchdog-device-check.service` logs a warning
and exits successfully. On Rock64, boot continues; a missing watchdog alone does not fail update verification or change
RAUC slot state. On the CM3, U-Boot has already started the watchdog, so a system whose systemd does not hold it is
reset once the kernel stops feeding it, and its slot falls back like any other failed boot.

#### Scenario: Enabled policy has no watchdog device

- Given `atomixos.watchdog.enableHardware = true`
- And no watchdog character device exists
- When the system reaches `multi-user.target`
- Then `watchdog-device-check.service` reports that hardware enforcement is unavailable
- And boot continues without changing RAUC slot state

### Watchdog resets feed boot-count rollback

`watchdog-boot-count.service` exists only on RAUC-enabled systems. To U-Boot, a watchdog reset is the same as any other
abnormal reboot. Each one:

1. decrements the current slot's boot counter;
2. skips the slot once its counter reaches 0;
3. boots the previous working slot instead.

A systemd hang on a newly updated slot therefore rolls back after three watchdog resets. The total time includes the
watchdog timeout plus each reboot and slot selection.

The QEMU `rauc-watchdog` check uses the `custom` RAUC backend with a two-attempt boot-count file to keep the test fast.
On hardware the counter is the U-Boot `BOOT_*_LEFT` variable.

#### Scenario: Watchdog-triggered rollback

- Given slot B was just installed with enforcement enabled
- And slot B hangs systemd on every boot
- Then the watchdog resets the board three times, 30 seconds after each hang
- And `BOOT_B_LEFT` decrements from 3 to 0
- And U-Boot falls back to slot A
