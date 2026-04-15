# Flashable Disk Image

Build a complete `.img` file that can be written to eMMC (or SD card) using `dd` or any raw disk writer.

## Build the Image

```sh
# Build with mise (copies .img to current directory)
mise run build:image

# Specify output path
mise run build:image -- -o atomixos-25.11.img

# Build via Lima VM
mise run build:image -- --lima

# Or with Nix directly (result stays in Nix store, symlinked to result-image/)
nix build .#image -o result-image
```

## Flash to eMMC

### macOS

Connect the eMMC module via a USB adapter. Identify the device (usually `/dev/disk4`):

```sh
diskutil list
```

Flash using the mise task:

```sh
# Auto-detect image, specify target disk
mise run flash /dev/disk4

# Specify image explicitly
mise run flash -i atomixos-25.11.img /dev/disk4

# Skip confirmation prompt
mise run flash -y /dev/disk4
```

The flash task automatically:

- Converts `/dev/diskN` to `/dev/rdiskN` (raw device for faster writes)
- Unmounts all partitions on the target disk
- Refuses to write to the macOS boot disk
- Runs `dd` with `bs=4M` and progress reporting
- Syncs and ejects when done

### Linux

```sh
# With mise
mise run flash -y /dev/mmcblk0

# With dd directly
sudo dd if=atomixos-25.11.img of=/dev/mmcblk0 bs=4M status=progress
sudo sync
```

## What's in the Image

The flashable image contains:

| Region                 | Content                                     |
|------------------------|---------------------------------------------|
| Raw (0-16 MB)          | U-Boot (idbloader + u-boot.itb)             |
| Partition 1 (boot-a)   | Kernel Image, initrd, DTB, boot.scr (vfat)  |
| Partition 2 (boot-b)   | Empty vfat (populated by first RAUC update) |
| Partition 3 (rootfs-a) | Squashfs root filesystem                    |
| Partition 4 (rootfs-b) | Empty (populated by first RAUC update)      |

The `/persist` partition is **not** in the image. It is created automatically on first boot by `systemd-repart`.

## Limitations

The flashable image method does **not** provision credentials. After flashing:

- The `admin` user has no password and no SSH key
- Cockpit and Traefik have no configuration
- The health manifest is empty

Credentials must be deployed manually to `/persist/config/` after first boot, or pre-populated on the persist partition.

For development, the `root` user has an empty password and serial console access on UART2 (ttyS2, 1.5 Mbaud).
