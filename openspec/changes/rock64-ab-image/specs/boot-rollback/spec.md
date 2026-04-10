# Boot Rollback Spec

## ADDED Requirements

### Requirement: U-Boot tracks boot attempts per slot

U-Boot SHALL maintain a boot attempt counter for each slot (`BOOT_A_LEFT`, `BOOT_B_LEFT`). On each boot, U-Boot SHALL
decrement the counter for the slot being booted. If the counter reaches zero, U-Boot SHALL switch to the other slot on
the next boot.

#### Scenario: Boot counter decrements on each boot

- **WHEN** the device boots and the active slot has `BOOT_A_LEFT=3`
- **THEN** after U-Boot runs, `BOOT_A_LEFT` is decremented to `2`

#### Scenario: Slot switches when counter reaches zero

- **WHEN** the active slot's boot counter reaches `0` and the device reboots
- **THEN** U-Boot selects the other slot as the boot target on the next boot

### Requirement: U-Boot boot order reflects RAUC slot priority

U-Boot SHALL use a `BOOT_ORDER` environment variable (e.g., `A B`) to determine slot priority. RAUC SHALL update this
variable when installing a new bundle so that the newly written slot is attempted first.

#### Scenario: RAUC install changes boot order

- **WHEN** RAUC installs a bundle to slot B while slot A is active
- **THEN** the U-Boot environment is updated so that `BOOT_ORDER` is `B A` and `BOOT_B_LEFT` is reset to the configured
  attempt count

### Requirement: Successful boot commits the slot via mark-good

After a successful boot and confirmation, the system SHALL call `rauc status mark-good` which resets the boot attempt
counter to its maximum value, preventing further rollback for the current slot.

#### Scenario: Mark-good prevents rollback

- **WHEN** `rauc status mark-good` is called on the active slot
- **THEN** the boot attempt counter for the active slot is reset to its maximum value and the slot is marked as
  committed

### Requirement: Rollback recovers the previous working image

If the new slot fails to boot (boot counter exhausted), U-Boot SHALL boot the previous slot. The previous slot SHALL
still be intact and bootable because RAUC only writes to the inactive slot.

#### Scenario: Failed update triggers automatic rollback

- **WHEN** a new image is installed to slot B and slot B fails to boot 3 consecutive times
- **THEN** U-Boot switches back to slot A and the device boots successfully from the previous known-good image

#### Scenario: Rollback preserves previous slot integrity

- **WHEN** the device rolls back from slot B to slot A
- **THEN** slot A's root filesystem is identical to its state before the update was attempted

### Requirement: U-Boot environment uses redundant storage

U-Boot environment SHALL be stored in two redundant copies on eMMC so that a power loss during environment write does
not corrupt the boot configuration.

#### Scenario: Power loss during env write does not corrupt boot config

- **WHEN** power is lost while U-Boot is writing environment variables
- **THEN** U-Boot falls back to the redundant copy and boots with the last known-good environment
