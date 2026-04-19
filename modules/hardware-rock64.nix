# Rock64 (RK3328) hardware-specific configuration.
# Kernel, device tree, U-Boot, and eMMC-specific settings.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Boot partition ────────────────────────────────────────────────────────────
  # Mount the active boot slot's FAT partition at /boot (slot A).
  fileSystems."/boot" = {
    device = "/dev/mmcblk1p1";
    fsType = "vfat";
  };

  # ── U-Boot environment tools (fw_setenv / fw_printenv) ─────────────────────
  # Environment is stored on SPI flash (not eMMC) to avoid the eMMC raw write
  # bug. first-boot.service uses fw_setenv to confirm the boot slot.
  environment.systemPackages = [ pkgs.ubootTools ];
  environment.etc."fw_env.config".text = ''
    # MTD device for SPI flash env (matches U-Boot CONFIG_ENV_OFFSET/SIZE)
    # Device         Offset    Size      Erase-size
    /dev/mtd0        0x140000  0x2000    0x1000
    /dev/mtd0        0x142000  0x2000    0x1000
  '';

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
        # ══════════════════════════════════════════════════════════════════
        # STRIPPED KERNEL CONFIG FOR ROCK64 GATEWAY
        # Stock NixOS builds ~7500 modules. We disable unused subsystems
        # at the top level to cascade-eliminate thousands of options.
        # ══════════════════════════════════════════════════════════════════

        # ── Built-in drivers (essential for boot) ──
        # mkForce needed where nixpkgs common-config.nix sets =m but we need =y

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

        # SPI flash (for U-Boot env on mtd0)
        SPI = lib.mkForce yes;
        SPI_ROCKCHIP = lib.mkForce yes;
        MTD = lib.mkForce yes;
        MTD_SPI_NOR = lib.mkForce yes;

        # Watchdog
        DW_WATCHDOG = lib.mkForce yes;

        # Filesystems
        SQUASHFS = lib.mkForce yes;
        SQUASHFS_XZ = lib.mkForce yes;
        SQUASHFS_ZSTD = lib.mkForce yes;
        F2FS_FS = lib.mkForce yes;
        OVERLAY_FS = lib.mkForce yes;

        # USB serial (for debug adapters)
        USB_SERIAL = lib.mkForce module;
        USB_SERIAL_FTDI_SIO = lib.mkForce module;
        USB_SERIAL_CP210X = lib.mkForce module;

        # ── Audio (Rock64 built-in I2S) ──
        # Keep SOUND + SND_SOC + Rockchip I2S, disable everything else
        SND_SOC_RK3328 = lib.mkForce module;
        SND_SOC_ROCKCHIP_I2S = lib.mkForce module;

        # ── DISABLED SUBSYSTEMS ──────────────────────────────────────────
        # Each of these eliminates hundreds of config options downstream.

        # No display/GPU (~420 options)
        DRM = lib.mkForce no;

        # No cameras, TV tuners, DVB (~200+ options)
        MEDIA_SUPPORT = lib.mkForce no;

        # No WiFi (re-enable when USB dongle hardware is selected)
        WLAN = lib.mkForce no;

        # No Bluetooth (re-enable when USB dongle hardware is selected)
        BT = lib.mkForce no;

        # No CAN bus (~70 options)
        CAN = lib.mkForce no;

        # No InfiniBand (~35 options)
        INFINIBAND = lib.mkForce no;

        # No NFC (~30 options)
        NFC = lib.mkForce no;

        # No DAQ/data acquisition hardware (~90 options)
        COMEDI = lib.mkForce no;

        # No FireWire
        FIREWIRE = lib.mkForce no;

        # No PCMCIA/CardBus
        PCCARD = lib.mkForce no;

        # No parallel port
        PARPORT = lib.mkForce no;

        # No game ports
        GAMEPORT = lib.mkForce no;

        # No FPGA
        FPGA = lib.mkForce no;

        # No IIO (industrial I/O sensors)
        IIO = lib.mkForce no;

        # No input devices we don't have
        INPUT_TOUCHSCREEN = lib.mkForce no;
        INPUT_JOYSTICK = lib.mkForce no;
        INPUT_TABLET = lib.mkForce no;

        # No framebuffer (no display)
        FB = lib.mkForce no;

        # No amateur radio
        HAMRADIO = lib.mkForce no;

        # No ATM networking
        ATM = lib.mkForce no;

        # No PCI sound cards (no PCI bus on Rock64)
        SND_PCI = lib.mkForce no;

        # No USB audio devices
        SND_USB = lib.mkForce no;

        # SND_HAD and SND_SOC_MEDIATEK are selected by other options, use unset
        SND_HAD = lib.mkForce unset;
        SND_SOC_MEDIATEK = lib.mkForce unset;
        SND_SOC_SAMSUNG = lib.mkForce no;
        SND_SOC_TEGRA = lib.mkForce no;

        # No USB gadget mode (we're host only)
        USB_EHCI_TEGRA = lib.mkForce no; # selects USB_GADGET, must disable first
        USB_GADGET = lib.mkForce no;

        # No Chrome/Surface platforms
        CHROME_PLATFORMS = lib.mkForce no;
        SURFACE_PLATFORMS = lib.mkForce no;

        # No accessibility
        ACCESSIBILITY = lib.mkForce no;

        # No PS/2 keyboard/mouse (no PS/2 port)
        KEYBOARD_ATKBD = lib.mkForce no;
        MOUSE_PS2 = lib.mkForce no;

        # No PATA/IDE (no IDE on Rock64)
        ATA_SFF = lib.mkForce no;
        PATA_PLATFORM = lib.mkForce unset;

        # ── Unneeded filesystems ─────────────────────────────────────────
        BTRFS_FS = lib.mkForce no;
        XFS_FS = lib.mkForce no;
        GFS2_FS = lib.mkForce no;
        OCFS2_FS = lib.mkForce no;
        JFS_FS = lib.mkForce no;
        CEPH_FS = lib.mkForce no;
        CIFS = lib.mkForce no;
        AFS_FS = lib.mkForce no;
        ORANGEFS_FS = lib.mkForce no;

        # ── Unset orphaned child options from disabled subsystems ─────────
        # nixpkgs common-config.nix sets these, but their parent toggles
        # are now disabled so the options don't exist in kconfig.
        # DRM children
        DRM_ACCEL = lib.mkForce unset;
        DRM_AMDGPU_CIK = lib.mkForce unset;
        DRM_AMDGPU_SI = lib.mkForce unset;
        DRM_AMDGPU_USERPTR = lib.mkForce unset;
        DRM_AMD_ACP = lib.mkForce unset;
        DRM_AMD_DC_FP = lib.mkForce unset;
        DRM_AMD_DC_SI = lib.mkForce unset;
        DRM_AMD_ISP = lib.mkForce unset;
        DRM_AMD_SECURE_DISPLAY = lib.mkForce unset;
        DRM_DISPLAY_DP_AUX_CEC = lib.mkForce unset;
        DRM_DISPLAY_DP_AUX_CHARDEV = lib.mkForce unset;
        DRM_FBDEV_EMULATION = lib.mkForce unset;
        DRM_HYPERV = lib.mkForce unset;
        DRM_LOAD_EDID_FIRMWARE = lib.mkForce unset;
        DRM_NOUVEAU_SVM = lib.mkForce unset;
        DRM_NOVA = lib.mkForce unset;
        DRM_PANIC = lib.mkForce unset;
        DRM_PANIC_SCREEN = lib.mkForce unset;
        DRM_PANIC_SCREEN_QR_CODE = lib.mkForce unset;
        DRM_SIMPLEDRM = lib.mkForce unset;
        DRM_VC4_HDMI_CEC = lib.mkForce unset;
        ROCKCHIP_DW_HDMI_QP = lib.mkForce unset;
        ROCKCHIP_DW_MIPI_DSI2 = lib.mkForce unset;
        HAS_AMD = lib.mkForce unset;
        HAS_AMD_P2P = lib.mkForce unset;
        HSA_AMD = lib.mkForce unset;
        HSA_AMD_P2P = lib.mkForce unset;
        # FB children
        FB_3DFX_ACCEL = lib.mkForce unset;
        FB_ATY_CT = lib.mkForce unset;
        FB_ATY_GX = lib.mkForce unset;
        FB_EFI = lib.mkForce unset;
        FB_HYPERV = lib.mkForce unset;
        FB_NVIDIA_I2C = lib.mkForce unset;
        FB_RIVA_I2C = lib.mkForce unset;
        FB_SAVAGE_ACCEL = lib.mkForce unset;
        FB_SAVAGE_I2C = lib.mkForce unset;
        FB_SIS_300 = lib.mkForce unset;
        FB_SIS_315 = lib.mkForce unset;
        FONTS = lib.mkForce unset;
        FONT_8x8 = lib.mkForce unset;
        FONT_TER16x32 = lib.mkForce unset;
        FRAMEBUFFER_CONSOLE = lib.mkForce unset;
        FRAMEBUFFER_CONSOLE_DEFERRED_TAKEOVER = lib.mkForce unset;
        FRAMEBUFFER_CONSOLE_DETECT_PRIMARY = lib.mkForce unset;
        FRAMEBUFFER_CONSOLE_ROTATION = lib.mkForce unset;
        LOGO = lib.mkForce unset;
        # BT children
        BT_HCIBTUSB_AUTOSUSPEND = lib.mkForce unset;
        BT_HCIBTUSB_MTK = lib.mkForce unset;
        BT_HCIUART = lib.mkForce unset;
        BT_HCIUART_QCA = lib.mkForce unset;
        BT_HCIUART_SERDEV = lib.mkForce unset;
        BT_QCA = lib.mkForce unset;
        # WLAN children
        AX25 = lib.mkForce unset;
        MT798X_WMAC = lib.mkForce unset;
        RT2800USB_RT53XX = lib.mkForce unset;
        RT2800USB_RT55XX = lib.mkForce unset;
        RTW88 = lib.mkForce unset;
        RTW88_8822BE = lib.mkForce unset;
        RTW88_8822CE = lib.mkForce unset;
        NVIDIA_SHIELD_FF = lib.mkForce unset;
        # MEDIA children
        MEDIA_ANALOG_TV_SUPPORT = lib.mkForce unset;
        MEDIA_ATTACH = lib.mkForce unset;
        MEDIA_CAMERA_SUPPORT = lib.mkForce unset;
        MEDIA_CONTROLLER = lib.mkForce unset;
        MEDIA_DIGITAL_TV_SUPPORT = lib.mkForce unset;
        MEDIA_PCI_SUPPORT = lib.mkForce unset;
        MEDIA_USB_SUPPORT = lib.mkForce unset;
        # INFINIBAND children
        INFINIBAND_IPOIB = lib.mkForce unset;
        INFINIBAND_IPOIB_CM = lib.mkForce unset;
        # Chrome OS children
        CHROMEOS_TBMC = lib.mkForce unset;
        CROS_EC = lib.mkForce unset;
        CROS_EC_I2C = lib.mkForce unset;
        CROS_EC_SPI = lib.mkForce unset;
        CROS_KBD_LED_BACKLIGHT = lib.mkForce unset;
        # FS children
        BTRFS_FS_POSIX_ACL = lib.mkForce unset;
        CEPH_FSCACHE = lib.mkForce unset;
        CEPH_FS_POSIX_ACL = lib.mkForce unset;
        CIFS_DFS_UPCALL = lib.mkForce unset;
        CIFS_FSCACHE = lib.mkForce unset;
        CIFS_UPCALL = lib.mkForce unset;
        CIFS_XATTR = lib.mkForce unset;
        # Sound children
        SND_USB_AUDIO_MIDI_V2 = lib.mkForce unset;
        SND_USB_CAIAQ_INPUT = lib.mkForce unset;
        # Input children
        MOUSE_PS2_ELANTECH = lib.mkForce unset;
        JOYSTICK_PSXPAD_SPI_FF = lib.mkForce unset;
        # SCSI children
        SCSI_LOWLEVEL_PCMCIA = lib.mkForce unset;
        # USB children
        USB_DWC2_DUAL_ROLE = lib.mkForce unset;
        USB_DWC3_DUAL_ROLE = lib.mkForce unset;
        U_SERIAL_CONSOLE = lib.mkForce unset;

        # ── Workarounds for removed options in kernel 6.19+ ──
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
  boot.initrd.availableKernelModules = lib.mkForce [
    "mmc_block"
    "dw_mmc_rockchip"
    "squashfs"
    "f2fs"
    "overlay"
    "dm_mod"
  ];

  # ── RAUC slot device paths (eMMC) ──────────────────────────────────────────
  # These map to the GPT partition layout created by the provisioning script:
  #   p1 = boot A (vfat), p2 = boot B (vfat), p3 = rootfs A, p4 = rootfs B
  atomixos.rauc.slots = {
    boot0 = "/dev/mmcblk1p1";
    boot1 = "/dev/mmcblk1p2";
    rootfs0 = "/dev/mmcblk1p3";
    rootfs1 = "/dev/mmcblk1p4";
  };

  # ── Serial console (UART2) ─────────────────────────────────────────────────
  # Enable login prompt on the debug serial console (ttyS2 @ 1.5Mbaud).
  # This is the 3-pin header on the Rock64 board.
  systemd.services."serial-getty@ttyS2" = {
    enable = true;
    wantedBy = [ "getty.target" ];
    serviceConfig.Restart = "always";
  };
}
