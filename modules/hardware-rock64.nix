# Rock64 (RK3328) hardware-specific configuration.
# Kernel, device tree, U-Boot, and eMMC-specific settings.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

let
  kernelConfig = import ./kernel-config.nix { inherit lib; };
  ubootEnvTools = self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools;
  bootToUms = pkgs.writeShellScriptBin "boot_to_ums" ''
    set -euo pipefail

    echo "Setting START_UMS=1 in SPI U-Boot environment"
    ${ubootEnvTools}/bin/fw_setenv START_UMS 1

    echo "Rebooting so U-Boot enters USB mass storage mode"
    exec ${pkgs.systemd}/bin/systemctl reboot
  '';

  rock64KernelConfig = with lib.kernel; {
    # Keep arm64 platform support focused on Rock64/RK3328 so kernel config
    # generation does not drag in unrelated SoC menus and DT builds.
    ARCH_ROCKCHIP = lib.mkForce yes;
    ARCH_ACTIONS = lib.mkForce no;
    ARCH_AIROHA = lib.mkForce no;
    ARCH_SUNXI = lib.mkForce no;
    ARCH_ALPINE = lib.mkForce no;
    ARCH_APPLE = lib.mkForce no;
    ARCH_ARTPEC = lib.mkForce unset;
    ARCH_AXIADO = lib.mkForce no;
    ARCH_BCM = lib.mkForce no;
    ARCH_BERLIN = lib.mkForce no;
    ARCH_BITMAIN = lib.mkForce no;
    ARCH_BLAIZE = lib.mkForce no;
    ARCH_BST = lib.mkForce no;
    ARCH_CIX = lib.mkForce no;
    ARCH_EXYNOS = lib.mkForce no;
    ARCH_K3 = lib.mkForce no;
    ARCH_LG1K = lib.mkForce no;
    ARCH_HISI = lib.mkForce no;
    ARCH_KEEMBAY = lib.mkForce no;
    ARCH_MEDIATEK = lib.mkForce no;
    ARCH_MESON = lib.mkForce no;
    ARCH_LAN969X = lib.mkForce no;
    ARCH_SPARX5 = lib.mkForce no;
    ARCH_MMP = lib.mkForce no;
    ARCH_MVEBU = lib.mkForce no;
    ARCH_NXP = lib.mkForce no;
    ARCH_MA35 = lib.mkForce no;
    ARCH_NPCM = lib.mkForce no;
    ARCH_PENSANDO = lib.mkForce no;
    ARCH_QCOM = lib.mkForce no;
    ARCH_REALTEK = lib.mkForce no;
    ARCH_RENESAS = lib.mkForce no;
    ARCH_SEATTLE = lib.mkForce no;
    ARCH_INTEL_SOCFPGA = lib.mkForce no;
    ARCH_SOPHGO = lib.mkForce no;
    ARCH_STM32 = lib.mkForce no;
    ARCH_SYNQUACER = lib.mkForce no;
    ARCH_TEGRA = lib.mkForce no;
    ARCH_TESLA_FSD = lib.mkForce unset;
    ARCH_SPRD = lib.mkForce no;
    ARCH_THUNDER = lib.mkForce no;
    ARCH_THUNDER2 = lib.mkForce no;
    ARCH_UNIPHIER = lib.mkForce no;
    ARCH_VEXPRESS = lib.mkForce no;
    ARCH_VISCONTI = lib.mkForce no;
    ARCH_XGENE = lib.mkForce no;
    ARCH_ZYNQMP = lib.mkForce no;

    # ── Audio (Rock64 built-in I2S) ──
    # This is on-board hardware, so keep the Rock64 audio path built in
    # and disable the rest of the Rockchip audio family.
    SOUND = lib.mkForce yes;
    SND = lib.mkForce yes;
    SND_SOC = lib.mkForce yes;
    SND_SOC_ALL_CODECS = lib.mkForce unset;
    SND_SIMPLE_CARD = lib.mkForce yes;
    SND_AUDIO_GRAPH_CARD = lib.mkForce no;
    SND_AUDIO_GRAPH_CARD2 = lib.mkForce no;
    SND_TEST_COMPONENT = lib.mkForce no;
    SND_XEN_FRONTEND = lib.mkForce no;
    SND_VIRTIO = lib.mkForce no;
    SND_SOC_RK3328 = lib.mkForce yes;
    SND_SOC_ROCKCHIP_I2S = lib.mkForce yes;
    SND_SOC_ROCKCHIP_I2S_TDM = lib.mkForce no;
    SND_SOC_ROCKCHIP_SPDIF = lib.mkForce yes;
    SND_SOC_GENERIC_DMAENGINE_PCM = lib.mkForce yes;
    SND_SOC_SDCA_OPTIONAL = lib.mkForce no;
    SND_SOC_SOF_TOPLEVEL = lib.mkForce no;
    SND_SOC_SOF_OF = lib.mkForce no;
    SND_SOC_SOF_MTK_TOPLEVEL = lib.mkForce no;
    SND_SOC_FSL_ASRC = lib.mkForce no;
    SND_SOC_FSL_SAI = lib.mkForce no;
    SND_SOC_FSL_AUDMIX = lib.mkForce no;
    SND_SOC_FSL_SSI = lib.mkForce no;
    SND_SOC_FSL_SPDIF = lib.mkForce no;
    SND_SOC_FSL_ESAI = lib.mkForce no;
    SND_SOC_FSL_MICFIL = lib.mkForce no;
    SND_SOC_FSL_EASRC = lib.mkForce no;
    SND_SOC_FSL_UTILS = lib.mkForce no;
    SND_SOC_IMX_AUDMUX = lib.mkForce no;
    SND_SOC_ADAU7002 = lib.mkForce no;
    SND_SOC_AK4613 = lib.mkForce no;
    SND_SOC_AK4619 = lib.mkForce no;
    SND_SOC_BT_SCO = lib.mkForce no;
    SND_SOC_DA7213 = lib.mkForce no;
    SND_SOC_DMIC = lib.mkForce no;
    SND_SOC_ES7134 = lib.mkForce no;
    SND_SOC_ES7241 = lib.mkForce no;
    SND_SOC_ES8316 = lib.mkForce no;
    SND_SOC_ES8326 = lib.mkForce no;
    SND_SOC_ES8328 = lib.mkForce no;
    SND_SOC_ES8328_I2C = lib.mkForce no;
    SND_SOC_GTM601 = lib.mkForce no;
    SND_SOC_MAX98357A = lib.mkForce no;
    SND_SOC_MAX98927 = lib.mkForce no;
    SND_SOC_MAX98390 = lib.mkForce no;
    SND_SOC_MSM8916_WCD_ANALOG = lib.mkForce no;
    SND_SOC_MSM8916_WCD_DIGITAL = lib.mkForce no;
    SND_SOC_PCM3168A = lib.mkForce no;
    SND_SOC_PCM3168A_I2C = lib.mkForce no;
    SND_SOC_RK817 = lib.mkForce no;
    SND_SOC_RL6231 = lib.mkForce no;
    SND_SOC_RT5640 = lib.mkForce no;
    SND_SOC_RT5659 = lib.mkForce no;
    SND_SOC_SGTL5000 = lib.mkForce no;
    SND_SOC_SIMPLE_AMPLIFIER = lib.mkForce no;
    SND_SOC_SIMPLE_MUX = lib.mkForce no;
    SND_SOC_SPDIF = lib.mkForce no;
    SND_SOC_TAS2552 = lib.mkForce no;
    SND_SOC_TAS571X = lib.mkForce no;
    SND_SOC_TLV320AIC31XX = lib.mkForce no;
    SND_SOC_TLV320AIC32X4 = lib.mkForce no;
    SND_SOC_TLV320AIC32X4_I2C = lib.mkForce no;
    SND_SOC_TLV320AIC3X = lib.mkForce no;
    SND_SOC_TLV320AIC3X_I2C = lib.mkForce no;
    SND_SOC_TS3A227E = lib.mkForce no;
    SND_SOC_WCD_CLASSH = lib.mkForce no;
    SND_SOC_WCD_COMMON = lib.mkForce no;
    SND_SOC_WCD9335 = lib.mkForce no;
    SND_SOC_WCD_MBHC = lib.mkForce no;
    SND_SOC_WCD934X = lib.mkForce no;
    SND_SOC_WCD938X = lib.mkForce no;
    SND_SOC_WCD938X_SDW = lib.mkForce no;
    SND_SOC_WCD939X = lib.mkForce no;
    SND_SOC_WCD939X_SDW = lib.mkForce no;
    SND_SOC_WM8524 = lib.mkForce no;
    SND_SOC_WM8904 = lib.mkForce no;
    SND_SOC_WM8960 = lib.mkForce no;
    SND_SOC_WM8962 = lib.mkForce no;
    SND_SOC_WM8978 = lib.mkForce no;
    SND_SOC_WSA881X = lib.mkForce no;
    SND_SOC_WSA883X = lib.mkForce no;
    SND_SOC_WSA884X = lib.mkForce no;
    SND_SOC_MT6357 = lib.mkForce no;
    SND_SOC_MT6358 = lib.mkForce no;
    SND_SOC_NAU8315 = lib.mkForce no;
    SND_SOC_NAU8822 = lib.mkForce no;
    SND_SOC_LPASS_MACRO_COMMON = lib.mkForce no;
    SND_SOC_LPASS_WSA_MACRO = lib.mkForce no;
    SND_SOC_LPASS_VA_MACRO = lib.mkForce no;
    SND_SOC_LPASS_RX_MACRO = lib.mkForce no;
    SND_SOC_LPASS_TX_MACRO = lib.mkForce no;
    SND_SOC_RK3308 = lib.mkForce no;
    SND_SOC_ROCKCHIP_SAI = lib.mkForce no;
    SND_SOC_ROCKCHIP_MAX98090 = lib.mkForce no;
    SND_SOC_ROCKCHIP_RT5645 = lib.mkForce no;
    SND_SOC_RK3288_HDMI_ANALOG = lib.mkForce no;
    SND_SOC_RK3399_GRU_SOUND = lib.mkForce no;

    # Rock64 has no PCIe host, so drop PCI-only drivers and the wireless
    # selector chains that can still pull in QRTR via ath11k/ath12k.
    PCI = lib.mkForce no;

    # USB Ethernet adapters for the LAN-side dongle. Keep only the small
    # set of chipsets our networking config names explicitly.
    USB_NET_DRIVERS = lib.mkForce yes;
    USB_USBNET = lib.mkForce module;
    USB_NET_AX88179_178A = lib.mkForce module;
    USB_NET_CDCETHER = lib.mkForce module;
    USB_RTL8152 = lib.mkForce module;

    USB_APPLEDISPLAY = lib.mkForce no;
    APPLE_MFI_FASTCHARGE = lib.mkForce no;
    USB_LJCA = lib.mkForce no;
    USB_SISUSBVGA = lib.mkForce no;
    USB_LD = lib.mkForce no;
    USB_TRANCEVIBRATOR = lib.mkForce no;
    USB_IOWARRIOR = lib.mkForce no;
    USB_TEST = lib.mkForce no;
    USB_EHSET_TEST_FIXTURE = lib.mkForce no;
    USB_ISIGHTFW = lib.mkForce no;
    USB_YUREX = lib.mkForce no;
    PHY_ROCKCHIP_PCIE = lib.mkForce no;

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

    # platform children / vendor glue that disappear when those platform
    # menus are disabled
    ARCH_LAYERSCAPE = lib.mkForce unset;
    ARCH_MXC = lib.mkForce unset;
    ARCH_S32 = lib.mkForce unset;
    B53 = lib.mkForce no;
    FSL_MC_UAPI_SUPPORT = lib.mkForce unset;
    NET_DSA = lib.mkForce no;
    NET_DSA_BCM_SF2 = lib.mkForce no;
    NET_VENDOR_AMAZON = lib.mkForce no;
    NET_VENDOR_ATHEROS = lib.mkForce no;
    NET_VENDOR_BROADCOM = lib.mkForce no;
    NET_VENDOR_MELLANOX = lib.mkForce no;
    NET_VENDOR_MEDIATEK = lib.mkForce unset;
    NET_VENDOR_QUALCOMM = lib.mkForce no;
    NET_VENDOR_REALTEK = lib.mkForce no;
    SUN8I_DE2_CCU = lib.mkForce unset;
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
    DRAGONRISE_FF = lib.mkForce unset;
    GREENASIA_FF = lib.mkForce unset;
    HIDRAW = lib.mkForce unset;
    HID_ACRUX_FF = lib.mkForce unset;
    HID_BATTERY_STRENGTH = lib.mkForce unset;
    HID_BPF = lib.mkForce unset;
    HID_HAPTIC = lib.mkForce unset;
    HOLTEK_FF = lib.mkForce unset;
    LOGIG940_FF = lib.mkForce unset;
    LOGIRUMBLEPAD2_FF = lib.mkForce unset;
    LOGITECH_FF = lib.mkForce unset;
    LOGIWHEELS_FF = lib.mkForce unset;
    MOUSE_PS2_ELANTECH = lib.mkForce unset;
    JOYSTICK_PSXPAD_SPI_FF = lib.mkForce unset;
    NINTENDO_FF = lib.mkForce unset;
    PLAYSTATION_FF = lib.mkForce unset;
    SMARTJOYPLUS_FF = lib.mkForce unset;
    SONY_FF = lib.mkForce unset;
    THRUSTMASTER_FF = lib.mkForce unset;
    USB_HIDDEV = lib.mkForce unset;
    ZEROPLUS_FF = lib.mkForce unset;

    # SCSI children
    SCSI_LOWLEVEL_PCMCIA = lib.mkForce unset;

    # USB children
    USB_DWC3_DUAL_ROLE = lib.mkForce unset;
    USB_PCI_AMD = lib.mkForce unset;
    USB_OTG_PRODUCTLIST = lib.mkForce unset;
    USB_OTG_DISABLE_EXTERNAL_HUB = lib.mkForce unset;
    USB_OTG_FSM = lib.mkForce unset;
    USB_LEDS_TRIGGER_USBPORT = lib.mkForce unset;
    U_SERIAL_CONSOLE = lib.mkForce unset;

    # ── Workarounds for removed options in kernel 6.19+ ──
    USB_SERIAL_CONSOLE = lib.mkForce unset;
  };

  serialRootDebugScript = pkgs.writeShellScript "rock64-serial-root-debug" ''
    set -euo pipefail

    env_value="$(${ubootEnvTools}/bin/fw_printenv -n _RUT_OH_ 2>/dev/null || true)"
    if [ "$env_value" != "1" ]; then
      exit 0
    fi

    ${pkgs.systemd}/bin/systemctl stop serial-getty@ttyS2.service
    ${pkgs.systemd}/bin/systemctl start serial-root-debug@ttyS2.service
    ${ubootEnvTools}/bin/fw_setenv _RUT_OH_
  '';
