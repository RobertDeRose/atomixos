# Provisioning

Deploy AtomixOS to a Rock64 device by building a [flashable disk image](./provisioning/flash-image.md) and writing it
to eMMC with `dd` (or `mise run flash`).

## After Provisioning

On first boot:

1. U-Boot loads `boot.scr` from boot-a, boots the kernel with initrd
2. The kernel mounts the squashfs rootfs read-only
3. `systemd-repart` creates the `/persist` partition (f2fs, remaining eMMC space)
4. `first-boot.service` marks the RAUC slot as good and writes the sentinel file
5. Network interfaces come up (eth0 via DHCP, eth1 static)
6. Services start: dnsmasq, chrony, sshd, os-upgrade timer

The device is then ready to receive OTA updates and serve LAN clients.
