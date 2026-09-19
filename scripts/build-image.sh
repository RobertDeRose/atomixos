#!/usr/bin/env bash
# Build a flashable disk image for the Rock64 eMMC.
# Called from the Nix derivation — variables are substituted by Nix:
#   @bootPartition@ — path to the shared boot partition image
#   @squashfs@     — path to squashfs image directory (contains rootfs.squashfs)
#   @out@          — Nix output path
# shellcheck disable=SC2154  # Variables are injected by Nix substitute
set -euo pipefail

# ── Partition layout (sizes in MiB) ───────────────────────────────────────────
#
# Offset     Size       Content
# 0          16 MiB     U-Boot (raw, idbloader @ sector 64, u-boot.itb @ sector 16384)
# 16 MiB     128 MiB    boot slot A (vfat) — kernel + DTB + boot.scr
# 144 MiB    1024 MiB   rootfs slot A (squashfs, Linux root aarch64 type)
# Slot B and /data are created by initrd systemd-repart on first boot,
# using the remaining eMMC space.
#
# Boot partitions use linux-generic type, and rootfs uses the Linux root
# aarch64 type.
#
# NOTE: The first partition MUST start at or after 16 MiB to avoid overwriting
# u-boot.itb which is written at sector 16384 (byte offset 8 MiB, ~9 MiB end).

XBOOTLDR_TYPE_GUID=@bootTypeGuid@
ROOT_ARM64_TYPE_GUID=@rootfsTypeGuid@

BOOT_A_START_MIB=@bootStartMiB@
BOOT_A_SIZE_MIB=@bootSizeMiB@
ROOTFS_A_START_MIB=@rootfsStartMiB@
ROOTFS_A_SIZE_MIB=@rootfsSizeMiB@

# Total image size: end of rootfs-a plus slack for the backup GPT header/table.
GPT_TAIL_SLACK_MIB=@gptTailSlackMiB@
IMAGE_SIZE_MIB=$((ROOTFS_A_START_MIB + ROOTFS_A_SIZE_MIB + GPT_TAIL_SLACK_MIB))

log() { echo "[build-image] $*"; }

mkdir -p "$out"
IMAGE="$out/@imageName@"

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

start=${BOOT_A_START_MIB}MiB, size=${BOOT_A_SIZE_MIB}MiB, type=${XBOOTLDR_TYPE_GUID}, name="@bootLabelA@"
start=${ROOTFS_A_START_MIB}MiB, size=${ROOTFS_A_SIZE_MIB}MiB, type=${ROOT_ARM64_TYPE_GUID}, name="@rootfsLabelA@"
EOF

# Write boot vfat into the image at the correct offset
log "Writing shared boot filesystem to boot slot A..."
dd if="@bootPartition@/boot.vfat" of="$IMAGE" bs=1M seek="${BOOT_A_START_MIB}" conv=notrunc status=none

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
log "  rootfs-a (${ROOTFS_A_SIZE_MIB} MiB)       — squashfs deployed"
log "  @bootLabelB@   (vfat, ${BOOT_A_SIZE_MIB} MiB)  — created on first boot by initrd systemd-repart"
log "  @rootfsLabelB@ (${ROOTFS_A_SIZE_MIB} MiB)       — created on first boot by initrd systemd-repart"
log "  data     — created on first boot by initrd systemd-repart"
log ""
log "Flash with: dd if=$IMAGE of=/dev/mmcblkN bs=4M status=progress"
log "Or use a tool like Etcher."
