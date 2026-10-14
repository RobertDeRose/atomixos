# Flashable Disk Image

Build a complete `.img` file that can be written to eMMC (or SD card) using `dd` or any raw disk writer.

## Build the Image

```sh
# Build ROCK64 (default: .gcroots/rock64/current/image/)
mise run build

# Build the Radxa CM3 IO Board (.gcroots/cm3/current/image/)
mise run build --board cm3

# Copy a specific board image to a path
mise run build --board rock64 -o atomixos-rock64-26.05.img

# Build via Lima VM
mise run build -- --board cm3 --lima

# Or with Nix directly (result stays in Nix store)
nix build .#rock64.image -o result-rock64-image
nix build .#cm3.image -o result-cm3-image
```

## Flash to eMMC

### macOS

Connect the eMMC module via a USB adapter. Identify the device (usually `/dev/disk4`):

```sh
diskutil list
```

Flash using the mise task:

```sh
# Flash the latest build of the only board you have built
mise run flash /dev/disk4

# With builds for both boards, choose one
mise run flash --board cm3 /dev/disk4

# Specify image explicitly
mise run flash -i atomixos-rock64-26.05.img /dev/disk4

# Skip confirmation prompt
mise run flash -y /dev/disk4
```

The flash task automatically:

- Uses `.gcroots/<board>/current/image/` unless `-i` names an image. Without `--board`, it uses the only board with a
  build and refuses to guess when both have one, so a ROCK64 image is never written to a CM3 eMMC by default
- Converts `/dev/diskN` to `/dev/rdiskN` (raw device for faster writes)
- On macOS, unmounts all partitions on the target disk and refuses to write to the boot disk
- On Linux, writes only a whole removable or USB disk that nothing uses, as `lsblk` reports it; the same disks are
  offered when no disk is given. A disk is in use when any partition or volume on it (including through LVM, LUKS, or
  RAID) is mounted or is swap, or when it carries a `zfs_member`, `LVM2_member`, `linux_raid_member`, `crypto_LUKS`,
  or `swap` signature. Unmount the disk first; clear an old signature with `wipefs -a`. Flash never unmounts on Linux,
  and checks the disk again after confirmation, in case it was mounted while the prompt waited
- Runs `dd` with `bs=4M` and progress reporting
- Syncs and ejects when done

When the board exposes its eMMC through U-Boot USB mass storage (`START_UMS` or `ums 0 mmc 0`), any host eject ends
`ums`. U-Boot reports that as `CTRL+C - Operation aborted`, and the disk disappears. On macOS, the "disk not readable"
dialog ejects the disk if you choose **Eject**, so choose **Ignore** and let the flash task unmount the disk. The flash
task's own eject at the end also ends `ums`, which then returns the board to the U-Boot prompt.

### Linux

```sh
# With mise: pick from the removable or USB disks, or name one (add --board with builds for both boards)
mise run flash
mise run flash -y /dev/sdb

# With dd directly (select the correct image and target disk)
sudo dd if=atomixos-rock64-26.05.img of=/dev/sdb bs=4M status=progress
sudo sync
```

## What's in the Image

The flashable image contains:

| Region                 | Content                                    |
|------------------------|--------------------------------------------|
| Raw (0-16 MB)          | U-Boot (idbloader + u-boot.itb)            |
| Partition 1 (boot-a)   | Kernel Image, initrd, DTB, boot.scr (vfat) |
| Partition 2 (rootfs-a) | Squashfs root filesystem                   |

The image intentionally does not include slot B or `/data`. On first boot,
initrd `systemd-repart` creates `boot-b` (vfat), `rootfs-b`, and `/data`
(`f2fs`) using the remaining eMMC space before the real system mounts it.

## First Boot Provisioning

The flashable image method does **not** embed credentials in the image. After
flashing, the device boots into the local provisioning flow and imports operator
configuration into `/data/config/` from one of these sources:

- `/boot/config.toml` on a fresh flash
- USB `config.toml` (USB discovery does not select bundle archives; bundle imports are available through the API, Boot UI,
  and compatibility CLI)
- the bootstrap web console on WAN and LAN port `8080` until initial provisioning completes

When a new `config.toml` or supported bundle is applied through one of those
paths, the device persists canonical state under `/data/config/`, writes admin SSH authorized keys, renders the
declared Quadlet units, and continues first boot without requiring a second
reboot.

Reprovisioning is done by wiping `/data` and rebooting. Because initrd only
treats `/boot/config.toml` as a seed on a true fresh flash, reprovisioning uses
USB `config.toml` first and then falls back to the bootstrap UI instead of
replaying an old `/boot/config.toml`.

The image keeps `root` locked and does not ship a built-in operator account. On every
board, `_RUT_OH_=1` enables a deterministic serial-only root recovery path on UART2
(`ttyS2`, 1.5 Mbaud) for the next boot; see
[Physical Recovery](../architecture/authentication.md#physical-recovery).

## Production RAUC Signing

Repository defaults build and trust the development RAUC signing material in `certs/`. Do not ship those defaults in a
production OTA fleet.

Production images must set `atomixos.rauc.keyringCert` to the production CA certificate and set
`atomixos.rauc.allowDevelopmentKeyring = false`. Production RAUC bundles must be built by overriding the
`rauc-bundle` derivation inputs `signingCert` and `signingKeyPath` with the matching production signing certificate and
private key.

Keep the RAUC private signing key outside the image closure and out of the repository. The image should contain only the
public CA certificate used by RAUC to verify installed bundles.
