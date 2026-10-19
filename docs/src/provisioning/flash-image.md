# Flash an Image

Build a raw `.img` disk image and write it to the device's eMMC (or an SD card) with `mise run flash`, `dd`, or any raw
disk writer.

## Build the image

```sh
# Build the Rock64 image (the default board), kept under .gcroots/rock64/current/image/
mise run build

# Build the Radxa CM3 IO Board image, kept under .gcroots/cm3/current/image/
mise run build --board cm3

# Also copy the image to a path of your choice
mise run build --board rock64 -o atomixos-rock64-26.05.img

# Build inside a Lima VM
mise run build -- --board cm3 --lima

# Or build with Nix directly; the result stays in the Nix store
nix build .#rock64.image -o result-rock64-image
nix build .#cm3.image -o result-cm3-image
```

[Building](../building.md) covers prerequisites, local build overrides, and the other artifacts.

## Write it to the eMMC

The `flash` task picks the image for you. Without `-i`, it uses `.gcroots/<board>/current/image/`. Without `--board`, it
uses the only board you have built, and it refuses to guess when both boards have a build, so it never writes a Rock64
image to a CM3 eMMC by default.

### macOS

1. Connect the eMMC module through a USB adapter, or expose the board's eMMC over USB mass storage (see
   [USB mass storage](#usb-mass-storage) below).
2. Find its device name, usually `/dev/disk4`:

   ```sh
   diskutil list
   ```

3. Flash it:

   ```sh
   # Flash the latest build of the only board you have built
   mise run flash /dev/disk4

   # With builds for both boards, choose one
   mise run flash --board cm3 /dev/disk4

   # Use a specific image
   mise run flash -i atomixos-rock64-26.05.img /dev/disk4

   # Skip the confirmation prompt
   mise run flash -y /dev/disk4
   ```

On macOS the task writes to the raw device (`/dev/rdiskN`) for speed, unmounts the disk's partitions first, and refuses
to write to the boot disk. It runs `dd` with `bs=4M` and progress output, then syncs and ejects the disk.

### Linux

```sh
# Pick from the removable or USB disks, or name one (add --board when both boards have a build)
mise run flash
mise run flash -y /dev/sdb

# Or with dd directly; choose the right image and target disk
sudo dd if=atomixos-rock64-26.05.img of=/dev/sdb bs=4M status=progress
sudo sync
```

On Linux the task writes only to a whole removable or USB disk that nothing is using, as `lsblk` reports it; with no
disk named, it offers those disks. A disk is in use when any partition or volume on it, including through LVM, LUKS, or
RAID, is mounted or is swap, or when it carries a `zfs_member`, `LVM2_member`, `linux_raid_member`, `crypto_LUKS`, or
`swap` signature. The task never unmounts anything on Linux:

1. Unmount the disk yourself.
2. Clear an old signature with `wipefs -a` if needed.
3. Run the task. It checks the disk again after you confirm, in case something mounted it while the prompt waited.

### USB mass storage

When a board exposes its eMMC through U-Boot USB mass storage (`START_UMS` or `ums 0 mmc 0`), any eject from the host
ends `ums`. U-Boot reports `CTRL+C - Operation aborted`, and the disk disappears. On macOS, the "disk not readable"
dialog ejects the disk if you choose **Eject**, so choose **Ignore** and let the flash task unmount it. The task's own
eject at the end also ends `ums`. A `START_UMS` or reset-button session then resets the board into the new image; a
`ums 0 mmc 0` typed at the U-Boot prompt returns to that prompt.

To rewrite a device that is already installed, put it into USB mass-storage mode first; see
[Recover a device](../provisioning.md#recover-a-device).

## What the image contains

| Region                   | Content                                       |
|--------------------------|-----------------------------------------------|
| Raw (0–16 MB)            | U-Boot (`idbloader` and `u-boot.itb`)         |
| Partition 1 (`boot-a`)   | Kernel, initrd, device tree, `boot.scr` (FAT) |
| Partition 2 (`rootfs-a`) | squashfs root filesystem                      |

The image holds slot A only. On the first boot the initrd creates `boot-b` (FAT), `rootfs-b`, and the `/data` partition
(f2fs) in the rest of the eMMC. [Partition Layout](../architecture/partition-layout.md) shows the final layout.

The image contains no credentials. Next, [provision the device](../provisioning.md).

## Sign production images with your own keys

By default the repository builds and trusts the development RAUC signing material in `certs/`. Do not ship those
defaults to a production fleet:

1. Set `atomixos.rauc.keyringCert` to your production CA certificate and set
   `atomixos.rauc.allowDevelopmentKeyring = false`. Evaluation fails if you disable the development keyring without
   providing a certificate.
2. Build RAUC bundles with the `rauc-bundle` derivation's `signingCert` and `signingKeyPath` inputs overridden with
   your production signing certificate and key.
3. Keep the private signing key outside the repository and the image. The image needs only the public CA certificate.

The options are described in [NixOS Modules](../code-reference/modules.md) and
[Nix Derivations](../code-reference/derivations.md).
