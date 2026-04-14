# U-Boot boot script for Rock64 A/B slot selection with boot-count logic.
#
# This script is compiled with mkimage and stored in U-Boot's environment
# or as a boot.scr file. It implements RAUC-compatible A/B boot selection
# with automatic rollback.
#
# Environment variables used:
#   BOOT_ORDER   - Space-separated slot priority, e.g., "A B"
#   BOOT_A_LEFT  - Remaining boot attempts for slot A (0-3)
#   BOOT_B_LEFT  - Remaining boot attempts for slot B (0-3)
#
# Device detection:
#   The script auto-detects the boot MMC device via U-Boot's devnum variable
#   (set by bootflow scan). Falls back to 0 if unset.
#
# Root filesystem identification:
#   Uses GPT partition labels (PARTLABEL=rootfs-a / rootfs-b) instead of
#   device numbers, since U-Boot and Linux may assign different mmcblk numbers
#   to the same physical device.

# Default values if not set
test -n "${BOOT_ORDER}" || setenv BOOT_ORDER "A B"
test -n "${BOOT_A_LEFT}" || setenv BOOT_A_LEFT 3
test -n "${BOOT_B_LEFT}" || setenv BOOT_B_LEFT 3

# Auto-detect boot device number (set by bootflow scan)
test -n "${devnum}" || setenv devnum 0

setenv bootargs_base "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xff130000 loglevel=7 rootwait"

# Override ramdisk address to avoid overlap with relocated kernel.
# Default ramdisk_addr_r=0x06000000 but kernel relocates to end=0x06130000+.
# Place initrd at 128 MiB (0x08000000) — well clear of kernel.
setenv ramdisk_addr_r 0x08000000

# Try each slot in order
for SLOT in ${BOOT_ORDER}; do
  if test "${SLOT}" = "A"; then
    if test ${BOOT_A_LEFT} -gt 0; then
      # Decrement boot counter
      if test ${BOOT_A_LEFT} = 3; then
        setenv BOOT_A_LEFT 2
      elif test ${BOOT_A_LEFT} = 2; then
        setenv BOOT_A_LEFT 1
      elif test ${BOOT_A_LEFT} = 1; then
        setenv BOOT_A_LEFT 0
      fi
      saveenv

      echo "Booting slot A (attempts left: ${BOOT_A_LEFT})"

      # Load kernel, DTB, and initrd from boot slot A (partition 1)
      fatload mmc ${devnum}:1 ${kernel_addr_r} Image
      fatload mmc ${devnum}:1 ${fdt_addr_r} dtbs/rockchip/rk3328-rock64.dtb
      fatload mmc ${devnum}:1 ${ramdisk_addr_r} initrd
      setenv initrd_size ${filesize}

      setenv bootargs "${bootargs_base} root=PARTLABEL=rootfs-a rootfstype=squashfs ro"
      booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
    fi
  elif test "${SLOT}" = "B"; then
    if test ${BOOT_B_LEFT} -gt 0; then
      if test ${BOOT_B_LEFT} = 3; then
        setenv BOOT_B_LEFT 2
      elif test ${BOOT_B_LEFT} = 2; then
        setenv BOOT_B_LEFT 1
      elif test ${BOOT_B_LEFT} = 1; then
        setenv BOOT_B_LEFT 0
      fi
      saveenv

      echo "Booting slot B (attempts left: ${BOOT_B_LEFT})"

      # Load kernel, DTB, and initrd from boot slot B (partition 2)
      fatload mmc ${devnum}:2 ${kernel_addr_r} Image
      fatload mmc ${devnum}:2 ${fdt_addr_r} dtbs/rockchip/rk3328-rock64.dtb
      fatload mmc ${devnum}:2 ${ramdisk_addr_r} initrd
      setenv initrd_size ${filesize}

      setenv bootargs "${bootargs_base} root=PARTLABEL=rootfs-b rootfstype=squashfs ro"
      booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
    fi
  fi
done

echo "ERROR: No bootable slot found!"
echo "BOOT_ORDER=${BOOT_ORDER}"
echo "BOOT_A_LEFT=${BOOT_A_LEFT}"
echo "BOOT_B_LEFT=${BOOT_B_LEFT}"
reset
