# Forensic Log Durability Spec

## ADDED Requirements

### Requirement: Critical lifecycle events are mirrored to slot-local forensic storage

The system SHALL mirror critical host lifecycle events into a bounded forensic
store on the active boot slot so they remain available after reboot, slot
rollback, and as many power-loss scenarios as practical. The initrd portion of
this path remains incomplete until the early-boot persistence design is revised
to avoid fragile direct boot-partition mounts during normal initrd execution.

#### Scenario: Critical boot event is retained after reboot

- **WHEN** the device records a critical boot or update lifecycle event and then reboots
- **THEN** that event remains available from the slot-local forensic store after the reboot

#### Scenario: Failed update leaves forensic evidence

- **WHEN** an update attempt fails and the device later rolls back to a previous slot
- **THEN** the affected slot retains its recent mirrored lifecycle events for forensic inspection

### Requirement: Slot-local forensic storage is strictly bounded

The system SHALL cap slot-local forensic storage at `28 MiB` per boot slot.
The system SHALL represent that budget as seven `4 MiB` segment files plus
minimal metadata, and SHALL rotate or overwrite the oldest forensic records
when that limit is reached.

#### Scenario: Forensic store reaches capacity

- **WHEN** new mirrored lifecycle events would exceed the `28 MiB` storage budget on a boot slot
- **THEN** the system retains newer events and removes or overwrites the oldest retained forensic records within that slot

#### Scenario: Segment rollover preserves bounded retention

- **WHEN** the active `4 MiB` segment fills during normal operation
- **THEN** the system advances to the next segment, reuses the oldest segment
  when necessary, and continues writing without exceeding the `28 MiB` slot
  budget

### Requirement: Tier 0 records use boot-scoped ordering

The system SHALL encode each Tier 0 forensic record as a single-line key/value
record. Each record SHALL include `boot_id`, `seq`, `ts`, `slot`, `stage`, and
`event`. The system SHALL reset `seq` at the start of each new `boot_id`.

#### Scenario: Events within a boot are strictly ordered

- **WHEN** multiple Tier 0 events are written during the same boot session
- **THEN** their `seq` values increase monotonically within that `boot_id`

#### Scenario: New boot starts a new forensic sequence

- **WHEN** the device reboots into a new boot session on the same slot
- **THEN** the device writes records with a new `boot_id` and restarts `seq` from the beginning for that boot session

### Requirement: Tier 0 event scope is limited to high-value lifecycle records

The system SHALL limit slot-local forensic storage to high-value lifecycle
events. Allowed Tier 0 stages SHALL include `initrd`, `boot`, `firstboot`,
`rauc`, `verify`, `rollback`, `watchdog`, and `shutdown`. Tier 0 events SHALL
cover boot progression, slot selection, `/data` mount outcome, update
lifecycle events, update-confirmation outcome, rollback detection,
watchdog-related reset markers, orderly shutdown flush markers, and managed
reboot or poweroff request markers where those flows are part of the system.
The initrd stage specifically requires redesign before this requirement can be
considered complete.

#### Scenario: Noisy routine logs are excluded from Tier 0

- **WHEN** ordinary service or application log traffic is emitted during normal runtime
- **THEN** that traffic is not mirrored wholesale into the slot-local forensic store

#### Scenario: Failed slot keeps its own forensic history

- **WHEN** the device boots into an updated slot, fails, and later rolls back to the previous slot
- **THEN** the failed slot retains its own recent Tier 0 forensic records on its boot partition for later inspection

### Requirement: General host logging remains memory-first outside Tier 0

The system SHALL keep general host journald logging memory-first during runtime
and SHALL reserve the slot-local forensic store for critical lifecycle evidence
rather than for general-purpose log persistence.

#### Scenario: Runtime host logs are not automatically durable

- **WHEN** a non-critical host log entry is written only to the general runtime journal
- **THEN** that entry is not guaranteed to survive an abrupt power loss

#### Scenario: Tier 0 remains focused on critical evidence

- **WHEN** routine host or application log traffic is emitted during normal
  operation
- **THEN** that traffic is handled through the general volatile-journald plus
  RAM-queued batch logging path rather than being mirrored wholesale into the
  slot-local forensic store
