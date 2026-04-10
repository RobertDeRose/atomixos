# Partition Layout Spec

## ADDED Requirements

### Requirement: eMMC partition layout supports A/B boot and root filesystem slots

The eMMC SHALL be partitioned with the following layout: raw U-Boot region (~4 MB), two vfat boot partitions (slot A and
slot B, ~32 MB each) containing kernel and DTB, two squashfs root filesystem partitions (slot A and slot B, ~200 MB
each), and an f2fs /persist partition consuming the remaining space (~15 GB on a 16 GB eMMC).

#### Scenario: Partition table matches specification

- **WHEN** the eMMC is inspected with `fdisk -l` or `parted print` after provisioning
- **THEN** the partition table contains two vfat boot partitions (A and B), two rootfs partitions (A and B), and an f2fs
  /persist partition, with U-Boot written at the RK3328 boot ROM expected offset

### Requirement: Per-slot boot partitions contain kernel and DTB

Each boot slot (A and B) SHALL contain the Linux kernel image and device tree blob for that slot's corresponding rootfs.
RAUC SHALL update the boot partition and rootfs partition atomically as part of a single bundle install.

#### Scenario: Boot partition matches its rootfs slot

- **WHEN** the device boots from slot A
- **THEN** U-Boot loads the kernel and DTB from boot slot A, which matches the kernel version in rootfs slot A

#### Scenario: Boot partition is updated atomically with rootfs

- **WHEN** a RAUC bundle is installed
- **THEN** both the boot partition and rootfs partition for the target slot are written as a single operation

### Requirement: Initial provisioning script partitions and deploys first image

An initial provisioning script SHALL partition the eMMC, write U-Boot to the correct raw offset, create filesystems on
each partition, deploy the first kernel+DTB to boot slot A, deploy the first squashfs image to rootfs slot A, configure
U-Boot environment for booting, and format /persist as f2fs.

#### Scenario: First boot after provisioning

- **WHEN** the provisioning script completes and the device reboots
- **THEN** U-Boot loads the kernel from boot slot A, mounts rootfs slot A as the root filesystem, and the system reaches
  multi-user.target

#### Scenario: Provisioning script is idempotent

- **WHEN** the provisioning script is run a second time on an already-provisioned eMMC
- **THEN** the script SHALL warn that existing data will be destroyed and require explicit confirmation before
  proceeding

### Requirement: U-Boot is written at correct RK3328 offset

The provisioning script SHALL write U-Boot (idbloader.img and u-boot.itb) to the eMMC at the offsets required by the
RK3328 boot ROM (sector 64 for idbloader, sector 16384 for u-boot.itb). U-Boot SHALL be sourced from the nixpkgs
`ubootRock64` package.

#### Scenario: U-Boot loads from eMMC

- **WHEN** the Rock64 powers on with the provisioned eMMC
- **THEN** the RK3328 boot ROM finds and executes U-Boot from the expected eMMC offsets

### Requirement: /persist partition survives updates

The /persist partition SHALL NOT be modified by RAUC updates or rootfs slot switches. It SHALL persist across all
updates and rollbacks.

#### Scenario: Data survives an A/B slot switch

- **WHEN** a file is written to /persist, then an update switches the active slot from A to B
- **THEN** the file is still present and unmodified on /persist after the slot switch

### Requirement: Boot configuration uses U-Boot environment for slot selection

U-Boot SHALL use environment variables (`BOOT_ORDER`, `BOOT_A_LEFT`, `BOOT_B_LEFT`) to determine which boot slot to load
the kernel from and which rootfs partition to pass as the root device to the kernel.

#### Scenario: U-Boot selects correct slot pair

- **WHEN** U-Boot reads `BOOT_ORDER=A B` and `BOOT_A_LEFT=3`
- **THEN** U-Boot loads kernel and DTB from boot slot A and passes rootfs slot A's partition as the root device
