# Watchdog Enforcement

## Delivery Summary

- Beads feature root: `atomixos-aua`
- Status: implementation and physical watchdog-path validation complete; close-out remains pending RAUC OTA evidence
- Pull request: not created
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS supports opt-in systemd hardware watchdog enforcement on Rock64. Immutable build policy selects either the
onboard RK3328 DesignWare watchdog or the external TI UCC2946 path through the included I2C GPIO-expander example.
Enforcement remains disabled by default.

## User-Facing Behavior

Configure `build.toml` or an ignored repository-root `build.dev.toml`:

```toml
[watchdog]
enable_hardware = true
backend = "internal" # or "external"
```

Set `enable_hardware = false` to disable enforcement completely. The backend field remains required by the strict schema,
but has no runtime effect while enforcement is disabled. Supported `mise` builds apply local overlays and mark outputs
`-dev`; direct Nix commands use committed policy only.

The internal path is `/dev/watchdog-internal`. The external path is `/dev/watchdog-external`, backed by the TI UCC2946
through I2C bus 1/address `0x41`. Systemd PID 1 is the sole watchdog owner. Missing hardware fails open with an
observable warning; the legacy userspace `i2cset` kicker is not used.

## Design Integration

The build-policy backend maps to a Rock64-specific device-tree selection and stable udev alias. The internal overlay
supplies the RK3328 `snps,watchdog-tops` table. The external always-running GPIO watchdog overlay is included only when
both the external backend and hardware enforcement are selected, preventing a disabled build from arming the external
hardware accidentally.

## Operational Impact

Enabled images use `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min` by default. Verify the selected path with:

```sh
systemctl show --property WatchdogDevice --property RuntimeWatchdogUSec --property RebootWatchdogUSec
journalctl -b --no-pager | grep -E 'Using hardware watchdog|Watchdog running'
```

Physical watchdog tests are destructive and require serial capture, recovery access, and a known-good slot. Rollback and
72-hour soak validation remain part of the RAUC OTA campaign.

## Reference and Contracts

- [Watchdog specification](../../specs/watchdog.md)
- [Build configuration](../../reference/build-configuration.md)
- [Hardware testing](../../hardware-testing.md#phase-8-watchdog)
- [Update and rollback architecture](../../architecture/update-rollback.md#watchdog-integration)
- [Feature design](design.md)

## Validation Evidence

- Rock64 internal path: `/dev/watchdog-internal` resolved to `watchdog0`; sysfs bound to `dw_wdt`; the loaded TOP table
  contained 16 cells; PID 1 held `/dev/watchdog0`.
- Rock64 external path: the UCC2946/PCA9536-compatible path was previously physically validated through I2C bus 1 and
  `/dev/watchdog-external`.
- Internal induced-reboot test: `run0 kill -STOP 1` caused a second U-Boot TPL/SPL/U-Boot sequence in the serial capture,
  followed by SSH recovery and a clean system state.
- Serial evidence: `/tmp/rock64-internal-watchdog-reset.log`.
- Post-reset systemd evidence: selected device, 30-second runtime timeout, 10-minute reboot timeout, running system,
  and no failed units.

## Design Reconciliation

### Delivered as Designed

- Immutable build-time policy owns enablement, backend selection, and timeout values.
- Systemd is the sole hardware watchdog owner.
- Internal and external Rock64 paths are selectable without introducing runtime configuration.
- Missing hardware remains fail-open.
- Physical device and induced-reboot evidence exists for both watchdog paths.

### Intentional Changes

- The originally investigated internal `dw_wdt` path required the RK3328 TOP interval table.
- The external device-tree overlay is conditional on both backend selection and hardware enablement so a disabled build
  cannot start the external always-running watchdog.

### Deferred Work

- Three-attempt watchdog rollback on an unconfirmed RAUC-updated slot.
- 72-hour normal-workload soak.
- Release-profile enablement remains deferred until the RAUC OTA validation campaign completes.

### Rejected or Removed Scope

- Runtime `config.toml` watchdog control.
- A userspace heartbeat daemon or legacy `i2cset` kicker.
- Treating QEMU watchdog checks as physical Rock64 evidence.

## Documentation Updated

- `docs/src/specs/watchdog.md`
- `docs/src/reference/build-configuration.md`
- `docs/src/hardware-testing.md`
- `docs/src/architecture/update-rollback.md`
- `docs/src/design-decisions.md`
- `docs/src/unknowns.md`
- `docs/src/planned-features.md`
- `docs/src/features/watchdog-enforcement/index.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`

## Audit Trail

Implementation and physical evidence were recorded on Beads task `atomixos-aua.7.32`. The implementation coordinator and
RAUC rollback/soak work remain open until the deferred validation is complete.
