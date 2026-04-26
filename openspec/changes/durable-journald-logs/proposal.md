# Proposal

## Why

- The current root filesystem uses a tmpfs-backed overlay, so host logs
  disappear on reboot and power loss. That makes boot failures, failed
  updates, watchdog resets, and rollback events hard to reconstruct after the
  device recovers.
- At the same time, the image intentionally favors tmpfs-backed runtime state
  to reduce eMMC write amplification. The logging design needs to preserve that
  wear benefit while still keeping the most important forensic breadcrumbs
  durable.

## What Changes

- Add a bounded forensic black-box on each boot slot so critical lifecycle
  events survive reboot, rollback, and as many power-loss scenarios as
  practical
- Reserve up to `28 MiB` of each `128 MiB` boot partition for slot-local
  forensic storage while preserving kernel/initrd growth headroom
- Keep general host journald logging volatile with a bounded `64 MiB` runtime
  cap, rather than turning the whole host log stream into persistent write
  churn
- Pin Podman container logging to `journald` so routine application logs stay
  inside the same memory-first logging boundary
- Define which events are mirrored durably immediately: boot/initrd progress,
  `/data` availability, RAUC install and slot transitions, update
  confirmation, rollback, watchdog-related resets, and shutdown flush markers
- Document retention, durability guarantees, and the boundary between durable
  host forensics and volatile general host/application logs

## Capabilities

### New Capabilities

- `forensic-log-durability`: Bounded, slot-local forensic logging for critical
  boot and update lifecycle events, with volatile-first runtime logging
  elsewhere

### Modified Capabilities

- `durable-journald-logs`: Volatile host journald with an explicit runtime cap
  and Podman logging pinned to `journald` instead of `/data`-backed persistence

## Impact

- **Affected code**: boot partition layout assumptions, boot/update services,
  and host logging configuration in the base system
- **Affected docs**: partition layout, boot/update architecture, and
  operational debugging guidance
- **Operational impact**: Devices retain a bounded record of critical
  lifecycle events across reboot and rollback without making normal host or
  application logging persistently write-heavy