in
{
  atomixos.serialRootDebug.enable = true;

  # ── Boot partition ────────────────────────────────────────────────────────────
  # Mount the active boot slot's FAT partition at /boot (slot A).
  fileSystems."/boot" = {
    device = "/dev/mmcblk1p1";
    fsType = "vfat";
  };

  # Initrd repart cannot infer the backing disk from our overlay root, so point
  # it at the Rock64 eMMC device explicitly when creating the data partition.
  boot.initrd.systemd.repart.device = "/dev/mmcblk1";
  # The Rock64 stores U-Boot in the raw gap before the first GPT partition.
  # systemd-repart's default discard pass trims that gap, which destroys the
  # bootloader payload and breaks subsequent soft reboots.
  boot.initrd.systemd.repart.discard = false;

  # ── U-Boot environment tools (fw_setenv / fw_printenv) ─────────────────────
  # Environment is stored on SPI flash (not eMMC) to avoid the eMMC raw write
  # bug. first-boot.service uses fw_setenv to confirm the boot slot.
  environment.systemPackages = [
    ubootEnvTools
    bootToUms
  ];
  environment.etc."fw_env.config".text = ''
    # MTD device for SPI flash env (matches U-Boot CONFIG_ENV_OFFSET/SIZE)
    # Device         Offset    Size      Erase-size
    /dev/mtd0        0x140000  0x2000    0x1000
  '';

  # ── Boot configuration ───────────────────────────────────────────────────────

  # U-Boot handles booting — no bootloader managed by NixOS
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = false;

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
        kernelConfig.baseKernelConfig // kernelConfig.optionalKernelConfig // rock64KernelConfig;
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
  # Enable login prompt on the debug serial console (ttyS2 @ 1.5Mbaud).
  # This is the 3-pin header on the Rock64 board.
  systemd.services."serial-getty@ttyS2" = {
    enable = true;
    wantedBy = [ "getty.target" ];
    serviceConfig.Restart = "always";
  };

  systemd.services."serial-root-debug@" = lib.mkIf config.atomixos.serialRootDebug.enable {
    description = "Serial root debug autologin on %I";
    after = [ "systemd-user-sessions.service" ];
    serviceConfig = {
      Type = "idle";
      ExecStart = "${pkgs.util-linux}/sbin/agetty --autologin root --keep-baud 1500000,115200,57600,38400 -8 -L %I vt220";
      Restart = "always";
      RestartSec = "0";
      TTYPath = "/dev/%I";
      TTYReset = true;
      TTYVHangup = true;
      IgnoreSIGPIPE = false;
      SendSIGHUP = true;
    };
  };

  systemd.services.serial-root-debug-gate = lib.mkIf config.atomixos.serialRootDebug.enable {
    description = "Enable serial root debug when _RUT_OH_=1";
    after = [
      "data.mount"
      "serial-getty@ttyS2.service"
    ];
    wants = [ "data.mount" ];
    wantedBy = [ "multi-user.target" ];
    unitConfig.RequiresMountsFor = [ "/data" ];
    path = [
      pkgs.coreutils
      pkgs.systemd
      ubootEnvTools
    ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = serialRootDebugScript;
    };
  };

  # Disable the storage debug capture by default on normal images.
  systemd.services.boot-storage-debug.wantedBy = lib.mkForce [ ];
}
