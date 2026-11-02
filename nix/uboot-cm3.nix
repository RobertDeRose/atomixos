# Upstream Radxa CM3 (RK3566) U-Boot, with RAUC bootmeth and persistent eMMC
# environment. The SPI NOR component is optional on CM3, so do not assume it
# exists. The first 16 MiB of the eMMC user area is reserved by image layout.
{
  pkgs,
}:
(pkgs.ubootRock3C.override {
  defconfig = "radxa-cm3-io-rk3566_defconfig";
  filesToInstall = [
    "idbloader.img"
    "u-boot.itb"
  ];
  extraConfig = ''
    CONFIG_CMD_SAVEENV=y
    CONFIG_ENV_IS_NOWHERE=n
    CONFIG_ENV_IS_IN_SPI_FLASH=n
    CONFIG_ENV_IS_IN_MMC=y
    CONFIG_ENV_MMC_DEVICE_INDEX=0
    CONFIG_ENV_MMC_EMMC_HW_PARTITION=0
    CONFIG_ENV_OFFSET=0x3F8000
    CONFIG_ENV_OFFSET_REDUND=0x3F0000
    CONFIG_ENV_SIZE=0x8000
    # Current U-Boot names this ENV_REDUNDANT; unknown symbols are dropped
    # silently, so keep the name exact. It must match the two-copy layout in
    # hardware-cm3.nix's fw_env.config.
    CONFIG_ENV_REDUNDANT=y

    # Do not let the ordinary 'script' bootmeth run boot.scr before RAUC has
    # selected a slot and persisted the decrementing try counter. Scan only
    # mmc0 (eMMC): Rockchip's default boot_targets tries mmc1 (SD) first.
    # Restrict boot_targets rather than passing a label: a labelled or
    # per-device scan skips global bootmeths, which U-Boot refuses once
    # `bootmeth order` is set, so `bootflow scan -b mmc0` finds nothing.
    # Reset if the selected slot fails to boot, so the decremented try counter
    # falls back to the other slot instead of stopping at the prompt.
    CONFIG_BOOTSTD=y
    CONFIG_BOOTSTD_FULL=y
    CONFIG_BOOTSTD_DEFAULTS=y
    CONFIG_USE_BOOTCOMMAND=y
    CONFIG_CMD_BOOTMETH=y
    CONFIG_CMD_BOOTFLOW=y
    CONFIG_BOOTCOMMAND="setenv boot_targets mmc0; bootmeth order rauc; bootflow scan -b; reset"

    CONFIG_BOOTMETH_RAUC=y
    CONFIG_BOOTMETH_RAUC_PARTITIONS="1,2 3,4"
    CONFIG_BOOTMETH_RAUC_BOOT_ORDER="A B"
    CONFIG_BOOTMETH_RAUC_DEFAULT_TRIES=3
    CONFIG_BOOTMETH_RAUC_RESET_ALL_ZERO_TRIES=y

    # ── Recovery mode over USB OTG ────────────────────────────────────────
    # Same recovery contract as ROCK64: boot.cmd drops into `ums` so the eMMC
    # can be reflashed over the OTG port. RK3566 OTG is the DWC3 controller
    # (usb_host0_xhci, dr_mode "otg" upstream), not ROCK64's DWC2.
    CONFIG_USB_GADGET=y
    CONFIG_USB_GADGET_DOWNLOAD=y
    CONFIG_USB_DWC3_GADGET=y
    CONFIG_CMD_USB_MASS_STORAGE=y
    CONFIG_USB_FUNCTION_MASS_STORAGE=y
    CONFIG_CMD_UMS_ABORT_KEYED=n
    CONFIG_CMD_FASTBOOT=n
    CONFIG_USB_FUNCTION_FASTBOOT=n
    CONFIG_CMD_USB_SDP=n
    CONFIG_USB_FUNCTION_SDP=n
    CONFIG_CMD_THOR_DOWNLOAD=n
    CONFIG_USB_FUNCTION_THOR=n
    CONFIG_CMD_ROCKUSB=n
    CONFIG_USB_FUNCTION_ROCKUSB=n

    # ── Boot watchdog ─────────────────────────────────────────────────────
    # Start the RK3566 DesignWare watchdog (fe600000) in U-Boot proper and
    # leave it running into the kernel, so a kernel that stalls before
    # systemd still resets the board and spends a RAUC try. U-Boot feeds it
    # every second wherever it calls schedule(): the prompt, autoboot,
    # delays, storage I/O, and ums. Linux feeds it until systemd opens it or
    # watchdog.open_timeout passes (atomixos.watchdog.bootloaderStarted in
    # hardware-cm3.nix). The 24 MHz counter only takes 2^(16+n)-cycle
    # periods, so 44 s rounds up to 2^30 cycles, 44.7 s: the same period
    # systemd's 30 s runtime timeout selects. SPL and the BootROM (Maskrom)
    # never start it.
    CONFIG_WDT=y
    CONFIG_DESIGNWARE_WATCHDOG=y
    CONFIG_WATCHDOG=y
    CONFIG_WATCHDOG_AUTOSTART=y
    CONFIG_WATCHDOG_TIMEOUT_MSECS=44000
    CONFIG_SPL_WATCHDOG=n
    CONFIG_SPL_WDT=n

    CONFIG_EFI_LOADER=n
    CONFIG_FAT_WRITE=y
  ''
  + import ./uboot-start-ums.nix;
}).overrideAttrs
  (old: {
    # Ship the resolved Kconfig: U-Boot silently drops unknown or renamed
    # symbols, and the cm3-board check compares this against extraConfig.
    postInstall = (old.postInstall or "") + ''
      install -m0444 .config "$out/u-boot.config"
    '';
  })
