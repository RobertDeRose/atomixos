# Boot & Rollback

> Source: `docs/src/features/rock64-ab-image/design.md#boot-rollback`

## Requirements

### ADDED: U-Boot tracks boot attempts per slot

U-Boot maintains `BOOT_A_LEFT` and `BOOT_B_LEFT` counters (initial value: 3). RAUC bootmeth selects the slot and
decrements the counter before loading `boot.scr`.

#### Scenario: Counter decrements on boot

- Given `BOOT_A_LEFT=3` and slot A is first in `BOOT_ORDER`
- When the device boots
- Then `BOOT_A_LEFT` is decremented to 2 before `boot.scr` loads the kernel
- And the SPI flash environment is updated

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

### ADDED: SPI flash U-Boot environment

The U-Boot environment is stored in SPI flash exposed to Linux as `/dev/mtd0` at offset `0x140000` with size `0x2000`.
AtomixOS does not store redundant U-Boot environment copies on eMMC.

#### Scenario: Userspace tools address SPI env

- Given the device has booted
- When `/etc/fw_env.config` is inspected
- Then it points to `/dev/mtd0 0x140000 0x2000 0x1000`
