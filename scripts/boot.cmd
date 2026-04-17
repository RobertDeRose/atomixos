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
# Boot confirmation flow:
#   Linux writes a "slot_good" file to the boot FAT partition after
#   successful boot. On next boot, this script detects the file, restores
#   the boot counter to 3, and deletes the file. This avoids using
#   fw_setenv from Linux, which triggers a firmware bug in the NCard eMMC
#   module (raw writes to the eMMC user data area brick the device).
#
# Device detection:
#   The script auto-detects the boot MMC device via U-Boot's devnum variable
#   (set by bootflow scan). Falls back to 0 if unset.
#
# Root filesystem identification:
#   Uses GPT partition labels (PARTLABEL=rootfs-a / rootfs-b) instead of
#   device numbers, since U-Boot and Linux may assign different mmcblk numbers
#   to the same physical device.

echo "AtomixOS build: @buildId@"
echo ""

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

# ── Check for slot confirmation from Linux ────────────────────────────────────
# If Linux marked the slot as good, restore boot counter and clean up.
# The slot_good file is written by first-boot.service to the boot FAT partition.
setenv slot_confirmed 0

# Check boot slot A for confirmation
fatload mmc ${devnum}:1 ${loadaddr} slot_good
if test $? -eq 0; then
  echo "Slot A confirmed good by Linux — restoring counter"
  setenv BOOT_A_LEFT 3
  saveenv
  fatrm mmc ${devnum}:1 slot_good
  setenv slot_confirmed 1
fi

# Check boot slot B for confirmation (if B is ever used)
if test ${slot_confirmed} -eq 0; then
  fatload mmc ${devnum}:2 ${loadaddr} slot_good
  if test $? -eq 0; then
    echo "Slot B confirmed good by Linux — restoring counter"
    setenv BOOT_B_LEFT 3
    saveenv
    fatrm mmc ${devnum}:2 slot_good
  fi
fi

# ── Try each slot in order ────────────────────────────────────────────────────
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
echo "Dropping to U-Boot shell for debugging..."
