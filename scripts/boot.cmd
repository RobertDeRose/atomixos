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
# Partition mapping:
#   Slot A: boot=mmcblk1p1, rootfs=mmcblk1p3
#   Slot B: boot=mmcblk1p2, rootfs=mmcblk1p4

# Default values if not set
test -n "${BOOT_ORDER}" || setenv BOOT_ORDER "A B"
test -n "${BOOT_A_LEFT}" || setenv BOOT_A_LEFT 3
test -n "${BOOT_B_LEFT}" || setenv BOOT_B_LEFT 3

setenv bootargs_base "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xff130000 loglevel=7"

# Try each slot in order
for SLOT in ${BOOT_ORDER}; do
  if test "${SLOT}" = "A"; then
    if test ${BOOT_A_LEFT} -gt 0; then
      setexpr BOOT_A_LEFT ${BOOT_A_LEFT} - 1
      saveenv

      echo "Booting slot A (attempts left: ${BOOT_A_LEFT})"

      # Load kernel and DTB from boot slot A (partition 1)
      fatload mmc 1:1 ${kernel_addr_r} Image
      fatload mmc 1:1 ${fdt_addr_r} dtbs/rockchip/rk3328-rock64.dtb

      setenv bootargs "${bootargs_base} root=/dev/mmcblk1p3 rootfstype=squashfs ro"
      booti ${kernel_addr_r} - ${fdt_addr_r}
    fi
  elif test "${SLOT}" = "B"; then
    if test ${BOOT_B_LEFT} -gt 0; then
      setexpr BOOT_B_LEFT ${BOOT_B_LEFT} - 1
      saveenv

      echo "Booting slot B (attempts left: ${BOOT_B_LEFT})"

      # Load kernel and DTB from boot slot B (partition 2)
      fatload mmc 1:2 ${kernel_addr_r} Image
      fatload mmc 1:2 ${fdt_addr_r} dtbs/rockchip/rk3328-rock64.dtb

      setenv bootargs "${bootargs_base} root=/dev/mmcblk1p4 rootfstype=squashfs ro"
      booti ${kernel_addr_r} - ${fdt_addr_r}
    fi
  fi
done

echo "ERROR: No bootable slot found!"
echo "BOOT_ORDER=${BOOT_ORDER}"
echo "BOOT_A_LEFT=${BOOT_A_LEFT}"
echo "BOOT_B_LEFT=${BOOT_B_LEFT}"
reset
