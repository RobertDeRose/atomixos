# Boot Rollback Spec

## ADDED Requirements

### Requirement: U-Boot tracks boot attempts per slot

U-Boot SHALL maintain a boot-attempt counter for each slot (`BOOT_A_LEFT`, `BOOT_B_LEFT`). On each boot attempt, the
counter for the selected slot SHALL be decremented. If the counter reaches zero, U-Boot SHALL fall back to the other
slot on the next boot.

#### Scenario: Boot counter decrements on each boot

- **WHEN** the device boots and the active slot has `BOOT_A_LEFT=3`
- **THEN** U-Boot decrements the slot counter before attempting the boot

#### Scenario: Slot switches when counter reaches zero

- **WHEN** the active slot's boot counter reaches `0`
- **THEN** U-Boot selects the other slot on the next boot

### Requirement: U-Boot boot order reflects the next slot priority

U-Boot SHALL use `BOOT_ORDER` to determine slot priority, and RAUC installation SHALL make the newly written inactive
slot the next slot to attempt.

#### Scenario: RAUC install changes the preferred slot

- **WHEN** RAUC installs a bundle to slot B while slot A is active
- **THEN** the next boot attempts slot B before slot A

### Requirement: Successful confirmation commits the slot with RAUC

After successful first-boot validation or post-update confirmation, Linux SHALL call `rauc status mark-good` for the
booted slot.

#### Scenario: First boot commits the slot after valid provisioning

- **WHEN** `first-boot.service` successfully imports and validates provisioning state
- **THEN** it calls `rauc status mark-good` for the booted slot

#### Scenario: Updated slot is committed after local verification

- **WHEN** `os-verification.service` confirms the booted slot is healthy
- **THEN** it calls `rauc status mark-good` for the booted slot

### Requirement: Rollback preserves the previous working slot

If a newly installed slot cannot boot successfully or never reaches a committed state, U-Boot SHALL eventually fall back
to the previous working slot.

#### Scenario: Failed update triggers automatic rollback

- **WHEN** a new image is installed to slot B and slot B fails repeatedly until its boot counter is exhausted
- **THEN** U-Boot falls back to slot A

#### Scenario: Previous slot remains intact

- **WHEN** the device rolls back from slot B to slot A
- **THEN** slot A still contains the previously working image because updates only write the inactive slot pair

### Requirement: Rock64 uses the active U-Boot environment path supported by the platform

The Rock64 rollback design SHALL use the platform's active U-Boot environment path together with RAUC's U-Boot backend
rather than relying on ad hoc slot bookkeeping in Linux.

#### Scenario: Linux and U-Boot agree on slot identity

- **WHEN** Linux determines the booted slot and calls `rauc status mark-good`
- **THEN** the same slot identity is used by the U-Boot / RAUC rollback path
