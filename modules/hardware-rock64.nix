# Rock64 (RK3328) hardware-specific configuration.
# Kernel, device tree, U-Boot, and eMMC-specific settings.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Boot configuration ───────────────────────────────────────────────────────

  # U-Boot handles booting — no bootloader managed by NixOS
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = false;

  # ── Kernel ───────────────────────────────────────────────────────────────────

  boot.kernelPackages = pkgs.linuxPackages_latest;

  # Custom kernel configuration: strip to RK3328 essentials
  # Built-in (=y): eMMC, ethernet, USB host, watchdog, squashfs, f2fs
  # Modules (=m): WiFi, Bluetooth, USB serial (for optional USB peripherals)
  boot.kernelPatches = [
    {
      name = "rock64-stripped";
      patch = null;
      structuredExtraConfig = with lib.kernel; {
        # ── Built-in drivers (essential for boot) ──
        # mkForce is needed where nixpkgs common-config.nix sets =m but we need =y
        # eMMC / SD
        MMC = lib.mkForce yes;
        MMC_DW = lib.mkForce yes;
        MMC_DW_ROCKCHIP = lib.mkForce yes;

        # Ethernet (stmmac / GMAC)
        STMMAC_ETH = lib.mkForce yes;
        STMMAC_PLATFORM = lib.mkForce yes;
        DWMAC_ROCKCHIP = lib.mkForce yes;

        # USB host
        USB = lib.mkForce yes;
        USB_DWC2 = lib.mkForce yes;
        USB_XHCI_HCD = lib.mkForce yes;
        USB_EHCI_HCD = lib.mkForce yes;
        USB_OHCI_HCD = lib.mkForce yes;

        # Watchdog
        DW_WATCHDOG = lib.mkForce yes;

        # Filesystems
        SQUASHFS = lib.mkForce yes;
        SQUASHFS_XZ = lib.mkForce yes;
        SQUASHFS_ZSTD = lib.mkForce yes;
        F2FS_FS = lib.mkForce yes;

        # ── Modules (optional USB peripherals) ──
        # WiFi
        RTL8XXXU = lib.mkForce module;
        ATH9K_HTC = lib.mkForce module;
        MT76_USB = lib.mkForce module;
        MT7601U = lib.mkForce module;
        MT7663U = lib.mkForce module;
        RTW88 = lib.mkForce module;
        RTW89 = lib.mkForce module;

        # Bluetooth
        BT = lib.mkForce module;
        BT_HCIBTUSB = lib.mkForce module;

        # USB serial
        USB_SERIAL = lib.mkForce module;
        USB_SERIAL_FTDI_SIO = lib.mkForce module;
        USB_SERIAL_CP210X = lib.mkForce module;

        # ── Workarounds for removed options in kernel 6.19+ ──
        # USB_SERIAL_CONSOLE was removed; unset to avoid "unused option" error
        # from nixpkgs common-config.nix
        USB_SERIAL_CONSOLE = lib.mkForce unset;
      };
    }
  ];

  # Device tree for Rock64
  hardware.deviceTree = {
    enable = true;
    name = "rockchip/rk3328-rock64.dtb";
  };

  # ── Hardware-specific settings ───────────────────────────────────────────────

  # Only include firmware for hardware we actually use.
  # enableRedistributableFirmware = true would pull in ALL linux-firmware (~700 MB).
  # The RK3328 SoC doesn't need runtime firmware for its built-in peripherals
  # (eMMC, Ethernet, USB). WiFi dongle firmware will be added selectively
  # when specific USB WiFi hardware is chosen.
  hardware.enableRedistributableFirmware = lib.mkForce false;

  # The root filesystem is a squashfs partition selected by U-Boot
  # The actual root device is passed via kernel command line by U-Boot boot script
  boot.initrd.availableKernelModules = [
    "squashfs"
    "f2fs"
    "mmc_block"
    "dw_mmc_rockchip"
  ];
}
