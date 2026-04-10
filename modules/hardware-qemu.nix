# QEMU aarch64-virt hardware configuration for development/testing.
# Shares all service configuration from base.nix but targets virtual hardware.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Boot configuration ───────────────────────────────────────────────────────

  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = true;

  # ── Kernel ───────────────────────────────────────────────────────────────────

  boot.kernelPackages = pkgs.linuxPackages_latest;

  # QEMU virtio drivers
  boot.initrd.availableKernelModules = [
    "virtio_pci"
    "virtio_blk"
    "virtio_net"
    "virtio_scsi"
    "squashfs"
    "f2fs"
  ];

  # ── Virtual hardware ─────────────────────────────────────────────────────────

  # QEMU uses software watchdog
  # (systemd watchdog config from watchdog.nix still applies,
  #  but hardware watchdog is simulated)

  # Virtual block devices for A/B slot testing
  # In QEMU, we use files as virtual disks
}
