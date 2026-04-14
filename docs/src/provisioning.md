# Provisioning

There are two ways to deploy AtomixOS to a Rock64 device:

1. **[Flashable disk image](./provisioning/flash-image.md)** -- build an `.img` file and write it to eMMC with `dd`.
   Suitable for development and small-scale deployment.

2. **[Direct eMMC provisioning](./provisioning/emmc-provisioning.md)** -- partition, format, and populate the eMMC
   directly from build artifacts. Includes credential provisioning for EN18031 compliance. Suitable for factory
   deployment.

Both methods produce the same partition layout. The difference is that direct provisioning also creates the `/persist`
partition and populates it with per-device credentials, while the flashable image defers `/persist` creation to first
boot via `systemd-repart`.

## After Provisioning

On first boot:

1. U-Boot loads `boot.scr` from boot-a, boots the kernel with initrd
2. The kernel mounts the squashfs rootfs read-only
3. `systemd-repart` creates the `/persist` partition (if using flash image method)
4. `first-boot.service` marks the RAUC slot as good and writes the sentinel file
5. Network interfaces come up (eth0 via DHCP, eth1 static)
6. Services start: dnsmasq, chrony, sshd, os-upgrade timer

The device is then ready to receive OTA updates and serve LAN clients.
