# U-Boot boot script for Rock64 with RAUC A/B bootmeth.
#
# RAUC bootmeth (CONFIG_BOOTMETH_RAUC) handles slot selection, boot counter
# decrement, and saveenv BEFORE loading this script. By the time this runs:
#
#   devnum           - MMC device number (1 for eMMC)
#   distro_bootpart  - Boot partition of selected slot (1=A, 2=B)
#   distro_rootpart  - Root partition of selected slot (3=A, 4=B)
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
echo "RAUC bootmeth selected: dev=${devnum} boot=${distro_bootpart} root=${distro_rootpart}"

# Hold the reset button at power-on to expose eMMC over the Rock64 OTG port.
# Linux sees this as gpiochip3 line 4; in U-Boot that is global GPIO 100.
if test -z "${recovery_button_pin}"; then
  setenv recovery_button_pin 100
fi
if test -z "${recovery_hold_secs}"; then
  setenv recovery_hold_secs 10
fi
if test -z "${recovery_usb_controller}"; then
  setenv recovery_usb_controller 0
fi
if test -z "${recovery_mmc_dev}"; then
  setenv recovery_mmc_dev ${devnum}
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
# Boot partition 1 → rootfs partition 3, boot partition 2 → rootfs partition 4.
if test -z "${distro_rootpart}"; then
  if test "${distro_bootpart}" = "1"; then
    setenv distro_rootpart 3
  elif test "${distro_bootpart}" = "2"; then
    setenv distro_rootpart 4
  else
    setenv distro_rootpart 3
  fi
  echo "WARNING: distro_rootpart was empty, defaulted to ${distro_rootpart}"
fi

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

setenv bootargs "${bootargs_base} ${raucargs} root=/dev/mmcblk1p${distro_rootpart} rootfstype=squashfs ro"
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}

echo "ERROR: booti failed!"
echo "Dropping to U-Boot shell for debugging..."
