# Partition Layout

Acceptance contract for the eMMC layout. `nix/partition-layout.nix` is the single source of these values; the
[Partition Layout](../architecture/partition-layout.md) architecture page explains the design.

## Requirements

### eMMC A/B layout

The eMMC holds raw U-Boot, two A/B slot pairs (boot and rootfs), and a persistent data partition that uses the
remaining space. The flashable image contains slot A only; initrd `systemd-repart` creates slot B and `/data` on first
boot.

| Region     | Start      | Size                             | Type (GUID)                                         | Filesystem |
|------------|------------|----------------------------------|-----------------------------------------------------|------------|
| U-Boot     | 0          | 16 MiB                           | Raw, no partition                                   | --         |
| `boot-a`   | 16 MiB     | 128 MiB                          | xbootldr (`BC13C2FF-59E6-4262-A352-B275FD6F7172`)   | vfat       |
| `rootfs-a` | 144 MiB    | 1024 MiB                         | root-arm64 (`B921B045-1DF0-41C3-AF44-4C6F280D3FAE`) | squashfs   |
| `boot-b`   | first boot | 128 MiB                          | xbootldr                                            | vfat       |
| `rootfs-b` | first boot | 1024 MiB                         | root-arm64                                          | squashfs   |
| `data`     | first boot | remaining space, at least 64 MiB | linux-generic                                       | f2fs       |

#### Scenario: Partition table matches the layout

- Given a freshly flashed eMMC
- Then `sfdisk -d` shows two GPT partitions, `boot-a` and `rootfs-a`
- And the raw region from 0 to 16 MiB contains U-Boot
- And after the first boot, initrd `systemd-repart` has created three more GPT partitions labeled `boot-b`, `rootfs-b`,
  and `data`
- And `/data` (f2fs) uses the remaining space

### Per-slot boot partitions

Each slot pair has its own vfat boot partition holding the kernel, initrd, DTB, and boot script, so boot and rootfs are
always consistent for a slot.

#### Scenario: Boot partition contents match the slot

- Given slot A is active
- Then `boot-a` contains `Image`, `initrd`, the board's DTB under `dtbs/` (for example
  `dtbs/rockchip/rk3328-rock64.dtb`), and `boot.scr`
- And `boot-b` is absent before first boot, or holds the other slot's kernel afterward

### Flashable disk image

`mise run build` (with `--board cm3` for the CM3) produces a 1170 MiB `.img` holding U-Boot, `boot-a`, `rootfs-a`, and 2
MiB of GPT tail slack. The rest of the eMMC is left unallocated for `systemd-repart`.

### U-Boot at Rockchip boot ROM offsets

U-Boot is written as raw data at the offsets the RK3328 and RK3566 boot ROMs expect:

- `idbloader.img` at sector 64 (byte offset 32 KiB)
- `u-boot.itb` at sector 16384 (byte offset 8 MiB)

Both come from the board's U-Boot package, built by `nix/uboot.nix` (Rock64) or `nix/uboot-cm3.nix` (CM3).

#### Scenario: U-Boot loads from eMMC

- Given U-Boot is written at these offsets
- When the board powers on
- Then the serial console shows U-Boot starting
- And `bootflow scan` finds `boot.scr` on `boot-a`

### /data survives updates

RAUC slot writes and slot switches never modify `/data`. Container data, configuration, and credentials persist across
every update and rollback.

#### Scenario: Data survives an update

- Given a file exists at `/data/config/test-file`
- When a RAUC update installs a new image and the device reboots
- Then `/data/config/test-file` still exists with the same content

### U-Boot environment selects the slot

The U-Boot variables `BOOT_ORDER`, `BOOT_A_LEFT`, and `BOOT_B_LEFT` decide which slot boots and how many attempts
remain. They are stored in SPI flash on Rock64 and as two redundant copies in the eMMC boot gap on the CM3 (see
[Boot and Rollback](boot-rollback.md#board-specific-u-boot-environment)). Linux seeds them on first boot when they are
missing.

#### Scenario: Environment survives power loss

- Given `BOOT_ORDER` is set to `B A`
- When power is lost during an environment write
- Then U-Boot falls back to its compiled defaults or the last valid saved environment
