# Watchdog Enforcement

AtomixOS supports opt-in hardware watchdog enforcement on Rock64, owned by systemd. Immutable build policy chooses the
onboard RK3328 DesignWare watchdog or an external TI UCC2946 watchdog, reached through the included I2C GPIO-expander
example. Enforcement is off by default. The original plan is in the [design record](design.md); Beads tracks the work
under `atomixos-aua`.

## What changed for users

Configure `build.toml`, or an ignored `build.dev.toml` at the repository root:

```toml
[watchdog]
enable_hardware = true
backend = "internal" # or "external"
```

- Set `enable_hardware = false` to turn enforcement off. The strict schema still requires `backend`, but it has no
  effect while enforcement is off.
- Supported `mise` builds apply local overlays and mark outputs `-dev`; direct Nix commands use the committed policy.
- The internal watchdog is `/dev/watchdog-internal`. The external one is `/dev/watchdog-external`, a TI UCC2946 on I2C
  bus 1 at address `0x41`.
- systemd (PID 1) is the only watchdog owner. Missing hardware fails open with a visible warning.

## How it fits in

The build-policy backend maps to a Rock64 device-tree selection and a stable udev alias. The internal overlay supplies
the RK3328 `snps,watchdog-tops` table. The external always-running GPIO watchdog overlay is included only when both the
external backend and enforcement are selected, so a build with enforcement off never arms the external hardware.

## Running it

Images with enforcement on use `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min` by default. Check the selected
watchdog with:

```sh
systemctl show --property WatchdogDevice --property RuntimeWatchdogUSec --property RebootWatchdogUSec
journalctl -b --no-pager | grep -E 'Using hardware watchdog|Watchdog running'
```

Physical watchdog tests are destructive. They need serial capture, recovery access, and a known-good slot; follow
[Hardware Testing](../../hardware-testing.md#phase-8-watchdog). An induced internal reset (`run0 kill -STOP 1`) must
show a second U-Boot TPL/SPL sequence on the serial console, then recover over SSH with no failed units.

## Differences from the design

- The internal `dw_wdt` path needed the RK3328 TOP interval table.
- The external device-tree overlay depends on both backend selection and enforcement, so a build with enforcement off
  cannot start the external always-running watchdog.

## Not included

- Enforcement in the committed policy. It stays off until external reset timing, watchdog rollback of an unconfirmed
  RAUC slot, and a 72-hour soak have been verified on hardware.
- Runtime watchdog control in `config.toml`, a userspace heartbeat daemon or `i2cset` kicker, and treating QEMU
  watchdog checks as hardware evidence.

## Tests

- `checks.<system>.watchdog-module`: option defaults and the opt-in systemd manager watchdog settings.
- `checks.<system>.watchdog-missing-device`: booting with enforcement on but no watchdog device.
- `checks.<system>.build-configuration` and `checks.<system>.build-config-workflow`: watchdog build policy.
- `checks.<system>.device-tree-overlay` and `checks.<system>.boot-script`: the Rock64 watchdog wiring.
- `mise run e2e:rauc-watchdog`: simulated watchdog resets and boot-count rollback.

## Related pages

- [Watchdog specification](../../specs/watchdog.md)
- [Build Configuration](../../reference/build-configuration.md)
- [Hardware Testing](../../hardware-testing.md#phase-8-watchdog)
- [Update and Rollback](../../architecture/update-rollback.md#watchdog-integration)
