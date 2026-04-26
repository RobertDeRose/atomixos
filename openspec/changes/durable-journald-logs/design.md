# Design

## Context

The Rock64 image runs from a read-only squashfs with a tmpfs-backed overlay for
mutable root state. That keeps the runtime root clean on every boot and
minimizes steady-state eMMC wear, but it also means host logs are currently
volatile unless they are copied elsewhere.

The failures this project cares about most are lifecycle failures: boot
regressions, failed update confirmation, watchdog resets, rollback decisions,
networking bring-up issues, and first-boot provisioning problems. Those events
need post-reboot forensic visibility, especially when a device recovers only
after a power cycle or slot rollback.

The device already has two different writable surfaces with different roles:

- `/boot` is mounted from the active slot's FAT boot partition and is available as part of the boot/update path
- `/data` is the main persistent mutable partition for provisioned state and application data

Applications are expected to run in Podman, with container storage already
rooted on `/data`. That means this change does not need to invent a general
persistent application-data model. The problem here is host-platform forensics
under tight write-wear constraints.

## Goals / Non-Goals

**Goals:**

- Preserve a bounded record of critical host lifecycle events across reboot, rollback, and as many power-loss cases as practical
- Keep normal host logging memory-first so the image retains the write-reduction benefits of its tmpfs-backed runtime model
- Reserve a fixed forensic budget on each boot slot with deterministic retention behavior
- Make the durability guarantees explicit: critical mirrored events are durable-first, general runtime logs are not

**Non-Goals:**

- Shipping a remote log collection pipeline or external log forwarding
- Making the full host journal power-loss durable
- Defining long-term application log retention policy beyond establishing the boundary with Podman logging
- Changing the overall partition layout or introducing a dedicated log partition

## Decisions

### 1. Use a three-tier logging model

**Choice**: Split logging into three tiers with different durability and wear profiles.

```text
Tier 0: Slot-local forensic black box on /boot
Tier 1: Volatile host journal in memory
Tier 2: Application/container log policy (separate concern)
```

Tier 0 exists for the small set of events that must survive reboot and should
be made as power-loss resistant as practical. Tier 1 keeps normal host logging
in RAM so the device does not continuously write routine logs to eMMC. Tier 2
acknowledges that applications run in Podman and need a separate logging policy
decision, rather than silently inheriting a host forensics design.

**Alternatives considered**:

- **Single persistent journald store**: simpler conceptually, but undermines
  the memory-first wear model by making all host logging durable.
- **No distinction between host and app logs**: blurs responsibility and makes scope creep likely.

### 2. Reserve `28 MiB` per boot slot for Tier 0 forensic storage

**Choice**: Dedicate up to `28 MiB` of each `128 MiB` boot partition to bounded forensic storage.

**Rationale**: The current kernel/initrd/DTB payload is well below the full
boot partition size, and the user explicitly wants a slot-local forensic
reserve that survives with the slot. `28 MiB` is large enough for a substantial
lifecycle event history while still preserving generous headroom for future
kernel and initrd growth.

This storage should behave like a black box, not a general-purpose filesystem
for arbitrary logs. A fixed budget makes retention deterministic and prevents
forensic artifacts from crowding out boot assets.

**Alternatives considered**:

- **Store Tier 0 only on `/data`**: simpler long-term store, but loses the
  advantage of slot-local, early-available forensic state.
- **Use a smaller budget**: safer for boot growth but less useful for field debugging.
- **Use a larger budget**: possible, but starts trading too much future boot payload headroom for logs.

### 3. Tier 0 should use a fixed-size rotated layout, not an unbounded append log

**Choice**: Represent Tier 0 as a fixed-size rotated or segmented store within the `28 MiB` budget.

**Rationale**: A black-box retention model only works if the size ceiling is
absolute. Fixed-size segments avoid unbounded growth, make recovery
expectations clearer, and reduce metadata churn compared with arbitrary file
creation.

One concrete model is seven `4 MiB` segments per slot plus a tiny metadata file:

```text
/boot/forensics/
  meta
  segment-0.log
  segment-1.log
  ...
  segment-6.log
```

