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

  kernelConfig = import ./kernel-config.nix { inherit lib; };

  # RK3566 and CM3 IO drivers on top of the shared Rockchip layer. Most are
  # already =y in the arm64 defconfig; forcing them keeps boot-critical
  # hardware built in if that defconfig changes.
  cm3KernelConfig = with lib.kernel; {
    # On-module eMMC (rk3568-dwcmshc) and its I/O voltage domains.
    MMC_SDHCI = lib.mkForce yes;
    MMC_SDHCI_PLTFM = lib.mkForce yes;
    MMC_SDHCI_OF_DWCMSHC = lib.mkForce yes;
    ROCKCHIP_IODOMAIN = lib.mkForce yes;
    ROCKCHIP_PM_DOMAINS = lib.mkForce yes;

    # Power: RK809 PMIC (rk817 driver family) and the TCS4525 CPU regulator.
    REGULATOR_FAN53555 = lib.mkForce yes;

    # CPU clock and frequency scaling go through SCMI firmware on RK356x.
    ARM_SCMI_PROTOCOL = lib.mkForce yes;
    COMMON_CLK_SCMI = lib.mkForce yes;
    ARM_SCMI_CPUFREQ = lib.mkForce yes;

    # No audio: the CM3 IO device tree defines no RK809 codec card, and its
    # HDMI sound card needs the display drivers this kernel leaves out.
  };
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

  # Same stripped kernel as the ROCK64, plus the RK3566 drivers above.
  boot.kernelPackages = pkgs.linuxPackagesFor (
    pkgs.linux_latest.override {
      enableCommonConfig = false;
      autoModules = false;
      ignoreConfigErrors = true;
    }
  );
  boot.kernelPatches = [
    {
      name = "cm3-stripped";
      patch = null;
      structuredExtraConfig =
        kernelConfig.baseKernelConfig
        // kernelConfig.optionalKernelConfig
        // kernelConfig.rockchipKernelConfig
        // cm3KernelConfig;
    }
  ];
  hardware.deviceTree = {
    enable = true;
    name = "rockchip/rk3566-radxa-cm3-io.dtb";
  };
  # The stripped kernel builds these in; replace the NixOS defaults, which name
  # modules (SATA, NVMe, USB HID) this kernel does not build.
  boot.initrd.availableKernelModules = lib.mkForce [
    "mmc_block"
    "sdhci_of_dwcmshc"
    "squashfs"
    "f2fs"
    "overlay"
    "dm_mod"
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

  # The onboard RK3566 GMAC1 is the WAN port.
  atomixos.network.wanLinkMatch.Path = "platform-fe010000.ethernet";

  # RK3566 watchdog differs from Rock64 (ff1a0000).
  services.udev.extraRules = ''
    SUBSYSTEM=="watchdog", KERNEL=="watchdog*", KERNELS=="fe600000.watchdog", SYMLINK+="watchdog-internal"
  '';
}
