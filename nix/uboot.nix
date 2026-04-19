# Custom U-Boot for Rock64 with SPI flash environment and RAUC A/B boot.
#
# Key changes from stock nixpkgs ubootRock64:
#   - Environment stored on SPI flash (not eMMC) — avoids eMMC raw write bug
#     that bricks NCard and similar budget eMMC modules
#   - Redundant env for power-loss safety during saveenv
#   - RAUC A/B bootmeth for native slot selection and boot counters
#   - EFI boot disabled (not used on this board)
#   - SD card removed from boot targets (security: prevent boot hijack)
{
  pkgs,
  lib,
}:

(pkgs.ubootRock64.override {
  extraConfig = ''
    # ── Environment: SPI flash instead of eMMC ────────────────────────────
    # The eMMC raw write bug (confirmed on NCard and other budget modules)
    # causes saveenv from both U-Boot and Linux to corrupt the eMMC,
    # bricking the board. SPI flash (16MB, mtd0) is a separate device
    # that doesn't have this issue.
    CONFIG_ENV_IS_IN_MMC=n
    CONFIG_ENV_IS_IN_SPI_FLASH=y
    CONFIG_ENV_OFFSET=0x140000
    CONFIG_ENV_SIZE=0x2000
    CONFIG_ENV_SECT_SIZE=0x1000
    CONFIG_ENV_SECT_SIZE_AUTO=y
    # Offset 0x140000 = 1.25MB (Rockchip default for SPI, clear of SPL/U-Boot)
    # Size 0x2000 = 8KB using two 4KB erase sectors on this board's SPI NOR.
    # Redundant copy at 0x142000 for power-loss safety.
    CONFIG_ENV_REDUNDANT=y
    CONFIG_ENV_OFFSET_REDUND=0x142000

    # ── RAUC A/B boot method ──────────────────────────────────────────────
    # Native U-Boot support for A/B slot selection with boot counters.
    # Handles slot selection, try-count decrement, and rollback automatically.
    # Partition layout: boot=1,2 rootfs=3,4 (matches our GPT layout)
    CONFIG_BOOTMETH_RAUC=y
    # Partition mapping: "boot,root boot,root" — slot A = p1,p3  slot B = p2,p4
    CONFIG_BOOTMETH_RAUC_PARTITIONS="1,3 2,4"
    CONFIG_BOOTMETH_RAUC_BOOT_ORDER="A B"
    CONFIG_BOOTMETH_RAUC_DEFAULT_TRIES=3
    CONFIG_BOOTMETH_RAUC_RESET_ALL_ZERO_TRIES=y

    # ── Recovery mode over USB OTG ────────────────────────────────────────
    # If the reset button is held during boot, boot.cmd drops into `ums`
    # so the on-board eMMC can be reflashed directly over USB.
    CONFIG_USB_GADGET=y
    CONFIG_USB_GADGET_DOWNLOAD=y
    CONFIG_USB_GADGET_DWC2_OTG=y
    CONFIG_CMD_USB_MASS_STORAGE=y
    CONFIG_USB_FUNCTION_MASS_STORAGE=y
    CONFIG_CMD_UMS_ABORT_KEYED=n
    CONFIG_CMD_FASTBOOT=n
    CONFIG_USB_FUNCTION_FASTBOOT=n
    CONFIG_CMD_USB_SDP=n
    CONFIG_USB_FUNCTION_SDP=n
    CONFIG_CMD_THOR_DOWNLOAD=n
    CONFIG_USB_FUNCTION_THOR=n
    CONFIG_FASTBOOT_BUF_ADDR=0x0

    # ── Disable EFI boot (not used, wastes boot time) ─────────────────────
    CONFIG_EFI_LOADER=n

    # ── FAT write support (for slot_good flag file from Linux) ────────────
    CONFIG_FAT_WRITE=y
  '';
}).overrideAttrs
  (old: {
    postPatch = (old.postPatch or "") + ''
      perl -0pi -e 's/&usb20_otg \{\n\s*dr_mode = "host";/&usb20_otg {\n\tdr_mode = "peripheral";/g' \
        dts/upstream/src/arm64/rockchip/rk3328-rock64.dts
    '';
  })
