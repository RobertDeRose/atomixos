# Settings shared by the Rockchip boards (ROCK64/RK3328, CM3/RK3566).
# Board modules import this and add their kernel, device tree, storage paths,
# and U-Boot environment location.
{
  lib,
  pkgs,
  ...
}:
{
  # U-Boot handles booting — no bootloader managed by NixOS
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = false;

  # Keep both stage-1 and stage-2 aware of the filesystems we provision in the
  # initrd so the required mkfs/fsck helpers are available to systemd-repart.
  boot.supportedFilesystems = [
    "vfat"
    "f2fs"
  ];
  boot.initrd.supportedFilesystems = [
    "vfat"
    "f2fs"
  ];

  # /boot is boot slot A, which RAUC overwrites when B is running, and RAUC
  # refuses to install to a mounted slot. Mount it only on access (first-boot
  # reads the fresh-flash /boot/config.toml seed) and unmount it when idle, so
  # it is not mounted during later updates.
  fileSystems."/boot".options = [
    "noauto"
    "x-systemd.automount"
    "x-systemd.idle-timeout=1min"
  ];

  # The eMMC gap before the first GPT partition holds SPL and U-Boot (and on
  # CM3 the U-Boot environment). systemd-repart's default discard pass trims
  # that gap, which destroys the bootloader and breaks subsequent reboots.
  boot.initrd.systemd.repart.discard = false;

  # Realtek RTL8153 USB NIC revisions request rtl_nic patch blobs. Install only
  # those instead of all of linux-firmware (~700 MB).
  hardware.firmware = [ (pkgs.callPackage ../nix/rtl815x-firmware.nix { }) ];

  # Login prompt on the debug serial console (UART2, ttyS2 @ 1.5 Mbaud).
  systemd.services."serial-getty@ttyS2" = {
    enable = true;
    wantedBy = [ "getty.target" ];
    serviceConfig.Restart = "always";
  };

  # boot-storage-debug probes ROCK64's SPI NOR and mmcblk1; keep it off on
  # normal images.
  systemd.services.boot-storage-debug.wantedBy = lib.mkForce [ ];
}
