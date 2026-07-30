# Tasks: durable-journald-logs

## 1. Tier 0 Forensic Storage Design

- [x] T001 1.1 Define the slot-local forensic storage layout under `/boot` with a hard `28 MiB` per-slot retention budget
- [x] T002 1.2 Implement the Tier 0 metadata and segment layout as `meta` plus seven `4 MiB` segment files per boot slot
- [x] T003 1.3 Implement Tier 0 records as single-line key/value records with
  required fields `boot_id`, `seq`, `ts`, `slot`, `stage`, and `event`
- [x] T004 1.4 Implement per-boot `boot_id + seq` ordering so `seq` resets for each new boot session
- [x] T005 1.5 Implement segment rollover that reuses the oldest segment without exceeding the `28 MiB` slot budget
- [x] T006 1.6 Define durable-write semantics for Tier 0 records so critical
  lifecycle events are flushed immediately and torn final lines are tolerated
  during readback

## 2. Critical Event Coverage

- [ ] T007 2.1 Redesign initrd Tier 0 forensic logging so early-boot markers are captured without relying on ad hoc
  boot-partition mounts during normal initrd execution
- [x] T008 2.2 Wire `/data` mount outcome, `first-boot`, RAUC install, update
  confirmation, and shutdown flush or managed reboot markers into Tier 0
  forensic logging using the defined stage/event taxonomy
- [x] T009 2.3 Record concrete slot-transition, rollback, and watchdog lifecycle
  markers on the real device path rather than only in test scaffolding
- [x] T010 2.4 Ensure Tier 0 captures enough information to reconstruct failed
  update and rollback flows without mirroring the whole journal

## 3. Buffered Runtime Logging Boundary

- [x] T011 3.1 Keep general host journald tmpfs-first during runtime and set an
  explicit bounded runtime size cap
- [x] T012 3.2 Add `rsyslog` behind volatile journald with a RAM-backed queue for
  general host logging
- [x] T013 3.3 Append buffered general host logs to `/data/logs` in large,
  infrequent, sequential batches rather than many small direct writes
- [x] T014 3.4 Flush the buffered general log queue to `/data/logs` during orderly
  shutdown
- [x] T015 3.5 Pin Podman container logging to `journald` so application stdout and
  stderr follow the same buffered journald path
- [x] T016 3.6 Validate Podman's logging path and retention behavior under the chosen
  journald-plus-rsyslog buffering model
- [x] T017 3.7 Define `/data/logs` rotation, retention, and append-file layout for
  the large-batch persistent path
- [x] T018 3.8 Evaluate whether `/data` should gain mount options such as `noatime`
  to further reduce metadata writes on the persistent log path
- [x] T019 3.9 Document the boundary between durable Tier 0 host forensics and
  buffered general host/application logs

## 4. Validation and Documentation

- [ ] T020 4.1 Verify the redesigned initrd Tier 0 path records the intended early-boot evidence without leaving failed
  initrd units on successful boots
- [x] T021 4.2 Verify the bounded retention model overwrites old records without exceeding the per-slot `28 MiB` budget
- [x] T022 4.3 Verify critical Tier 0 events remain available after simulated failed
  update or rollback scenarios using the real forensic implementation rather
  than test-only stubs
- [x] T023 4.4 Verify per-boot `boot_id + seq` ordering behaves correctly across reboot, slot switch, and rollback scenarios
- [x] T024 4.5 Verify the `rsyslog` RAM queue appends buffered logs to `/data/logs`
  in large sequential batches during normal runtime
- [x] T025 4.6 Verify orderly shutdown flush persists the latest buffered general
  logs to `/data/logs`
- [x] T026 4.7 Verify Podman/application logs follow the intended memory-first and
  batched persistent retention path
- [x] T027 4.8 Update architecture and operational docs to describe the three-tier
  logging model and the power-loss durability boundary
- [ ] T028 4.9 Record post-review hardening fixes and regression coverage for the redesigned initrd forensic path,
  mount selection, RAUC confirmation failure handling, and Tier 0 event filtering
