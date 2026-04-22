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
  ubootEnvTools = self.packages.${pkgs.system}.uboot-env-tools;
  bootToUms = pkgs.writeShellScriptBin "boot_to_ums" ''
    set -euo pipefail

    echo "Setting START_UMS=1 in SPI U-Boot environment"
    ${ubootEnvTools}/bin/fw_setenv START_UMS 1

    echo "Rebooting so U-Boot enters USB mass storage mode"
    exec ${pkgs.systemd}/bin/systemctl reboot
  '';

  # Keep optional peripheral support isolated from the Rock64 board baseline.
  # This makes it cheap to add or remove a small set of USB adapters later
  # without reopening the built-in board hardware set.
  rock64OptionalKernelConfig = with lib.kernel; {
    # USB serial (for debug adapters)
    USB_SERIAL = lib.mkForce module;
    USB_SERIAL_FTDI_SIO = lib.mkForce module;
    USB_SERIAL_CP210X = lib.mkForce module;
    USB_SERIAL_GENERIC = lib.mkForce no;
    USB_SERIAL_SIMPLE = lib.mkForce no;
    USB_SERIAL_AIRCABLE = lib.mkForce no;
    USB_SERIAL_ARK3116 = lib.mkForce no;
    USB_SERIAL_BELKIN = lib.mkForce no;
    USB_SERIAL_CH341 = lib.mkForce no;
    USB_SERIAL_WHITEHEAT = lib.mkForce no;
    USB_SERIAL_DIGI_ACCELEPORT = lib.mkForce no;
    USB_SERIAL_CYPRESS_M8 = lib.mkForce no;
    USB_SERIAL_EMPEG = lib.mkForce no;
    USB_SERIAL_VISOR = lib.mkForce no;
    USB_SERIAL_IPAQ = lib.mkForce no;
    USB_SERIAL_IR = lib.mkForce no;
    USB_SERIAL_EDGEPORT = lib.mkForce no;
    USB_SERIAL_EDGEPORT_TI = lib.mkForce no;
    USB_SERIAL_F81232 = lib.mkForce no;
    USB_SERIAL_F8153X = lib.mkForce no;
    USB_SERIAL_GARMIN = lib.mkForce no;
    USB_SERIAL_IPW = lib.mkForce no;
    USB_SERIAL_IUU = lib.mkForce no;
    USB_SERIAL_KEYSPAN_PDA = lib.mkForce no;
    USB_SERIAL_KEYSPAN = lib.mkForce no;
    USB_SERIAL_KLSI = lib.mkForce no;
    USB_SERIAL_KOBIL_SCT = lib.mkForce no;
    USB_SERIAL_MCT_U232 = lib.mkForce no;
    USB_SERIAL_METRO = lib.mkForce no;
    USB_SERIAL_MOS7720 = lib.mkForce no;
    USB_SERIAL_MOS7840 = lib.mkForce no;
    USB_SERIAL_MXUPORT = lib.mkForce no;
    USB_SERIAL_NAVMAN = lib.mkForce no;
    USB_SERIAL_PL2303 = lib.mkForce no;
    USB_SERIAL_OTI6858 = lib.mkForce no;
    USB_SERIAL_QCAUX = lib.mkForce no;
    USB_SERIAL_QUALCOMM = lib.mkForce no;
    USB_SERIAL_SPCP8X5 = lib.mkForce no;
    USB_SERIAL_SAFE = lib.mkForce no;
    USB_SERIAL_SIERRAWIRELESS = lib.mkForce no;
    USB_SERIAL_SYMBOL = lib.mkForce no;
    USB_SERIAL_TI = lib.mkForce no;
    USB_SERIAL_CYBERJACK = lib.mkForce no;
    USB_SERIAL_OPTION = lib.mkForce no;
    USB_SERIAL_OMNINET = lib.mkForce no;
    USB_SERIAL_OPTICON = lib.mkForce no;
    USB_SERIAL_XSENS_MT = lib.mkForce no;
    USB_SERIAL_WISHBONE = lib.mkForce no;
    USB_SERIAL_SSU100 = lib.mkForce no;
    USB_SERIAL_QT2 = lib.mkForce no;
    USB_SERIAL_UPD78F0730 = lib.mkForce no;
    USB_SERIAL_XR = lib.mkForce no;
    USB_SERIAL_DEBUG = lib.mkForce no;
  };
