# Boot and Rollback

Acceptance contract for U-Boot slot selection, boot counting, and rollback. The flow is explained in
[Update and Rollback](../architecture/update-rollback.md).

## Requirements

### U-Boot tracks boot attempts per slot

U-Boot keeps `BOOT_A_LEFT` and `BOOT_B_LEFT` counters (3 tries per slot). The RAUC bootmeth selects the slot and
decrements its counter before loading `boot.scr`.

#### Scenario: Counter decrements on boot

- Given `BOOT_A_LEFT=3` and slot A is first in `BOOT_ORDER`
- When the device boots
- Then `BOOT_A_LEFT` is 2 before `boot.scr` loads the kernel
- And the saved U-Boot environment is updated

#### Scenario: Counter reaches zero

- Given `BOOT_A_LEFT=0`
- When U-Boot selects a slot
- Then slot A is skipped
- And U-Boot tries the next slot in `BOOT_ORDER`

#### Scenario: Every slot is exhausted

- Given every slot's counter is 0
- When U-Boot selects a slot
- Then it resets every counter to 3 and boots in `BOOT_ORDER`

### Boot order reflects RAUC slot priority

When RAUC installs an update to slot B it sets `BOOT_ORDER=B A`, so the updated slot is tried first. An install to slot
A sets `BOOT_ORDER=A B`.

#### Scenario: RAUC sets the boot order

- Given slot A is active
- When a RAUC bundle is installed
- Then `BOOT_ORDER` changes to `B A`
- And `BOOT_B_LEFT` is set to 3

### A healthy boot commits the slot

After the health check passes, `rauc status mark-good` restores the current slot's counter, which stops further
rollback attempts.

#### Scenario: Health check commits the slot

- Given the device booted slot B with `BOOT_B_LEFT=2`
- When `os-verification.service` passes all checks
- Then `rauc status mark-good` runs
- And `BOOT_B_LEFT` is reset to 3

### Rollback recovers the previous image

After three failed boots, the counter reaches 0 and U-Boot boots the previous working slot. The failed slot's data is
kept for diagnostics but is not booted.

A kernel panic after `systemd-sysctl` reboots the device after 10 seconds (`kernel.panic = 10`), which counts as a
failed boot. A panic earlier in the initrd needs a hardware watchdog reset or a power cycle.

#### Scenario: Automatic rollback after three failures

- Given slot B was just installed with `BOOT_ORDER=B A`
- And slot B fails to boot three times (kernel panic, hang, or failed health check)
- Then `BOOT_B_LEFT` reaches 0
- And U-Boot boots slot A, the previous working image
- And slot A still has its original content

#### Scenario: A slot whose boot files fail to load still rolls back

- Given slot B is preferred and its `boot.scr`, kernel, or DTB cannot be loaded
- When U-Boot's boot command fails to boot it
- Then the boot command resets the board instead of stopping at the U-Boot prompt
- And the next boot sees the decremented `BOOT_B_LEFT`, reaching slot A after the tries are used

### The boot script works with factory-flashed U-Boot

RAUC bundles replace `boot.scr` but not U-Boot, so the boot script keeps working with the U-Boot a device was flashed
with and does not depend on features added to U-Boot later.

#### Scenario: USB recovery after an OTA update on an older U-Boot

- Given a device whose U-Boot has no `START_UMS` `PREBOOT` installs a new bundle
- When `START_UMS=1` is set and the device reboots
- Then the new `boot.scr` enters USB mass storage mode

#### Scenario: A failed load resets without the U-Boot reset fallback

- Given a device whose U-Boot boot command doesn't end in `reset`
- When `boot.scr` cannot load the kernel, DTB, or initrd, or `booti` rejects them
- Then `boot.scr` resets the board itself

### Board-specific U-Boot environment

On Rock64, the U-Boot environment lives in SPI flash, exposed to Linux as `/dev/mtd0`, at offset `0x140000` with size
`0x2000`, with no copy on eMMC. On the Radxa CM3, which may have no SPI NOR, it is stored as two redundant 32 KiB copies
in the reserved eMMC gap before the first partition, at `0x3F8000` (primary) and `0x3F0000` (redundant).

#### Scenario: Userspace tools address the Rock64 SPI environment

- Given a Rock64 device has booted
- When `/etc/fw_env.config` is inspected
- Then it contains `/dev/mtd0 0x140000 0x2000 0x1000`

#### Scenario: Userspace tools address the CM3 redundant eMMC environment

- Given a CM3 device has booted
- When `/etc/fw_env.config` is inspected
- Then its first line is `/dev/mmcblk0 0x3F8000 0x8000`
- And its second line is `/dev/mmcblk0 0x3F0000 0x8000`
- And U-Boot is built with `CONFIG_ENV_REDUNDANT` and the same offsets
