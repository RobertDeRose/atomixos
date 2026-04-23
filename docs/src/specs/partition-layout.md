# Partition Layout Specification

> Source: `openspec/changes/rock64-ab-image/specs/partition-layout/spec.md`

## Requirements

### ADDED: eMMC A/B layout

The 16 GB eMMC uses a fixed partition layout with raw U-Boot at the beginning, two pairs of A/B slots (boot + rootfs),
and a persistent data partition using all remaining space.

#### Scenario: Partition table matches specification

- Given a provisioned eMMC
- Then `sfdisk -d` shows 5 GPT partitions (boot-a, boot-b, rootfs-a, rootfs-b, persist)
- And the raw region (0-16 MB) contains U-Boot
- And `/persist` (f2fs) uses remaining space

### ADDED: Per-slot boot partitions

Each slot pair has its own boot partition (vfat) containing the kernel, initrd, DTB, and boot script. This ensures boot
and rootfs are always consistent for a given slot.

#### Scenario: Boot partition contents match slot

- Given slot A is active
- Then boot-a contains `Image`, `initrd`, `rk3328-rock64.dtb`, and `boot.scr`
- And boot-b is either empty or contains the other slot's kernel

### ADDED: Flashable disk image

The `build:image` task produces a flashable `.img` file containing U-Boot, boot slots A/B, rootfs slots A/B, and a
small `persist` partition formatted as f2fs.

### ADDED: U-Boot at RK3328 offsets

U-Boot is written as raw data (no partition) at the offsets expected by the RK3328 boot ROM:

- `idbloader.img` at sector 64 (byte offset 32 KB)
- `u-boot.itb` at sector 16384 (byte offset 8 MB)

Both come from the custom Rock64 U-Boot package built by this flake.

#### Scenario: U-Boot loads from eMMC

- Given U-Boot is written at the correct offsets
- When the Rock64 powers on
- Then the serial console shows U-Boot initialization
- And `bootflow scan` finds `boot.scr` on boot-a

### ADDED: /persist survives updates

The `/persist` partition is never modified by RAUC slot writes or slot switches. Container data, configuration, and
credentials persist across all updates and rollbacks.

#### Scenario: Persist data survives update

- Given a file exists at `/persist/config/test-file`
- When a RAUC update installs a new image and the device reboots
- Then `/persist/config/test-file` still exists with the same content

### ADDED: U-Boot env for slot selection

U-Boot environment variables (`BOOT_ORDER`, `BOOT_A_LEFT`, `BOOT_B_LEFT`) control which slot boots and how many attempts
remain. On Rock64 these are stored in SPI flash and are seeded safely from Linux on first boot when missing.

#### Scenario: Environment survives power loss

- Given `BOOT_ORDER` is set to `"B A"`
- When power is lost during env write
- Then U-Boot falls back to its compiled defaults or a previously valid SPI environment