in
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

  # Custom kernel configuration: strip to RK3328 essentials
  # Built-in (=y): eMMC, ethernet, USB host, watchdog, squashfs, f2fs
  # Modules (=m): WiFi, Bluetooth, USB serial (for optional USB peripherals)
  boot.kernelPatches = [
    {
      name = "rock64-stripped";
      patch = null;
      structuredExtraConfig =
        (with lib.kernel; {
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
          DWMAC_GENERIC = lib.mkForce no;

          # USB host
          USB_SUPPORT = lib.mkForce yes;
          USB = lib.mkForce yes;
          USB_PCI = lib.mkForce no;
          USB_DWC2 = lib.mkForce yes;
          USB_XHCI_HCD = lib.mkForce yes;
          USB_EHCI_HCD = lib.mkForce yes;
          USB_OHCI_HCD = lib.mkForce yes;
          USB_LED_TRIG = lib.mkForce no;
          USB_CONN_GPIO = lib.mkForce no;
          USB_ANNOUNCE_NEW_DEVICES = lib.mkForce no;
          USB_DEFAULT_PERSIST = lib.mkForce yes;
          USB_FEW_INIT_RETRIES = lib.mkForce no;
          USB_DYNAMIC_MINORS = lib.mkForce yes;
          USB_OTG = lib.mkForce no;
          USB_MON = lib.mkForce no;
          USB_C67X00_HCD = lib.mkForce no;
          USB_XHCI_DBGCAP = lib.mkForce no;
          USB_XHCI_PCI_RENESAS = lib.mkForce unset;
          USB_XHCI_SIDEBAND = lib.mkForce no;
          USB_EHCI_TT_NEWSCHED = lib.mkForce yes;
          USB_EHCI_FSL = lib.mkForce no;
          USB_EHCI_HCD_PLATFORM = lib.mkForce yes;
          USB_OHCI_HCD_PCI = lib.mkForce unset;
          USB_OHCI_HCD_PLATFORM = lib.mkForce yes;
          USB_OXU210HP_HCD = lib.mkForce no;
          USB_ISP116X_HCD = lib.mkForce no;
          USB_MAX3421_HCD = lib.mkForce no;
          USB_UHCI_HCD = lib.mkForce unset;
          USB_SL811_HCD = lib.mkForce no;
          USB_R8A66597_HCD = lib.mkForce no;
          USB_HCD_BCMA = lib.mkForce no;
          USB_HCD_SSB = lib.mkForce no;
          USB_HCD_TEST_MODE = lib.mkForce no;
          USB_XEN_HCD = lib.mkForce no;
          USB_ACM = lib.mkForce no;
          USB_VL600 = lib.mkForce no;
          USB_PULSE8_CEC = lib.mkForce no;
          USB_RAINSHADOW_CEC = lib.mkForce no;
          USB_NET_HUAWEI_CDC_NCM = lib.mkForce no;
          USB_NET_CDC_MBIM = lib.mkForce no;
          USB_NET_QMI_WWAN = lib.mkForce no;
          USB_PRINTER = lib.mkForce no;
          USB_WDM = lib.mkForce no;
          USB_TMC = lib.mkForce no;
          USB_DWC2_HOST = lib.mkForce yes;
          USB_DWC2_PERIPHERAL = lib.mkForce unset;
          USB_DWC2_DUAL_ROLE = lib.mkForce unset;
          USB_DWC2_DEBUG = lib.mkForce no;
          USB_DWC2_TRACK_MISSED_SOFS = lib.mkForce no;
          USB_GPIO_VBUS = lib.mkForce no;
          TAHVO_USB = lib.mkForce no;
          TAHVO_USB_HOST_BY_DEFAULT = lib.mkForce unset;
          USB_ISP1301 = lib.mkForce no;

          # SPI flash (for U-Boot env on mtd0)
          SPI = lib.mkForce yes;
          SPI_ROCKCHIP = lib.mkForce yes;
          MTD = lib.mkForce yes;
          MTD_SPI_NOR = lib.mkForce yes;

          # Board-local support required by the Rock64 DTS
          I2C = lib.mkForce yes;
          I2C_RK3X = lib.mkForce yes;
          SERIAL_8250 = lib.mkForce yes;
          SERIAL_8250_CONSOLE = lib.mkForce yes;
          SERIAL_8250_DW = lib.mkForce yes;
          SERIAL_OF_PLATFORM = lib.mkForce yes;
          EXTCON = lib.mkForce yes;
          PHYLIB = lib.mkForce yes;
          REALTEK_PHY = lib.mkForce yes;
          # USB net driver prompts are processed later than PHYLIB, so keep the
          # PHY symbols at =m here to avoid repeated-question loops before the
          # later USB_NET_DRIVERS/USB_USBNET disables collapse those selectors.
          AX88796B_PHY = lib.mkForce module;
          BROADCOM_PHY = lib.mkForce no;
          BCM54140_PHY = lib.mkForce no;
          BCM7XXX_PHY = lib.mkForce no;
          BCM_NET_PHYLIB = lib.mkForce no;
          MARVELL_PHY = lib.mkForce no;
          MICROCHIP_PHY = lib.mkForce module;
          SMSC_PHY = lib.mkForce module;
          DP83869_PHY = lib.mkForce no;
          REGULATOR = lib.mkForce yes;
          REGULATOR_FIXED_VOLTAGE = lib.mkForce yes;
          MFD_RK8XX_I2C = lib.mkForce yes;
          REGULATOR_RK808 = lib.mkForce yes;
          RTC_CLASS = lib.mkForce yes;
          RTC_DRV_RK808 = lib.mkForce yes;
          RTC_DRV_DS1307 = lib.mkForce no;
          RTC_DRV_HYM8563 = lib.mkForce no;
          RTC_DRV_ISL1208 = lib.mkForce no;
          RTC_DRV_PCF85363 = lib.mkForce no;
          RTC_DRV_PCF8563 = lib.mkForce no;
          RTC_DRV_M41T80 = lib.mkForce no;
          RTC_DRV_BQ32K = lib.mkForce no;
          RTC_DRV_TPS6594 = lib.mkForce no;
          RTC_DRV_RX8581 = lib.mkForce no;
          RTC_DRV_RV3028 = lib.mkForce no;
          RTC_DRV_RV8803 = lib.mkForce no;
          RTC_DRV_PCF2127 = lib.mkForce no;
          RTC_DRV_PCF85063 = lib.mkForce no;
          RTC_DRV_DA9063 = lib.mkForce no;
          RTC_DRV_MT6397 = lib.mkForce no;
          POWER_RESET = lib.mkForce yes;
          POWER_RESET_SYSCON = lib.mkForce yes;
          SYSCON_REBOOT_MODE = lib.mkForce yes;
          THERMAL = lib.mkForce yes;
          ROCKCHIP_THERMAL = lib.mkForce yes;
          ARM_CCI_PMU = lib.mkForce no;
          ARM_CSPMU = lib.mkForce no;
          ARM_CCN = lib.mkForce no;
          ARM_CMN = lib.mkForce no;
          ARM_DSU_PMU = lib.mkForce no;
          ARM_SPE_PMU = lib.mkForce no;
          ARM_SMMU_V3_PMU = lib.mkForce no;
          ARM_CORESIGHT_PMU_ARCH_SYSTEM_PMU = lib.mkForce no;
          NVIDIA_CORESIGHT_PMU_ARCH_SYSTEM_PMU = lib.mkForce no;
          ARM_DMC620_PMU = lib.mkForce no;
          PHY_ROCKCHIP_INNO_USB2 = lib.mkForce yes;
          PHY_ROCKCHIP_NANENG_COMBO_PHY = lib.mkForce yes;
          PHY_ROCKCHIP_INNO_HDMI = lib.mkForce no;
          PHY_ROCKCHIP_INNO_DSIDPHY = lib.mkForce no;
          PHY_ROCKCHIP_SAMSUNG_HDPTX = lib.mkForce no;

          # Keep arm64 platform support focused on Rock64/RK3328 so kernel config
          # generation does not drag in unrelated SoC menus and DT builds.
          COMPILE_TEST = lib.mkForce no;
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

          # Watchdog
          DW_WATCHDOG = lib.mkForce yes;

          # Filesystems
          SQUASHFS = lib.mkForce yes;
          SQUASHFS_XZ = lib.mkForce yes;
          SQUASHFS_ZSTD = lib.mkForce yes;
          F2FS_FS = lib.mkForce yes;
          OVERLAY_FS = lib.mkForce yes;

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

          # ── DISABLED SUBSYSTEMS ──────────────────────────────────────────
          # Each of these eliminates hundreds of config options downstream.

          # No display/GPU (~420 options)
          DRM = lib.mkForce no;

          # No cameras, TV tuners, DVB (~200+ options)
          MEDIA_SUPPORT = lib.mkForce no;
          RC_CORE = lib.mkForce no;
          CEC_CORE = lib.mkForce no;
          MEDIA_CEC_SUPPORT = lib.mkForce no;

          # No WiFi (re-enable when USB dongle hardware is selected)
          WLAN = lib.mkForce no;
          WLAN_VENDOR_ATH = lib.mkForce no;
          CFG80211 = lib.mkForce no;
          MAC80211 = lib.mkForce no;
          RFKILL = lib.mkForce no;
          ATH11K = lib.mkForce no;
          ATH11K_PCI = lib.mkForce no;
          ATH12K = lib.mkForce no;

          # No Bluetooth (re-enable when USB dongle hardware is selected)
          BT = lib.mkForce no;

          # Keep the container/VPN networking baseline that this image uses:
          # Podman needs bridge/veth/macvlan/tap-related plumbing, OpenVPN needs
          # tun, and WireGuard should stay available as an optional module.
          WIREGUARD = lib.mkForce module;
          TUN = lib.mkForce yes;
          TAP = lib.mkForce module;
          VETH = lib.mkForce module;
          BRIDGE = lib.mkForce module;
          BRIDGE_NETFILTER = lib.mkForce module;
          VLAN_8021Q = lib.mkForce module;
          MACVLAN = lib.mkForce module;
          MACVTAP = lib.mkForce module;
          IPV6 = lib.mkForce module;
          NETFILTER = lib.mkForce yes;
          NF_CONNTRACK = lib.mkForce module;

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

          # No mobile modem, IR/audio sideband buses, or related helper stacks
          MHI_BUS = lib.mkForce no;
          # QRTR is prompted under Networking before the later PCI/WLAN answers
          # can disable the ath11k/ath12k selector chain, so keep it at =m here
          # and let those later parent disables prune it back out of the final
          # Rock64 config.
          QRTR = lib.mkForce module;
          QRTR_SMD = lib.mkForce no;
          QRTR_TUN = lib.mkForce no;
          WWAN = lib.mkForce no;
          SOUNDWIRE = lib.mkForce no;
          SLIMBUS = lib.mkForce no;
          TYPEC = lib.mkForce no;
          IPMI_HANDLER = lib.mkForce no;
          TCG_TPM = lib.mkForce no;
          PHY_CADENCE_TORRENT = lib.mkForce no;
          PHY_CADENCE_DPHY = lib.mkForce no;
          PHY_CADENCE_DPHY_RX = lib.mkForce no;
          PHY_CADENCE_SIERRA = lib.mkForce no;
          PHY_CADENCE_SALVO = lib.mkForce no;
          PHY_CAN_TRANSCEIVER = lib.mkForce no;
          PHY_NXP_PTN3222 = lib.mkForce no;
          CORESIGHT = lib.mkForce no;
          CORESIGHT_STM = lib.mkForce no;
          POWER_SEQUENCING_QCOM_WCN = lib.mkForce no;
          MFD_QCOM_PM8008 = lib.mkForce no;
          REGULATOR_QCOM_USB_VBUS = lib.mkForce no;
          BACKLIGHT_QCOM_WLED = lib.mkForce no;
          LEDS_QCOM_LPG = lib.mkForce no;
          RPMSG_QCOM_GLINK = lib.mkForce no;
          RPMSG_QCOM_GLINK_RPM = lib.mkForce no;
          QCOM_PBS = lib.mkForce no;
          PHY_QCOM_USB_HS = lib.mkForce no;
          GREYBUS = lib.mkForce no;
          GREYBUS_BEAGLEPLAY = lib.mkForce no;
          GNSS = lib.mkForce no;
          GNSS_SERIAL = lib.mkForce no;
          GNSS_MTK = lib.mkForce no;
          # STM is prompted from drivers/hwtracing/Kconfig before the later
          # CoreSight menu collapses, so keep it at =m here to avoid the same
          # repeated-question trap we hit earlier with QRTR.
          STM = lib.mkForce module;
          STM_PROTO_BASIC = lib.mkForce no;
          STM_PROTO_SYS_T = lib.mkForce no;
          UACCE = lib.mkForce no;
          SND_ALOOP = lib.mkForce no;
          NBD = lib.mkForce no;

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
          HID_SUPPORT = lib.mkForce no;
          HID = lib.mkForce unset;

          # No framebuffer (no display)
          FB = lib.mkForce no;

          # No amateur radio
          HAMRADIO = lib.mkForce no;

          # No ATM networking
          ATM = lib.mkForce no;

          # Rock64 has no PCIe host, so drop PCI-only drivers and the wireless
          # selector chains that can still pull in QRTR via ath11k/ath12k.
          PCI = lib.mkForce no;

          # No software RAID, SCSI, or NVMe on Rock64.
          SCSI = lib.mkForce no;
          ATA = lib.mkForce no;
          NVME_CORE = lib.mkForce no;
          BLK_DEV_MD = lib.mkForce no;
          DM_MIRROR = lib.mkForce no;
          DM_ZERO = lib.mkForce no;
          MTD_NAND_BRCMNAND = lib.mkForce no;
          MTD_SPI_NAND = lib.mkForce no;
          MTD_UBI = lib.mkForce no;
          UBIFS_FS = lib.mkForce no;

          # No PCI sound cards (no PCI bus on Rock64)
          SND_PCI = lib.mkForce no;

          # No USB audio devices
          SND_USB = lib.mkForce no;

          # SND_HAD and some SoC-specific audio options are selected by other
          # platform menus, so they must be unset once those menus disappear.
          SND_HAD = lib.mkForce unset;
          SND_SOC_MEDIATEK = lib.mkForce unset;
          SND_SOC_SAMSUNG = lib.mkForce unset;
          SND_SOC_TEGRA = lib.mkForce unset;

          # No USB gadget mode (we're host only)
          USB_EHCI_TEGRA = lib.mkForce unset; # option disappears with Tegra off
          USB_GADGET = lib.mkForce no;
          USB_STORAGE = lib.mkForce no;
          USB_NET_DRIVERS = lib.mkForce no;
          USB_USBNET = lib.mkForce no;
          USB_NET_AX8817X = lib.mkForce no;
          USB_LAN78XX = lib.mkForce no;
          USB_NET_SMSC95XX = lib.mkForce no;
          USB_UAS = lib.mkForce unset;
          USB_MDC800 = lib.mkForce no;
          USB_MICROTEK = lib.mkForce no;
          USBIP_CORE = lib.mkForce no;
          USB_CDNS_SUPPORT = lib.mkForce no;
          USB_CDNSP_PCI = lib.mkForce unset;
          USB_MUSB_HDRC = lib.mkForce no;
          USB_DWC3 = lib.mkForce yes;
          USB_DWC3_HOST = lib.mkForce yes;
          USB_DWC3_GADGET = lib.mkForce unset;
          USB_DWC3_ULPI = lib.mkForce no;
          USB_CHIPIDEA = lib.mkForce no;
          USB_ISP1760 = lib.mkForce no;
          USB_EZUSB_FX2 = lib.mkForce no;
          USB_HSIC_USB3503 = lib.mkForce no;
          USB_HUB_USB251XB = lib.mkForce no;
          USB_HSIC_USB4604 = lib.mkForce no;
          USB_LINK_LAYER_TEST = lib.mkForce no;
          USB_CHAOSKEY = lib.mkForce no;
          BRCM_USB_PINMAP = lib.mkForce unset;
          USB_ONBOARD_DEV = lib.mkForce no;
          USB_ONBOARD_DEV_USB5744 = lib.mkForce unset;
          NOP_USB_XCEIV = lib.mkForce no;
          USB_MXS_PHY = lib.mkForce unset;

          # Match the currently selected preemption model so linux-config does not
          # report a stale mismatch against the defconfig baseline.
          PREEMPT_VOLUNTARY = lib.mkForce no;
          USB_EMI62 = lib.mkForce no;
          USB_EMI26 = lib.mkForce no;
          USB_ADUTUX = lib.mkForce no;
          USB_SEVSEG = lib.mkForce no;
          USB_LEGOTOWER = lib.mkForce no;
          USB_LCD = lib.mkForce no;
          USB_CYPRESS_CY7C63 = lib.mkForce no;
          USB_CYTHERM = lib.mkForce no;
          USB_IDMOUSE = lib.mkForce no;
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
        })
        // rock64OptionalKernelConfig;
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

  # Disable the storage debug capture by default on normal images.
  systemd.services.boot-storage-debug.wantedBy = lib.mkForce [ ];
}
