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

#### Scenario: A slot whose boot files fail to load still rolls back

- Given slot B is preferred and its `boot.scr`, kernel, or DTB cannot be loaded
- When U-Boot's boot command fails to boot it
- Then the boot command resets the board instead of stopping at the U-Boot prompt
- And the next boot sees the decremented `BOOT_B_LEFT`, reaching slot A after the tries are used

### ADDED: Board-specific U-Boot environment

On ROCK64, the U-Boot environment is stored in SPI flash exposed to Linux as `/dev/mtd0` at offset `0x140000` with size
`0x2000`, with no redundant copy on eMMC. On the Radxa CM3, which may have no SPI NOR, it is stored as two redundant
32 KiB copies in the reserved eMMC gap before the first partition, at `0x3F8000` (primary) and `0x3F0000` (redundant).

#### Scenario: Userspace tools address the ROCK64 SPI env

- Given a ROCK64 device has booted
- When `/etc/fw_env.config` is inspected
- Then it points to `/dev/mtd0 0x140000 0x2000 0x1000`

#### Scenario: Userspace tools address the CM3 redundant eMMC env

- Given a CM3 device has booted
- When `/etc/fw_env.config` is inspected
- Then its first line is `/dev/mmcblk0 0x3F8000 0x8000`
- And its second line is `/dev/mmcblk0 0x3F0000 0x8000`
- And U-Boot is built with `CONFIG_ENV_REDUNDANT` and the same offsets
