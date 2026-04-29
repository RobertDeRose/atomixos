# Partition Layout Specification

> Source: `openspec/changes/rock64-ab-image/specs/partition-layout/spec.md`

## Requirements

### ADDED: eMMC A/B layout

The 16 GB eMMC uses a fixed partition layout with raw U-Boot at the beginning, two pairs of A/B slots (boot + rootfs),
and a persistent data partition using all remaining space. The flash image contains slot A only; initrd
`systemd-repart` creates slot B and `/data` on first boot.

#### Scenario: Partition table matches specification

- Given a provisioned eMMC
- Then `sfdisk -d` shows 2 GPT partitions in the flashable image (boot-a, rootfs-a)
- And the raw region (0-16 MB) contains U-Boot
- And after the first successful boot, initrd `systemd-repart` has created three
  additional GPT partitions labeled `boot-b`, `rootfs-b`, and `data`
- And `/data` (f2fs) uses the remaining space

### ADDED: Per-slot boot partitions

Each slot pair has its own boot partition (vfat) containing the kernel, initrd, DTB, and boot script. This ensures boot
and rootfs are always consistent for a given slot.

#### Scenario: Boot partition contents match slot

- Given slot A is active
- Then boot-a contains `Image`, `initrd`, `rk3328-rock64.dtb`, and `boot.scr`
- And boot-b is absent before first boot or contains the other slot's kernel afterward

### ADDED: Flashable disk image

The `build` task produces a flashable `.img` file containing U-Boot, boot slot A, rootfs slot A, and a
remaining-space region reserved for first-boot creation of boot slot B, rootfs slot B, and `/data` by initrd
`systemd-repart`.

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

### ADDED: /data survives updates

The `/data` partition is never modified by RAUC slot writes or slot switches. Container data, configuration, and
credentials persist across all updates and rollbacks.

#### Scenario: Persist data survives update

- Given a file exists at `/data/config/test-file`
- When a RAUC update installs a new image and the device reboots
- Then `/data/config/test-file` still exists with the same content

### ADDED: U-Boot env for slot selection

U-Boot environment variables (`BOOT_ORDER`, `BOOT_A_LEFT`, `BOOT_B_LEFT`) control which slot boots and how many attempts
remain. On Rock64 these are stored in SPI flash and are seeded safely from Linux on first boot when missing.

#### Scenario: Environment survives power loss

- Given `BOOT_ORDER` is set to `"B A"`
- When power is lost during env write
- Then U-Boot falls back to its compiled defaults or a previously valid SPI environment
