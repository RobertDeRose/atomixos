# Boot & Rollback

> Source: `openspec/changes/rock64-ab-image/specs/boot-rollback/spec.md`

## Requirements

### ADDED: U-Boot tracks boot attempts per slot

U-Boot maintains `BOOT_A_LEFT` and `BOOT_B_LEFT` counters (initial value: 3). On each boot attempt, the `boot.scr`
script decrements the counter for the selected slot and saves the environment before loading the kernel.

#### Scenario: Counter decrements on boot

- Given `BOOT_A_LEFT=3` and slot A is first in `BOOT_ORDER`
- When the device boots
- Then `BOOT_A_LEFT` is decremented to 2 before the kernel loads
- And the environment is saved to eMMC

#### Scenario: Counter reaches zero

- Given `BOOT_A_LEFT=0`
- When U-Boot attempts to boot slot A
- Then slot A is skipped
- And U-Boot tries the next slot in `BOOT_ORDER`

### ADDED: Boot order reflects RAUC slot priority

When RAUC installs an update to slot B, it sets `BOOT_ORDER=B A` so the updated slot is tried first. When slot A is
installed, it sets `BOOT_ORDER=A B`.

#### Scenario: RAUC sets boot order

- Given slot A is active
- When a RAUC bundle is installed
- Then `BOOT_ORDER` changes to `"B A"`
- And `BOOT_B_LEFT` is set to 3

### ADDED: Successful boot commits slot

After the health-check service passes, `rauc status mark-good` resets the boot counter for the current slot. This
prevents further rollback attempts.

#### Scenario: Health check commits slot

- Given the device booted into slot B with `BOOT_B_LEFT=2`
- When `os-verification.service` passes all checks
- Then `rauc status mark-good` is called
- And `BOOT_B_LEFT` is reset to 3

### ADDED: Rollback recovers previous image

After 3 consecutive failed boots (counter reaches 0), U-Boot skips the failing slot and boots the previous working slot.
The failed slot's data is preserved for diagnostics but is not booted.

#### Scenario: Automatic rollback after 3 failures

- Given slot B was just installed with `BOOT_ORDER=B A`
- And slot B fails to boot 3 times (kernel panic, hang, or health check failure)
- Then `BOOT_B_LEFT` reaches 0
- And U-Boot boots slot A (the previous working image)
- And slot A still has its original content

### ADDED: Redundant U-Boot environment

The U-Boot environment is stored in two copies at known eMMC offsets (`0x3F8000` and `0x3FC000`). If power is lost
during an environment write, the redundant copy preserves the last valid state.

#### Scenario: Power loss during env write

- Given `saveenv` is in progress
- When power is lost
- Then on next boot, U-Boot reads the valid redundant copy
- And boot continues with consistent state
