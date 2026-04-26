# Tasks

## 1. Tier 0 Forensic Storage Design

- [x] 1.1 Define the slot-local forensic storage layout under `/boot` with a hard `28 MiB` per-slot retention budget
- [x] 1.2 Implement the Tier 0 metadata and segment layout as `meta` plus seven `4 MiB` segment files per boot slot
- [x] 1.3 Implement Tier 0 records as single-line key/value records with
  required fields `boot_id`, `seq`, `ts`, `slot`, `stage`, and `event`
- [x] 1.4 Implement per-boot `boot_id + seq` ordering so `seq` resets for each new boot session
- [x] 1.5 Implement segment rollover that reuses the oldest segment without exceeding the `28 MiB` slot budget
- [x] 1.6 Define durable-write semantics for Tier 0 records so critical
  lifecycle events are flushed immediately and torn final lines are tolerated
  during readback

## 2. Critical Event Coverage

- [x] 2.1 Wire boot and initrd progression markers into Tier 0 forensic logging
- [x] 2.2 Wire `/data` mount outcome, `first-boot`, RAUC install, update
  confirmation, rollback, watchdog, and shutdown flush markers into Tier 0
  forensic logging using the defined stage/event taxonomy
- [x] 2.3 Ensure Tier 0 captures enough information to reconstruct failed
  update and rollback flows without mirroring the whole journal

## 3. Volatile Runtime Logging Boundary

- [x] 3.1 Keep general host journald logging volatile and set an explicit
  `64 MiB` runtime size cap
- [x] 3.2 Pin Podman container logging to `journald` so application stdout and
  stderr follow the same volatile-first boundary
- [x] 3.3 Document the boundary between durable Tier 0 host forensics and non-durable general host/application logs

## 4. Validation and Documentation

- [x] 4.1 Verify Tier 0 forensic records survive reboot and remain readable after a successful slot switch
- [x] 4.2 Verify the bounded retention model overwrites old records without exceeding the per-slot `28 MiB` budget
- [x] 4.3 Verify critical Tier 0 events remain available after simulated failed update or rollback scenarios
- [x] 4.4 Verify per-boot `boot_id + seq` ordering behaves correctly across reboot, slot switch, and rollback scenarios
- [x] 4.5 Update architecture and operational docs to describe the three-tier
  logging model and the power-loss durability boundary
- [x] 4.6 Record post-review hardening fixes and regression coverage for mount
  selection, initrd durability, RAUC confirmation failure handling, and Tier 0
  event filtering
