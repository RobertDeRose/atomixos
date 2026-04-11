#!/usr/bin/env bash
# Apollo Rock64 eMMC Provisioning Script
#
# Partitions the eMMC, writes U-Boot, deploys the first image to slot A,
# and sets up the /persist partition.
#
# Usage: sudo ./provision-emmc.sh <emmc-device> <uboot-dir> <kernel-image> <dtb-file> <squashfs-image>
#
# Example:
#   sudo ./provision-emmc.sh /dev/mmcblk1 ./u-boot ./kernel/Image ./kernel/rk3328-rock64.dtb ./rootfs.squashfs

set -euo pipefail

# ── Arguments ──────────────────────────────────────────────────────────────────

EMMC_DEV="${1:?Usage: $0 <emmc-device> <uboot-dir> <kernel-image> <dtb-file> <squashfs-image>}"
UBOOT_DIR="${2:?Missing U-Boot directory (containing idbloader.img and u-boot.itb)}"
KERNEL_IMAGE="${3:?Missing kernel image path}"
DTB_FILE="${4:?Missing DTB file path}"
SQUASHFS_IMAGE="${5:?Missing squashfs image path}"

# ── Partition layout (sizes in MiB) ───────────────────────────────────────────
#
# Offset     Size       Content
# 0          4 MiB      U-Boot (raw, idbloader @ sector 64, u-boot.itb @ sector 16384)
# 4 MiB      32 MiB     boot slot A (vfat) — kernel + DTB
# 36 MiB     32 MiB     boot slot B (vfat) — kernel + DTB
# 68 MiB     200 MiB    rootfs slot A (squashfs)
# 268 MiB    200 MiB    rootfs slot B (squashfs)
# 468 MiB    remaining  /persist (f2fs)

BOOT_A_START_MIB=4
BOOT_A_SIZE_MIB=32
BOOT_B_START_MIB=36
BOOT_B_SIZE_MIB=32
ROOTFS_A_START_MIB=68
ROOTFS_A_SIZE_MIB=200
ROOTFS_B_START_MIB=268
ROOTFS_B_SIZE_MIB=200
PERSIST_START_MIB=468

# ── Validation ─────────────────────────────────────────────────────────────────

