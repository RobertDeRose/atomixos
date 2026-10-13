# Radxa ROCK 3 Compute Module (CM3/RK3566) on the Radxa CM3 IO Board.
# This is intentionally separate from the RK3328 Rock64 hardware module.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  # The CM3 device tree aliases mmc0 to the on-module eMMC (sdhci, fe310000)
  # and mmc1 to the IO board SD slot, so /dev/mmcblk0 is always the eMMC.
  # Use fixed eMMC paths: every AtomixOS image shares the same GPT labels, so
  # by-partlabel could resolve to an inserted SD card.
  emmc = "/dev/mmcblk0";
in
{
  imports = [ ./hardware-rockchip.nix ];

  atomixos.board = "cm3";
  atomixos.watchdog.device = "/dev/watchdog-internal";

  # build.toml is shared with ROCK64, whose default backend is external. The
  # CM3 always uses the internal watchdog device, so warn instead of failing.
  warnings = lib.optional (
    config.atomixos.watchdog.enableHardware && config.atomixos.watchdog.backend == "external"
  ) "CM3 IO has no external watchdog; using the internal RK3566 watchdog (fe600000).";

  # Start with the stock upstream kernel: the Rock64's aggressively stripped
  # RK3328 config excludes critical RK3566 eMMC/SDHCI and PMIC drivers.
  boot.kernelPackages = pkgs.linuxPackages_latest;
  hardware.deviceTree = {
    enable = true;
    name = "rockchip/rk3566-radxa-cm3-io.dtb";
  };
  boot.initrd.availableKernelModules = [
    "mmc_block"
    "sdhci"
    "sdhci_pltfm"
    "sdhci_of_dwcmshc"
    # initrd-prepare-overlay-lower mounts the squashfs slot. The stock kernel
    # builds squashfs (and the eMMC host drivers) in, so these entries only
    # matter if the kernel config changes.
    "squashfs"
  ];

  # The first 16 MiB contains Rockchip SPL, U-Boot, and redundant environments;
  # hardware-rockchip.nix keeps systemd-repart from trimming it.
  boot.initrd.systemd.repart.device = emmc;
  fileSystems."/boot" = {
    device = "${emmc}p1";
    fsType = "vfat";
  };
  fileSystems."/data".device = lib.mkForce "${emmc}p5";

  # The U-Boot environment is in the eMMC user area; two 32KiB copies avoid
  # losing the RAUC slot state during an interrupted write.
  environment.etc."fw_env.config".text = ''
    ${emmc} 0x3F8000 0x8000
    ${emmc} 0x3F0000 0x8000
  '';
  environment.systemPackages = [
    config.atomixos.ubootEnvTools
    pkgs.i2c-tools
  ];

  atomixos.rauc = {
    enable = lib.mkDefault true;
    compatible = "radxa-cm3-io";
    slots = {
      boot0 = "${emmc}p1";
      boot1 = "${emmc}p3";
      rootfs0 = "${emmc}p2";
      rootfs1 = "${emmc}p4";
    };
  };

  # RK3566 GMAC1 is at fe010000; Rock64's NIC match targets ff540000.
  systemd.network.links."10-onboard-eth".matchConfig.Path = lib.mkForce "platform-fe010000.ethernet";

  # RK3566 watchdog differs from Rock64 (ff1a0000).
  services.udev.extraRules = ''
    SUBSYSTEM=="watchdog", KERNEL=="watchdog*", KERNELS=="fe600000.watchdog", SYMLINK+="watchdog-internal"
  '';
}
