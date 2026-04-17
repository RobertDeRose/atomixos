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

### Requirement: Boot confirmation uses FAT flag file (not fw_setenv)

**CHANGED**: The original design called for `fw_setenv` from Linux to reset boot counters after successful confirmation.
Testing revealed that **writing to the raw eMMC user data area from Linux bricks NCard eMMC modules** (the board fails
to produce any U-Boot output after power cycle). U-Boot's own `saveenv` command works correctly.

The confirmation flow now uses a FAT flag file approach:

1. `first-boot.service` (or `os-verification.service`) writes a `slot_good` file to the boot FAT partition (`/boot`)
2. On next boot, U-Boot's `boot.cmd` checks for `slot_good` via `fatload`
3. If found: U-Boot restores `BOOT_x_LEFT=3` and calls `saveenv` (which works from U-Boot), then deletes the flag file
4. If not found: normal boot-count decrement continues

This avoids all raw eMMC writes from Linux while preserving the boot-count rollback mechanism.

#### Scenario: First boot confirmation via FAT flag

- **WHEN** `first-boot.service` runs on a freshly provisioned image
- **THEN** it writes a `slot_good` file to `/boot` (the boot FAT partition)
- **AND** on the next power cycle, U-Boot detects `slot_good`, restores the boot counter, and deletes the file

#### Scenario: Update confirmation via FAT flag

- **WHEN** `os-verification.service` confirms a successful update
- **THEN** it writes a `slot_good` file to `/boot`
- **AND** on the next power cycle, U-Boot commits the slot via `saveenv`

### Requirement: U-Boot environment uses single-copy storage

U-Boot environment is stored as a single 32 KB copy at offset `0x3F8000` on the eMMC. The Rock64's U-Boot build
(`rk3328_defconfig`) does NOT enable `CONFIG_ENV_REDUNDANT`.

**Note**: The original design called for redundant environment storage. Investigation of the U-Boot source confirmed
this is not configured for this platform. The FAT flag file approach mitigates the risk — if U-Boot's `saveenv` is
interrupted by power loss, the `slot_good` file remains on the FAT partition and U-Boot will retry on the next boot.

#### Scenario: Power loss during U-Boot saveenv

- **WHEN** power is lost while U-Boot is writing environment variables via `saveenv`
- **THEN** the `slot_good` flag file remains on the FAT partition, and U-Boot will re-attempt the counter restore on
  the next boot
