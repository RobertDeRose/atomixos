# Oops And Early-Boot Logging Findings

## Context

We investigated how to persist very-early boot forensic information,
especially initrd failures, without relying on the current approach of
mounting the boot FAT partition in initrd and writing custom marker
files on every boot.

## Current State

The current initrd forensic implementation is not working reliably.

Observed on the live board:

- `forensics-initrd-start.service` and `forensics-initrd-rootfs-selected.service` fail during initrd on the current boot.
- The actual failure is not just stale systemd state after switch-root.
- The current journal showed:

```text
forensics-initrd-log: failed to mount /dev/mmcblk1p1 at /run/forensics-initrd
forensics-initrd-start.service: Main process exited, code=exited, status=1/FAILURE
forensics-initrd-rootfs-selected.service: Main process exited, code=exited, status=1/FAILURE
```

- `systemctl reset-failed` only clears the recorded failed state afterward. It does not fix the root cause.

## What Systemd Is Doing

Systemd initrd runs as a separate service manager instance before switch-root.

Relevant documented initrd flow:

- `initrd-root-device.target`
- `sysroot.mount`
- `initrd-root-fs.target`
- `initrd-fs.target`
- `initrd.target`
- `initrd-switch-root.target`
- `initrd-switch-root.service`

Important implications:

- initrd units run in the initrd manager, not the host OS manager.
- after `initrd-switch-root.service`, the host manager takes over
- failed initrd units can still appear in `systemctl --failed` until
  reset, because systemd keeps failed units in memory for introspection
- there is no special unit setting that means “this is an initrd unit, do not show failure after switch-root”

What `reset-failed` does:

- clears the recorded failed state
- clears start-limit/restart counters
- does not repair the actual initrd failure

## Conclusion About The Current Design

The current design of mounting the boot FAT partition from initrd and writing markers on every boot is fragile.

The failure we are seeing is most likely an ordering/dependency issue:

- `initrd-root-device.target` means the root device exists
- it does not guarantee that the boot FAT partition is ready to be mounted safely at that point
- our custom initrd services attempt an ad hoc mount of `/dev/mmcblk1p1` too early

So this should be treated as a real initrd dependency/order bug, not a cosmetic failed-state propagation issue.

## Alternative Design Considered

### Buffer To `/run` In Initrd, Flush Only On Failure

Proposed approach:

- write initrd forensic events only to `/run` during initrd
- do not try to mount `/boot` on the normal initrd success path
- add an initrd service that flushes the buffered log to
  `/boot/forensics` only on failure, for example when initrd reaches
  `emergency.target`

Why this is attractive:

- `/run` is tmpfs and always available in initrd
- it avoids the current fragile early FAT mount attempt
- `emergency.target` is a standard systemd failure hook in initrd

Likely systemd shape:

- buffer logs to `/run/atomixos-forensics/...`
- add an initrd oneshot such as `forensics-initrd-flush-on-emergency.service`
- order it before `emergency.service`
- pull it in via `wantedBy = [ "emergency.target" ]`

Possible enhancement:

- use `OnFailure=` on specific critical initrd services in addition to or instead of the generic emergency hook

## Tradeoffs Of The `/run` Plus Emergency-Flush Design

What is lost:

- initrd forensic records are no longer persisted on every successful boot
- persistence only happens when the failure path stays alive long enough to flush them
- it will not catch:
  - kernel panic
  - hard hang
  - sudden power loss
  - failure before systemd can run the flush service

What is kept:

- forensic capture for the recoverable initrd failure class that drops into emergency/recovery
- the `/boot/forensics` persistence model
- userspace forensics after switch-root

What is gained:

- avoids false failed units on healthy boots
- removes dependency on mounting the boot FAT partition too early
- makes persisted initrd markers more meaningful, because they now indicate an actual initrd failure path

This is a narrower guarantee than "always write a marker on
every boot", but that broader goal is not currently working
anyway.

## Existing Implementations And Guidance

### Kernel-Supported Persistent Crash Logging

The kernel already has established facilities for early/crash logging.

#### `ramoops`

Documented in the kernel admin guide.

Purpose:

- persistent oops/panic logger using reserved persistent RAM
- circular buffer across reboot
- can also support console and ftrace persistence

When it fits:

- best option if the platform can reserve persistent RAM safely
- intended exactly for crash/oops/panic persistence

#### `pstore/blk`

Also documented in the kernel admin guide.

Purpose:

- writes oops/panic/console/ftrace/pmsg data to a block backend
- records are exposed through the `pstore` filesystem after reboot

Important guidance from the docs:

- panic-time writers must not rely on normal kernel conveniences
- no dynamic allocation at panic time
- no sleeping/interrupt-driven behavior
- avoid ordinary locking and heavyweight kernel services

This strongly suggests that low-level persistence is better
handled by `pstore` than by ad hoc initrd shell units mounting
writable filesystems.

### Early Console

The kernel command line and serial console facilities are the standard live-observation path:

- `earlycon`
- `console=`

These are useful for visibility, but they do not provide persistent storage by themselves.

### Systemd Guidance

Systemd documentation strongly supports:

- using initrd targets correctly
- using `emergency.target` for recoverable failure handling

It does not suggest that custom initrd services should
routinely mount arbitrary writable filesystems and append logs
there during every boot.

## NixOS-Specific Findings

No clear built-in NixOS high-level option was identified for “persist custom initrd forensic markers to `/boot`”.

That means the problem is mostly architectural rather than “we forgot to enable the obvious NixOS option”.

## Recommended Direction

### Pragmatic Near-Term Direction

Replace the current initrd FAT-write behavior with:

- write semantic breadcrumbs to `/run` during initrd
- flush them to `/boot/forensics` only on the initrd failure path, such as `emergency.target`

This is the cleanest way to preserve the current custom forensic model while removing the fragile early mount dependency.

### Best-Practice Long-Term Direction

Use a layered approach:

1. `earlycon` / serial console for live early visibility
2. `pstore` (`ramoops` preferred, `pstore/blk` if needed) for panic/oops persistence
3. custom `/run`-buffered initrd breadcrumbs for high-level semantic state, flushed only on recoverable initrd failures

## Bottom Line

- The current implementation does not work correctly.
- `reset-failed` is not the right solution; it only hides the evidence afterward.
- There is no special systemd unit flag that makes initrd failures disappear properly after switch-root.
- Existing kernel guidance points toward `pstore` for true crash persistence.
- Existing systemd guidance points toward `emergency.target` for recoverable initrd failure hooks.
- If we keep the custom forensic breadcrumb approach, buffering
  to `/run` and flushing only on failure is the most reasonable
  next design.
