# Rock64 (RK3328) hardware-specific configuration.
# Kernel, device tree, U-Boot, and eMMC-specific settings.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  kernelConfig = import ./kernel-config.nix { inherit lib; };
  ubootEnvTools = config.atomixos.ubootEnvTools;
  watchdogDevice =
    {
      internal = "/dev/watchdog-internal";
      external = "/dev/watchdog-external";
    }
    .${config.atomixos.watchdog.backend};

  rock64KernelConfig = with lib.kernel; {
    # On-board audio: RK3328 codec through the I2S and SPDIF controllers.
    SND_SOC_RK3328 = lib.mkForce yes;
    SND_SOC_ROCKCHIP_I2S = lib.mkForce yes;
    SND_SOC_ROCKCHIP_SPDIF = lib.mkForce yes;
  };
in
{
  imports = [ ./hardware-rockchip.nix ];

  # The onboard RK3328 GMAC is the WAN port.
  atomixos.network.wanLinkMatch.Path = "platform-ff540000.ethernet";

  # ── Boot partition ────────────────────────────────────────────────────────────
  # Boot slot A's FAT partition, whichever slot is active; hardware-rockchip.nix
  # makes /boot an idle-unmounting automount.
  fileSystems."/boot" = {
    device = "/dev/mmcblk1p1";
    fsType = "vfat";
  };

  # Initrd repart cannot infer the backing disk from our overlay root, so point
  # it at the Rock64 eMMC device explicitly when creating the data partition.
  boot.initrd.systemd.repart.device = "/dev/mmcblk1";

  # ── U-Boot environment tools (fw_setenv / fw_printenv) ─────────────────────
  # Environment is stored on SPI flash (not eMMC) to avoid the eMMC raw write
  # bug. first-boot.service uses fw_setenv to confirm the boot slot.
  environment.systemPackages = [
    ubootEnvTools
    pkgs.i2c-tools
  ];
  environment.etc."fw_env.config".text = ''
    # MTD device for SPI flash env (matches U-Boot CONFIG_ENV_OFFSET/SIZE)
    # Device         Offset    Size      Erase-size
    /dev/mtd0        0x140000  0x2000    0x1000
  '';

  # ── Kernel ───────────────────────────────────────────────────────────────────

  boot.kernelPackages = pkgs.linuxPackagesFor (
    pkgs.linux_latest.override {
      enableCommonConfig = false;
      autoModules = false;
      ignoreConfigErrors = true;
    }
  );

  # Custom kernel configuration: strip to RK3328 essentials.
  # Built-in (=y): eMMC, Ethernet, USB host, watchdog, squashfs, f2fs.
  # Modules (=m): selected USB Ethernet and USB serial peripherals.
  boot.kernelPatches = [
    {
      name = "rock64-stripped";
      patch = null;
      structuredExtraConfig =
        kernelConfig.baseKernelConfig
        // kernelConfig.optionalKernelConfig
        // kernelConfig.rockchipKernelConfig
        // rock64KernelConfig;
    }
  ];

  # Select the watchdog implementation requested by immutable build policy.
  atomixos.watchdog.device = watchdogDevice;
  services.udev.extraRules = ''
    SUBSYSTEM=="watchdog", KERNEL=="watchdog*", KERNELS=="ff1a0000.watchdog", SYMLINK+="watchdog-internal"
    SUBSYSTEM=="watchdog", KERNEL=="watchdog*", KERNELS=="watchdog-external", SYMLINK+="watchdog-external"
  '';

  # Device tree for Rock64
  hardware.deviceTree = {
    enable = true;
    name = "rockchip/rk3328-rock64.dtb";
    overlays = [
      {
        name = "rock64-internal-watchdog";
        dtsFile = ../dts/rock64-internal-watchdog.dts;
      }
    ]
    ++
      lib.optional
        (config.atomixos.watchdog.enableHardware && config.atomixos.watchdog.backend == "external")
        {
          name = "rock64-i2c-header";
          dtsFile = ../dts/rock64-i2c-header.dts;
        };
  };

  # ── Hardware-specific settings ───────────────────────────────────────────────

  # Only include firmware for hardware we actually use (the RK3328 SoC needs
  # none for its built-in peripherals); hardware-rockchip.nix adds the USB NIC
  # blobs.
  hardware.enableRedistributableFirmware = lib.mkForce false;

  # The root filesystem is a squashfs partition selected by U-Boot
  # The actual root device is passed via kernel command line by U-Boot boot script
  boot.initrd.availableKernelModules = lib.mkForce [
    "mmc_block"
    "dw_mmc_rockchip"
    "squashfs"
    "f2fs"
    "overlay"
    "dm_mod"
  ];

  # ── RAUC slot device paths (eMMC) ──────────────────────────────────────────
  # These map to the GPT partition layout after initrd repartitioning:
  #   p1 = boot A (vfat), p2 = rootfs A, p3 = boot B (vfat), p4 = rootfs B
  atomixos.rauc = {
    enable = lib.mkDefault true;
    slots = {
      boot0 = "/dev/mmcblk1p1";
      boot1 = "/dev/mmcblk1p3";
      rootfs0 = "/dev/mmcblk1p2";
      rootfs1 = "/dev/mmcblk1p4";
    };
  };

  # ── Serial console (UART2) ─────────────────────────────────────────────────
  # hardware-rockchip.nix enables the ttyS2 getty and the `_RUT_OH_` serial
  # root recovery on the Rock64's 3-pin header.
}