The active segment appends new records until full, then the oldest segment is
reused. That makes retention size-based rather than time-based and keeps the
implementation aligned with a black-box recorder.

The metadata file should track only the minimum state needed for recovery and
continuation, such as format version, active segment, active `boot_id`, and
next sequence number.

**Alternatives considered**:

- **Single growing file with truncation**: simpler initially, but harder to
  reason about after crashes and less explicit as a ring-buffer design.
- **Timestamp-based rotation**: less deterministic under bursty failure scenarios.

### 4. Tier 0 should use compact key/value line records with `boot_id + seq`

**Choice**: Encode Tier 0 as single-line key/value records with a per-boot `boot_id` and a monotonic `seq` within that boot.

**Rationale**: Tier 0 is a forensic recorder, not a general logging backend.
Human-readable key/value lines are compact, easy to inspect over serial or SSH,
easy to emit from shell-driven services, and degrade gracefully on power loss
because a torn final line can simply be ignored.

The record format should require:

- `boot_id`
- `seq`
- `ts`
- `slot`
- `stage`
- `event`

with optional fields such as:

- `result`
- `target_slot`
- `reason`
- `version`
- `device`
- `service`
- `attempt`
- `detail`

The `boot_id + seq` pairing is intentional:

- `boot_id` groups events by boot session for cleaner forensic reading
- `seq` provides strict ordering even when timestamps are coarse, identical, or corrected later by NTP

This is stronger than timestamps alone and simpler than a single global persistent sequence spanning all boots.

**Alternatives considered**:

- **JSON lines**: more machine-friendly, but more verbose and more awkward to emit robustly from shell-heavy boot paths.
- **Binary records**: more deterministic, but far less debuggable in the field.
- **Timestamp-only ordering**: too weak for early boot and near-simultaneous events.

### 5. Mirror only critical lifecycle events into Tier 0

**Choice**: Limit Tier 0 to a narrow event taxonomy instead of trying to mirror the full journal.

**Rationale**: The goal is post-failure reconstruction, not durable storage for
all log chatter. A smaller event vocabulary keeps write volume low and makes
the black-box log more useful during triage.

The initial event taxonomy should include these stage names:

- `initrd`
- `boot`
- `firstboot`
- `rauc`
- `verify`
- `rollback`
- `watchdog`
- `shutdown`

The initial event set should include:

- initrd and boot progression markers
- active slot and rootfs selection markers
- `/data` mount success or failure
- `first-boot` start and completion
- RAUC install start, success, and failure
- update-confirmation start, success, and failure
- rollback detection
- watchdog-related reset markers or inferred reboot cause markers
- orderly shutdown flush begin and end

Representative event names include:

- `boot-start`
- `lowerdev-selected`
- `rootfs-mount-ok`
- `rootfs-mount-failed`
- `userspace-start`
- `data-mount-ok`
- `data-mount-failed`
- `boot-complete`
- `start`
- `complete`
- `failed`
- `install-start`
- `install-complete`
- `install-failed`
- `mark-good-start`
- `mark-good-complete`
- `mark-good-failed`
- `detected`
- `slot-fallback`
- `boot-attempt-exhausted`
- `armed`
- `reboot-inferred`
- `flush-begin`
- `flush-end`

**Alternatives considered**:

- **Mirror the whole journal**: too write-heavy and defeats the purpose of volatile-first logging.
- **Log only RAUC events**: too narrow; boot and watchdog failures would still be opaque.

### 6. Tier 0 events should be written with durable-first semantics

**Choice**: Treat each Tier 0 write as an immediate durability event and flush it explicitly.

**Rationale**: The whole point of Tier 0 is surviving the cases where Tier 1
volatile logs disappear. Each critical event should therefore be written and
flushed in a way that minimizes exposure to power loss.

This does not create a theoretical guarantee against every possible corruption
mode, but it does create the strongest practical durability semantics in the
current storage model.

**Alternatives considered**:

- **Batch writes for efficiency**: lower write overhead, but directly weakens the power-loss guarantee.
- **Rely on periodic journal export only**: leaves exactly the most important events vulnerable.

