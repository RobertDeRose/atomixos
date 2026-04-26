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
- Keep general host journald tmpfs-first during runtime as the log ingress
  point, without allowing journald itself to write routine logs directly to
  persistent media
- Add an `rsyslog` RAM queue behind volatile journald so general host and
  container logs are collected in memory and written to `/data/logs` in large,
  infrequent, sequential batches rather than in many small writes
- Flush the in-memory buffered log queue to `/data/logs` during orderly
  shutdown so the last clean shutdown captures the latest buffered host
  diagnostics
- Align Podman container logging with the same journald-plus-rsyslog buffering
  policy so routine application logs also remain memory-first during runtime
  while following the same large-batch persistent append path
- Define which events are mirrored durably immediately: boot/initrd progress,
  `/data` availability, RAUC install and slot transitions, update
  confirmation, rollback, watchdog-related resets, and shutdown/reboot markers
- Document retention, durability guarantees, and the boundary between durable
  host forensics and buffered general host/application logs

## Capabilities

### New Capabilities

- `forensic-log-durability`: Bounded, slot-local forensic logging for critical
  boot and update lifecycle events, with memory-first runtime logging
  elsewhere

### Modified Capabilities

- `durable-journald-logs`: Tmpfs-first host journald feeding an in-memory
  `rsyslog` batch queue, with large sequential appends to `/data/logs`,
  orderly shutdown flush, and Podman logging aligned to the same buffering
  model

## Impact

- **Affected code**: boot partition layout assumptions, boot/update services,
  host logging configuration in the base system, and the `/data` log export
  path
- **Affected docs**: partition layout, boot/update architecture, and
  operational debugging guidance
- **Operational impact**: Devices retain a bounded record of critical
  lifecycle events across reboot and rollback while keeping normal host and
  application logging memory-first during runtime and appending broader logs to
  `/data/logs` in large, sequential batches plus orderly shutdown flushes

The recovered explore discussion was most concrete about the Tier 0 `/boot`
forensic design. The broader tmpfs-first journald plus `/data` durable logging
path was also part of the explored architecture. This change now resolves the
less-specified Layer 2 mechanism explicitly as a RAM-queued `rsyslog` batch
append path to `/data/logs` rather than timer-driven journal checkpoints.
