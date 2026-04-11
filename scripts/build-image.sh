#!/usr/bin/env bash
# Build a flashable disk image for the Rock64 eMMC.
# Called from the Nix derivation — variables are substituted by Nix:
#   @kernel@       — path to kernel package (contains Image and dtbs/)
#   @dtbPath@      — relative DTB path (e.g. rockchip/rk3328-rock64.dtb)
#   @squashfs@     — path to squashfs image directory (contains rootfs.squashfs)
#   @bootScript@   — path to boot-script directory (contains boot.scr)
#   @out@          — Nix output path
# shellcheck disable=SC2154  # Variables are injected by Nix substitute
set -euo pipefail

# ── Partition layout (sizes in MiB) ───────────────────────────────────────────
#
# Offset     Size       Content
# 0          4 MiB      U-Boot (raw, idbloader @ sector 64, u-boot.itb @ sector 16384)
# 4 MiB      128 MiB    boot slot A (vfat) — kernel + DTB + boot.scr
# 132 MiB    128 MiB    boot slot B (vfat) — empty
# 260 MiB    1024 MiB   rootfs slot A (squashfs)
# 1284 MiB   1024 MiB   rootfs slot B (empty)
# No persist partition — systemd-repart creates it on first boot.

BOOT_A_START_MIB=4
BOOT_A_SIZE_MIB=128
BOOT_B_START_MIB=132
BOOT_B_SIZE_MIB=128
ROOTFS_A_START_MIB=260
ROOTFS_A_SIZE_MIB=1024
ROOTFS_B_START_MIB=1284
ROOTFS_B_SIZE_MIB=1024

# Total image size: end of rootfs-b
IMAGE_SIZE_MIB=$((ROOTFS_B_START_MIB + ROOTFS_B_SIZE_MIB))

log() { echo "[build-image] $*"; }

mkdir -p "$out"
IMAGE="$out/rock64.img"

# ── Create sparse image file ──────────────────────────────────────────────────

log "Creating ${IMAGE_SIZE_MIB} MiB sparse image..."
truncate -s "${IMAGE_SIZE_MIB}M" "$IMAGE"

# ── Write U-Boot ──────────────────────────────────────────────────────────────

log "Writing U-Boot idbloader.img to sector 64..."
dd if="@uboot@/idbloader.img" of="$IMAGE" seek=64 conv=notrunc bs=512 status=none

log "Writing U-Boot u-boot.itb to sector 16384..."
dd if="@uboot@/u-boot.itb" of="$IMAGE" seek=16384 conv=notrunc bs=512 status=none

# ── Create GPT partition table ────────────────────────────────────────────────

log "Creating GPT partition table..."
sfdisk "$IMAGE" <<EOF
label: gpt

start=${BOOT_A_START_MIB}MiB, size=${BOOT_A_SIZE_MIB}MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="boot-a"
start=${BOOT_B_START_MIB}MiB, size=${BOOT_B_SIZE_MIB}MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="boot-b"
start=${ROOTFS_A_START_MIB}MiB, size=${ROOTFS_A_SIZE_MIB}MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="rootfs-a"
start=${ROOTFS_B_START_MIB}MiB, size=${ROOTFS_B_SIZE_MIB}MiB, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="rootfs-b"
EOF

# ── Create boot slot A (vfat with kernel + DTB + boot.scr) ────────────────────

log "Creating boot slot A vfat image..."
BOOT_VFAT=$(mktemp)
dd if=/dev/zero of="$BOOT_VFAT" bs=1M count="${BOOT_A_SIZE_MIB}" status=none
mkfs.vfat -n "BOOT-A" "$BOOT_VFAT"

# Copy kernel, DTB, and boot script using mtools (no mount required)
mmd -i "$BOOT_VFAT" ::dtbs
mmd -i "$BOOT_VFAT" ::dtbs/rockchip
mcopy -i "$BOOT_VFAT" "@kernel@/Image" ::Image
mcopy -i "$BOOT_VFAT" "@kernel@/dtbs/@dtbPath@" "::dtbs/rockchip/rk3328-rock64.dtb"
mcopy -i "$BOOT_VFAT" "@bootScript@/boot.scr" ::boot.scr

# Write boot vfat into the image at the correct offset
dd if="$BOOT_VFAT" of="$IMAGE" bs=1M seek="${BOOT_A_START_MIB}" conv=notrunc status=none
rm -f "$BOOT_VFAT"

# ── Create empty boot slot B (vfat) ──────────────────────────────────────────

log "Creating boot slot B (empty vfat)..."
BOOT_B_VFAT=$(mktemp)
dd if=/dev/zero of="$BOOT_B_VFAT" bs=1M count="${BOOT_B_SIZE_MIB}" status=none
mkfs.vfat -n "BOOT-B" "$BOOT_B_VFAT"
dd if="$BOOT_B_VFAT" of="$IMAGE" bs=1M seek="${BOOT_B_START_MIB}" conv=notrunc status=none
rm -f "$BOOT_B_VFAT"

# ── Write squashfs to rootfs slot A ──────────────────────────────────────────

log "Writing squashfs to rootfs slot A..."
dd if="@squashfs@/rootfs.squashfs" of="$IMAGE" bs=1M seek="${ROOTFS_A_START_MIB}" conv=notrunc status=none

# ── Summary ──────────────────────────────────────────────────────────────────

ACTUAL_SIZE=$(stat -c%s "$IMAGE" 2>/dev/null || stat -f%z "$IMAGE")
log ""
log "=== Image build complete ==="
log ""
log "Image: $IMAGE"
log "Size: $((ACTUAL_SIZE / 1024 / 1024)) MiB"
log ""
log "Partition layout:"
log "  boot-a   (vfat, ${BOOT_A_SIZE_MIB} MiB)  — kernel + DTB + boot.scr"
log "  boot-b   (vfat, ${BOOT_B_SIZE_MIB} MiB)  — empty (for future updates)"
log "  rootfs-a (${ROOTFS_A_SIZE_MIB} MiB)       — squashfs deployed"
log "  rootfs-b (${ROOTFS_B_SIZE_MIB} MiB)       — empty (for future updates)"
log "  persist  — created on first boot by systemd-repart"
log ""
log "Flash with: dd if=$IMAGE of=/dev/mmcblkN bs=4M status=progress"
log "Or use a tool like Etcher."
