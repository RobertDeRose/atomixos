# U-Boot boot script for Rock64 and CM3 with RAUC A/B bootmeth.
#
# RAUC bootmeth (CONFIG_BOOTMETH_RAUC) handles slot selection, boot counter
# decrement, and saveenv BEFORE loading this script. By the time this runs:
#
#   devnum           - MMC device selected by the RAUC bootmeth
#   distro_bootpart  - Boot partition of selected slot (1=A, 3=B)
#   distro_rootpart  - Root partition of selected slot (2=A, 4=B)
#
# This script only needs to load kernel/DTB/initrd and set bootargs.
#
# Confirmation flow:
#   After successful boot, Linux calls `rauc status mark-good` which
#   internally uses fw_setenv to restore BOOT_x_LEFT=3.
#   Environment location depends on the board: SPI flash on Rock64,
#   redundant reserved eMMC sectors on CM3.
#   See modules/first-boot.nix and scripts/first-boot.sh.

echo "AtomixOS build: @buildId@"
echo ""

# Self-heal blank or stale boot environments in memory only. Persistent
# initialization is done from Linux with matching fw_setenv tooling.
if test -z "${BOOT_ORDER}"; then
  echo "Seeding BOOT_ORDER default (in-memory)"
  setenv BOOT_ORDER "A B"
fi

if test -z "${BOOT_A_LEFT}"; then
  echo "Seeding BOOT_A_LEFT default (in-memory)"
  setenv BOOT_A_LEFT 3
fi

if test -z "${BOOT_B_LEFT}"; then
  echo "Seeding BOOT_B_LEFT default (in-memory)"
  setenv BOOT_B_LEFT 3
fi

if test -z "${devnum}"; then
  setenv devnum 0
fi
if test -z "${distro_bootpart}"; then
  setenv distro_bootpart 1
fi

# GPIO recovery is supported on Rock64; the CM3 does not use that pin.
if test -z "${recovery_button_pin}"; then
  setenv recovery_button_pin "@recoveryButtonPin@"
fi
if test -z "${recovery_hold_secs}"; then
  setenv recovery_hold_secs 5
fi
if test -z "${recovery_usb_controller}"; then
  setenv recovery_usb_controller 0
fi
if test -z "${recovery_mmc_dev}"; then
  setenv recovery_mmc_dev ${devnum}
fi

# U-Boot's PREBOOT handles START_UMS before slot selection
# (nix/uboot-start-ums.nix), so it works even when this script is unreadable.
# RAUC bundles update this script but not U-Boot, so keep this fallback for
# boards whose U-Boot predates that PREBOOT.
if test "${START_UMS}" = "1"; then
  echo "START_UMS=1 requested, entering USB mass storage mode"
  setenv START_UMS
  saveenv
  echo "Write a new image over the OTG USB cable, then unplug to reboot"
  ums ${recovery_usb_controller} mmc ${recovery_mmc_dev}
  echo "USB mass storage exited, resetting..."
  reset
fi

if test -n "${recovery_button_pin}"; then
  if gpio input ${recovery_button_pin}; then
    echo "Recovery button detected on GPIO ${recovery_button_pin}"
    echo "Hold for ${recovery_hold_secs} seconds to enter USB mass storage mode"
    sleep ${recovery_hold_secs}
    if gpio input ${recovery_button_pin}; then
      echo "Entering USB mass storage mode for mmc ${recovery_mmc_dev}"
      echo "Write a new image over the OTG USB cable, then unplug to reboot"
      ums ${recovery_usb_controller} mmc ${recovery_mmc_dev}
      echo "USB mass storage exited, resetting..."
      reset
    fi
  fi
fi

# Derive the rootfs from the selected boot partition. RAUC bootmeth can leave
# a stale distro_rootpart in the environment, so never trust that value without
# checking it against distro_bootpart.
# Boot partition 1 → rootfs partition 2, boot partition 3 → rootfs partition 4.
if test "${distro_bootpart}" = "1"; then
  setenv distro_rootpart 2
  setenv atomixos_lowerdev "@rootfsPathA@"
elif test "${distro_bootpart}" = "3"; then
  setenv distro_rootpart 4
  setenv atomixos_lowerdev "@rootfsPathB@"
else
  setenv distro_rootpart 2
  setenv atomixos_lowerdev "@rootfsPathA@"
  echo "WARNING: unknown distro_bootpart, defaulted rootfs to ${distro_rootpart}"
fi

# RAUC's U-Boot backend needs the boot slot identity (boot.0 / boot.1), not the
# rootfs slot, so mark-good can target BOOT_A_LEFT / BOOT_B_LEFT correctly.
if test "${distro_bootpart}" = "1"; then
  setenv rauc_slot boot.0
elif test "${distro_bootpart}" = "3"; then
  setenv rauc_slot boot.1
else
  setenv rauc_slot boot.0
fi

echo "Recovery boot selection: dev=${devnum} boot=${distro_bootpart} root=${distro_rootpart}"

setenv bootargs_base "@bootargsBase@"

# Rock64: override ramdisk address to avoid overlap with relocated kernel.
# Default ramdisk_addr_r=0x06000000 but kernel relocates to end=0x06130000+.
# Place initrd at 128 MiB (0x08000000) — well clear of kernel.
# CM3 leaves this empty and keeps the RK3568 defaults.
if test -n "@ramdiskAddr@"; then
  setenv ramdisk_addr_r @ramdiskAddr@
fi

# Load kernel, DTB, and initrd from the selected boot partition. A failed load
# must not reach booti (a stale ${filesize} would give a wrong initrd size), so
# reset and let the decremented RAUC try counter fall back. Report the first
# file that failed.
setenv atomixos_load_failed
fatload mmc ${devnum}:${distro_bootpart} ${kernel_addr_r} Image || test -n "${atomixos_load_failed}" || setenv atomixos_load_failed Image
fatload mmc ${devnum}:${distro_bootpart} ${fdt_addr_r} dtbs/@dtbPath@ || test -n "${atomixos_load_failed}" || setenv atomixos_load_failed dtbs/@dtbPath@
fatload mmc ${devnum}:${distro_bootpart} ${ramdisk_addr_r} initrd || test -n "${atomixos_load_failed}" || setenv atomixos_load_failed initrd
if test -n "${atomixos_load_failed}"; then
  echo "ERROR: cannot load ${atomixos_load_failed} from mmc ${devnum}:${distro_bootpart}; resetting"
  reset
fi
setenv initrd_size ${filesize}

# NixOS boot.kernelParams first, so the board's console and loglevel win.
setenv bootargs "@kernelParams@ ${bootargs_base} root=fstab rw atomixos.lowerdev=${atomixos_lowerdev} atomixos.lowerfstype=squashfs init=@systemClosure@/init rauc.slot=${rauc_slot}"
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}

# Reset here too: U-Boot builds flashed before CONFIG_BOOTCOMMAND gained
# "; reset" would otherwise stop at the prompt.
echo "ERROR: booti failed; resetting so the RAUC try counter can fall back to the other slot"
reset
