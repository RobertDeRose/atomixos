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
  confirmation, and shutdown flush or managed reboot markers into Tier 0
  forensic logging using the defined stage/event taxonomy
- [ ] 2.3 Record concrete slot-transition, rollback, and watchdog lifecycle
  markers on the real device path rather than only in test scaffolding
- [ ] 2.4 Ensure Tier 0 captures enough information to reconstruct failed
  update and rollback flows without mirroring the whole journal

## 3. Buffered Runtime Logging Boundary

- [x] 3.1 Keep general host journald tmpfs-first during runtime and set an
  explicit bounded runtime size cap
- [ ] 3.2 Add `rsyslog` behind volatile journald with a RAM-backed queue for
  general host logging
- [ ] 3.3 Append buffered general host logs to `/data/logs` in large,
  infrequent, sequential batches rather than many small direct writes
- [ ] 3.4 Flush the buffered general log queue to `/data/logs` during orderly
  shutdown
- [x] 3.5 Pin Podman container logging to `journald` so application stdout and
  stderr follow the same buffered journald path
- [ ] 3.6 Validate Podman's logging path and retention behavior under the chosen
  journald-plus-rsyslog buffering model
- [ ] 3.7 Define `/data/logs` rotation, retention, and append-file layout for
  the large-batch persistent path
- [ ] 3.8 Evaluate whether `/data` should gain mount options such as `noatime`
  to further reduce metadata writes on the persistent log path
- [ ] 3.9 Document the boundary between durable Tier 0 host forensics and
  buffered general host/application logs

## 4. Validation and Documentation

- [x] 4.1 Verify Tier 0 forensic records survive reboot and remain readable after a successful slot switch
- [x] 4.2 Verify the bounded retention model overwrites old records without exceeding the per-slot `28 MiB` budget
- [ ] 4.3 Verify critical Tier 0 events remain available after simulated failed
  update or rollback scenarios using the real forensic implementation rather
  than test-only stubs
- [x] 4.4 Verify per-boot `boot_id + seq` ordering behaves correctly across reboot, slot switch, and rollback scenarios
- [ ] 4.5 Verify the `rsyslog` RAM queue appends buffered logs to `/data/logs`
  in large sequential batches during normal runtime
- [ ] 4.6 Verify orderly shutdown flush persists the latest buffered general
  logs to `/data/logs`
- [ ] 4.7 Verify Podman/application logs follow the intended memory-first and
  batched persistent retention path
- [ ] 4.8 Update architecture and operational docs to describe the three-tier
  logging model and the power-loss durability boundary
- [x] 4.9 Record post-review hardening fixes and regression coverage for mount
  selection, initrd durability, RAUC confirmation failure handling, and Tier 0
  event filtering