log() { echo "[provision] $*"; }
die() {
	echo "[provision] ERROR: $*" >&2
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "Must run as root"
[ -b "$EMMC_DEV" ] || die "Not a block device: $EMMC_DEV"
[ -d "$UBOOT_DIR" ] || die "Not a directory: $UBOOT_DIR"
[ -f "$UBOOT_DIR/idbloader.img" ] || die "Missing $UBOOT_DIR/idbloader.img"
[ -f "$UBOOT_DIR/u-boot.itb" ] || die "Missing $UBOOT_DIR/u-boot.itb"
[ -f "$KERNEL_IMAGE" ] || die "Missing kernel image: $KERNEL_IMAGE"
[ -f "$DTB_FILE" ] || die "Missing DTB: $DTB_FILE"
[ -f "$SQUASHFS_IMAGE" ] || die "Missing squashfs image: $SQUASHFS_IMAGE"

# Check squashfs size
SQUASHFS_SIZE=$(stat -c%s "$SQUASHFS_IMAGE" 2>/dev/null || stat -f%z "$SQUASHFS_IMAGE")
MAX_ROOTFS_SIZE=$((ROOTFS_A_SIZE_MIB * 1024 * 1024))
if [ "$SQUASHFS_SIZE" -gt "$MAX_ROOTFS_SIZE" ]; then
	die "Squashfs image ($SQUASHFS_SIZE bytes) exceeds slot size ($MAX_ROOTFS_SIZE bytes)"
fi

# ── Idempotency check ─────────────────────────────────────────────────────────

if sfdisk -d "$EMMC_DEV" &>/dev/null; then
	EXISTING_PARTS=$(sfdisk -d "$EMMC_DEV" 2>/dev/null | grep -c "^${EMMC_DEV}p" || true)
	if [ "$EXISTING_PARTS" -gt 0 ]; then
		log "WARNING: $EMMC_DEV already has $EXISTING_PARTS partition(s)"
		log "This will DESTROY all existing data on $EMMC_DEV"
		read -rp "Type 'yes' to continue: " CONFIRM
		if [ "$CONFIRM" != "yes" ]; then
			log "Aborted"
			exit 1
		fi
	fi
fi

# ── Unmount any existing partitions ────────────────────────────────────────────

log "Unmounting any existing partitions on $EMMC_DEV..."
for part in "${EMMC_DEV}p"*; do
	if mountpoint -q "$part" 2>/dev/null || mount | grep -q "$part"; then
		umount "$part" 2>/dev/null || true
	fi
done

# ── Write U-Boot ───────────────────────────────────────────────────────────────

log "Writing U-Boot idbloader.img to sector 64..."
dd if="$UBOOT_DIR/idbloader.img" of="$EMMC_DEV" seek=64 conv=notrunc bs=512 status=progress

log "Writing U-Boot u-boot.itb to sector 16384..."
dd if="$UBOOT_DIR/u-boot.itb" of="$EMMC_DEV" seek=16384 conv=notrunc bs=512 status=progress

# ── Partition the eMMC ─────────────────────────────────────────────────────────

log "Creating partition table..."
sfdisk "$EMMC_DEV" <<EOF
label: gpt

# boot slot A (vfat)
start=${BOOT_A_START_MIB}MiB, size=${BOOT_A_SIZE_MIB}MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="boot-a"

# boot slot B (vfat)
start=${BOOT_B_START_MIB}MiB, size=${BOOT_B_SIZE_MIB}MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="boot-b"

# rootfs slot A
start=${ROOTFS_A_START_MIB}MiB, size=${ROOTFS_A_SIZE_MIB}MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="rootfs-a"

# rootfs slot B
start=${ROOTFS_B_START_MIB}MiB, size=${ROOTFS_B_SIZE_MIB}MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="rootfs-b"

# /persist
start=${PERSIST_START_MIB}MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="persist"
EOF

# Force kernel to re-read partition table
partprobe "$EMMC_DEV" || true
sleep 2

# ── Create filesystems ─────────────────────────────────────────────────────────

log "Creating vfat on boot slot A (${EMMC_DEV}p1)..."
mkfs.vfat -n "BOOT-A" "${EMMC_DEV}p1"

log "Creating vfat on boot slot B (${EMMC_DEV}p2)..."
mkfs.vfat -n "BOOT-B" "${EMMC_DEV}p2"

# rootfs partitions don't need a filesystem — squashfs is written directly

log "Creating f2fs on /persist (${EMMC_DEV}p5)..."
mkfs.f2fs -l "persist" -f "${EMMC_DEV}p5"

# ── Deploy boot slot A ─────────────────────────────────────────────────────────

log "Deploying kernel and DTB to boot slot A..."
BOOT_A_MNT=$(mktemp -d)
mount "${EMMC_DEV}p1" "$BOOT_A_MNT"

mkdir -p "$BOOT_A_MNT/dtbs/rockchip"
cp "$KERNEL_IMAGE" "$BOOT_A_MNT/Image"
cp "$DTB_FILE" "$BOOT_A_MNT/dtbs/rockchip/rk3328-rock64.dtb"

umount "$BOOT_A_MNT"
rmdir "$BOOT_A_MNT"

# ── Deploy rootfs slot A ───────────────────────────────────────────────────────

log "Writing squashfs image to rootfs slot A (${EMMC_DEV}p3)..."
dd if="$SQUASHFS_IMAGE" of="${EMMC_DEV}p3" bs=4M status=progress

# ── Set U-Boot environment ─────────────────────────────────────────────────────

log "Setting U-Boot environment variables..."
# fw_setenv requires U-Boot tools and proper env config
# These set the initial boot-count variables for RAUC
if command -v fw_setenv &>/dev/null; then
	fw_setenv BOOT_ORDER "A B"
	fw_setenv BOOT_A_LEFT 3
	fw_setenv BOOT_B_LEFT 0
	log "U-Boot environment set: BOOT_ORDER=A B, BOOT_A_LEFT=3, BOOT_B_LEFT=0"
else
	log "WARNING: fw_setenv not available — U-Boot env must be set manually or via U-Boot console"
	log "  Required variables:"
	log "    BOOT_ORDER=A B"
	log "    BOOT_A_LEFT=3"
	log "    BOOT_B_LEFT=0"
fi

# ── Done ───────────────────────────────────────────────────────────────────────

log ""
log "=== Provisioning complete ==="
log ""
log "Partition layout on $EMMC_DEV:"
log "  p1: boot-a  (vfat, ${BOOT_A_SIZE_MIB} MiB) — kernel + DTB"
log "  p2: boot-b  (vfat, ${BOOT_B_SIZE_MIB} MiB) — empty (for future updates)"
log "  p3: rootfs-a (${ROOTFS_A_SIZE_MIB} MiB) — squashfs deployed"
log "  p4: rootfs-b (${ROOTFS_B_SIZE_MIB} MiB) — empty (for future updates)"
log "  p5: persist  (f2fs, remaining) — writable storage"
log ""
log "Remove SD card and reboot to boot from eMMC."
