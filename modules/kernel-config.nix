# Defines shared AtomixOS ARM64 kernel config fragments, including the stripped base config and optional USB-serial support.
{
  lib,
}:

let
  optionalKernelConfig = with lib.kernel; {
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

  baseKernelConfig = with lib.kernel; {
    # ══════════════════════════════════════════════════════════════════
    # STRIPPED KERNEL CONFIG FOR ATOMIXOS ARM64 GATEWAY
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

    # Board-local support required by the Rock64 DTS or shared boot plumbing.
    I2C = lib.mkForce yes;
    I2C_RK3X = lib.mkForce yes;
    SERIAL_8250 = lib.mkForce yes;
    SERIAL_8250_CONSOLE = lib.mkForce yes;
    SERIAL_8250_DW = lib.mkForce yes;
    SERIAL_OF_PLATFORM = lib.mkForce yes;
    EXTCON = lib.mkForce yes;
    PHYLIB = lib.mkForce yes;
    REALTEK_PHY = lib.mkForce yes;
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

    COMPILE_TEST = lib.mkForce no;

    # Watchdog
    DW_WATCHDOG = lib.mkForce yes;

    # Filesystems
    SQUASHFS = lib.mkForce yes;
    SQUASHFS_XZ = lib.mkForce yes;
    SQUASHFS_ZSTD = lib.mkForce yes;
    F2FS_FS = lib.mkForce yes;
    OVERLAY_FS = lib.mkForce yes;

    # Networking baseline used by the gateway image.
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
    NFNETLINK = lib.mkForce yes;
    NF_CONNTRACK = lib.mkForce module;
    NF_NAT = lib.mkForce module;
    NF_TABLES = lib.mkForce yes;
    NF_TABLES_INET = lib.mkForce yes;
    NF_TABLES_IPV4 = lib.mkForce yes;
    NF_TABLES_IPV6 = lib.mkForce yes;
    NFT_CT = lib.mkForce module;
    NFT_COUNTER = lib.mkForce yes;
    NFT_LIMIT = lib.mkForce module;
    NFT_LOG = lib.mkForce module;
    NFT_MASQ = lib.mkForce module;
    NFT_NAT = lib.mkForce module;
    NFT_REJECT = lib.mkForce module;

    # Large disabled subsystems.
    DRM = lib.mkForce no;
    MEDIA_SUPPORT = lib.mkForce no;
    RC_CORE = lib.mkForce no;
    CEC_CORE = lib.mkForce no;
    MEDIA_CEC_SUPPORT = lib.mkForce no;
    WLAN = lib.mkForce no;
    WLAN_VENDOR_ATH = lib.mkForce no;
    CFG80211 = lib.mkForce no;
    MAC80211 = lib.mkForce no;
    RFKILL = lib.mkForce no;
    ATH11K = lib.mkForce no;
    ATH11K_PCI = lib.mkForce no;
    ATH12K = lib.mkForce no;
    BT = lib.mkForce no;
    CAN = lib.mkForce no;
    INFINIBAND = lib.mkForce no;
    NFC = lib.mkForce no;
    COMEDI = lib.mkForce no;
    FIREWIRE = lib.mkForce no;
    PCCARD = lib.mkForce no;
    MHI_BUS = lib.mkForce no;
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
    STM = lib.mkForce module;
    STM_PROTO_BASIC = lib.mkForce no;
    STM_PROTO_SYS_T = lib.mkForce no;
    UACCE = lib.mkForce no;
    SND_ALOOP = lib.mkForce no;
    NBD = lib.mkForce no;
    PARPORT = lib.mkForce no;
    GAMEPORT = lib.mkForce no;
    FPGA = lib.mkForce no;
    IIO = lib.mkForce no;
    INPUT_TOUCHSCREEN = lib.mkForce no;
    INPUT_JOYSTICK = lib.mkForce no;
    INPUT_TABLET = lib.mkForce no;
    HID_SUPPORT = lib.mkForce no;
    HID = lib.mkForce unset;
    FB = lib.mkForce no;
    HAMRADIO = lib.mkForce no;
    ATM = lib.mkForce no;
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
    SND_PCI = lib.mkForce no;
    SND_USB = lib.mkForce no;
    SND_HAD = lib.mkForce unset;
    SND_SOC_MEDIATEK = lib.mkForce unset;
    SND_SOC_SAMSUNG = lib.mkForce unset;
    SND_SOC_TEGRA = lib.mkForce unset;
    USB_EHCI_TEGRA = lib.mkForce unset;
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
    SCSI_LOWLEVEL_PCMCIA = lib.mkForce unset;
    USB_DWC3_DUAL_ROLE = lib.mkForce unset;
    USB_PCI_AMD = lib.mkForce unset;
    USB_OTG_PRODUCTLIST = lib.mkForce unset;
    USB_OTG_DISABLE_EXTERNAL_HUB = lib.mkForce unset;
    USB_OTG_FSM = lib.mkForce unset;
    USB_LEDS_TRIGGER_USBPORT = lib.mkForce unset;
    U_SERIAL_CONSOLE = lib.mkForce unset;
    USB_SERIAL_CONSOLE = lib.mkForce unset;
  };
in
{
  inherit optionalKernelConfig baseKernelConfig;
}
