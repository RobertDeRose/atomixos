# Provisioning

Deploy AtomixOS to a Rock64 device by building a [flashable disk image](./provisioning/flash-image.md) and writing it
to eMMC with `dd` (or `mise run flash`).

## After Provisioning

On first boot:

1. U-Boot loads `boot.scr` from boot-a, echoes build ID, boots the kernel with initrd
2. The initrd mounts the squashfs rootfs, then `postMountCommands` converts it to an
   OverlayFS root (squashfs lower + tmpfs upper) before `switch_root`
3. The image boots with a built-in `/persist` partition (f2fs, currently fixed-size)
4. `first-boot.service` unconditionally marks the RAUC slot as good (no network dependency) and writes the sentinel file
5. Network interfaces come up (eth0 via DHCP, eth1 static); `systemd-networkd-wait-online` uses 30s timeout with `anyInterface=true`
6. Services start: dnsmasq, chrony, sshd, os-upgrade timer

The device is then ready to receive OTA updates and serve LAN clients.

## USB Recovery Mode

If the reset button is held from power-on for 10 seconds, U-Boot enters USB
mass storage mode instead of booting Linux. The
Rock64 OTG USB port then exposes the full eMMC as a removable disk, allowing the host to write a fresh image directly.