### 7. Keep Tier 1 journald volatile and bounded

**Choice**: Keep normal host journald storage in volatile memory with an
explicit `64 MiB` runtime cap.

**Rationale**: This preserves the eMMC-wear benefits of the tmpfs-backed system
while still allowing rich short-term diagnostics during a live session. Tier 0
covers the durable forensic minimum; Tier 1 remains a convenience layer, not
the durable truth source.

**Alternatives considered**:

- **Persistent journald on `/data`**: contradicts the wear-reduction goal.
- **No journald cap**: risks memory pressure from noisy services.

### 8. Pin Podman logging to journald inside the volatile boundary

**Choice**: Set Podman's container `log_driver` to `journald` so routine
application stdout and stderr follow the same volatile-first boundary as host
journald.

**Rationale**: Applications run in Podman and their durable state already lives
on `/data`, but application stdout/stderr retention is a different question
from host lifecycle forensics. Pinning the log driver avoids drift in Podman
defaults and keeps application log behavior aligned with the final logging
boundary documented by this change.

**Alternatives considered**:

- **Make app logs part of Tier 0**: too broad and too write-heavy.
- **Ignore app logs entirely**: leaves an important design boundary
  undocumented.

## Risks / Trade-offs

- **FAT boot storage is not a perfect forensic medium** -> Mitigate by keeping
  the Tier 0 format simple, bounded, append-oriented, and tolerant of a torn
  final line.
- **Immediate durable writes still create some wear** -> Acceptable because
  Tier 0 is intentionally tiny and event-limited.
- **Slot-local boot logs may not follow the active slot after rollback** ->
  This is partly a feature, because each slot preserves its own recent history;
  docs should make that mental model clear.
- **Application log volume could pressure volatile journal space** -> Mitigate
  by pinning Podman to `journald`, keeping the host runtime cap explicit, and
  relying on Tier 0 only for critical lifecycle records.
- **Metadata corruption could obscure the active segment** -> Keep metadata
  minimal and recoverable by scanning segment files if needed.

## Post-Review Hardening

The initial implementation satisfied the core change goals, but a later review
found a small set of durability and correctness gaps that were fixed before
closing validation.

- The active-slot forensic mount helper now verifies an actual mount via
  `findmnt` instead of assuming directory existence implies durable boot
  storage. This prevents Tier 0 writes from silently falling back to tmpfs.
- The initrd forensic helper now fails explicitly on missing boot-device or
  mount prerequisites instead of silently succeeding. This keeps early
  lifecycle markers aligned with the change's durable-first intent.
- The update-confirmation path now logs `mark-good-complete` only on real
  success and logs `mark-good-failed` plus `verify failed` on failure in both
  the first-boot fallback and post-health-check confirmation paths.
- RAUC status parsing was corrected to read the keyed slot structure returned
  by `rauc status --output-format=json`, avoiding false "already good" or
  incorrect current-version decisions.
- Routine polling and "no update" style upgrade chatter was removed from Tier
  0 so the durable forensic budget stays focused on high-value lifecycle
  evidence.
- Regression coverage was extended to include mount-selection behavior and an
  explicit negative `mark-good` confirmation path in `rauc-confirm`, including
  test harness steps needed to avoid stale cached RAUC state across phases.

## Migration Plan

Existing devices pick up the new configuration on the next deployed image. The
boot partitions gain a reserved forensic directory within the existing slot
budget, and host lifecycle services begin mirroring critical events into that
bounded store.

Rollback is straightforward: remove the Tier 0 writer and return to purely
volatile host journald. No data migration is required because the forensic
store is bounded, slot-local, and self-contained.

## Final Scope Notes

- The explored option of storing the full host journal on `/data` was not
  adopted. The final design keeps general journald traffic volatile and relies
  on the bounded Tier 0 `/boot` recorder for durable lifecycle evidence.
- The volatile journald cap is `64 MiB`.
- Podman logging is pinned to `journald` so container log traffic remains
  inside the same volatile-first runtime boundary.
