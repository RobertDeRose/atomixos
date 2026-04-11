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

  # ── RAUC slot device paths (virtio block devices) ──────────────────────────
  # When launched with the test runner (scripts/run-qemu-rauc-test.sh), QEMU
  # attaches four extra virtio-blk disks for A/B slot testing:
  #   vdb = boot A (vfat, 128 MB)
  #   vdc = boot B (vfat, 128 MB)
  #   vdd = rootfs A (1 GB)
  #   vde = rootfs B (1 GB)
  #
  # The primary disk (vda) is the NixOS root filesystem.
  atomixos.rauc.slots = {
    boot0 = "/dev/vdb";
    boot1 = "/dev/vdc";
    rootfs0 = "/dev/vdd";
    rootfs1 = "/dev/vde";
  };

  # Use custom bootloader backend in QEMU — simulates U-Boot boot selection
  # via plain files instead of fw_setenv/fw_printenv.
  atomixos.rauc.bootloader = "custom";
}
