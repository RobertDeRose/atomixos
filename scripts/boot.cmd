# U-Boot boot script for Rock64 with RAUC A/B bootmeth.
#
# RAUC bootmeth (CONFIG_BOOTMETH_RAUC) handles slot selection, boot counter
# decrement, and saveenv BEFORE loading this script. By the time this runs:
#
#   devnum           - MMC device number (1 for eMMC)
#   distro_bootpart  - Boot partition of selected slot (1=A, 3=B)
#   distro_rootpart  - Root partition of selected slot (2=A, 4=B)
#
# This script only needs to load kernel/DTB/initrd and set bootargs.
#
# Confirmation flow:
#   After successful boot, Linux calls `rauc status mark-good` which
#   internally uses fw_setenv to restore BOOT_x_LEFT=3.
#   Environment is stored on SPI flash (not eMMC), so fw_setenv is safe.
#   See modules/first-boot.nix and scripts/first-boot.sh.

echo "AtomixOS build: @buildId@"
echo ""

# Self-heal blank or stale SPI environments in memory only. Persisting SPI from
# early boot is riskier than fixing it from Linux on first boot with matching
# fw_setenv tooling.
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

# Hold the reset button at power-on to expose eMMC over the Rock64 OTG port.
# Linux sees this as gpiochip3 line 4; in U-Boot that is global GPIO 100.
if test -z "${recovery_button_pin}"; then
  setenv recovery_button_pin 100
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

if test "${START_UMS}" = "1"; then
  echo "START_UMS=1 requested, entering USB mass storage mode"
  setenv START_UMS
  saveenv
  echo "Write a new image over the OTG USB cable, then unplug to reboot"
  ums ${recovery_usb_controller} mmc ${recovery_mmc_dev}
  echo "USB mass storage exited, resetting..."
  reset
fi

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

# Fallback: if RAUC bootmeth didn't set distro_rootpart (e.g. env_save failed
# on first boot with uninitialized SPI flash), derive it from distro_bootpart.
# Boot partition 1 → rootfs partition 2, boot partition 3 → rootfs partition 4.
if test -z "${distro_rootpart}"; then
  if test "${distro_bootpart}" = "1"; then
    setenv distro_rootpart 2
  elif test "${distro_bootpart}" = "3"; then
    setenv distro_rootpart 4
  else
    setenv distro_rootpart 2
  fi
  echo "WARNING: distro_rootpart was empty, defaulted to ${distro_rootpart}"
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

setenv bootargs_base "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xff130000 loglevel=7 rootwait"

# Override ramdisk address to avoid overlap with relocated kernel.
# Default ramdisk_addr_r=0x06000000 but kernel relocates to end=0x06130000+.
# Place initrd at 128 MiB (0x08000000) — well clear of kernel.
setenv ramdisk_addr_r 0x08000000

# Load kernel, DTB, and initrd from the selected boot partition
fatload mmc ${devnum}:${distro_bootpart} ${kernel_addr_r} Image
fatload mmc ${devnum}:${distro_bootpart} ${fdt_addr_r} dtbs/rockchip/rk3328-rock64.dtb
fatload mmc ${devnum}:${distro_bootpart} ${ramdisk_addr_r} initrd
setenv initrd_size ${filesize}

setenv bootargs "${bootargs_base} root=fstab rw atomixos.lowerdev=/dev/mmcblk1p${distro_rootpart} atomixos.lowerfstype=squashfs init=@systemClosure@/init rauc.slot=${rauc_slot}"
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}

echo "ERROR: booti failed!"
echo "Dropping to U-Boot shell for debugging..."
