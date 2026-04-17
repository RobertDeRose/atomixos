#!/usr/bin/env bash
# First-boot initialization — runs once on initial device boot.
#
# On first boot there is no health manifest and container images have not
# been pulled yet, so the normal os-verification health check cannot pass.
# This script writes a "slot_good" flag to the boot FAT partition (/boot)
# so U-Boot restores the boot counter on next boot. It also writes a
# sentinel file so it never runs again.
#
# The flag-file approach avoids using fw_setenv, which triggers a firmware
# bug in the NCard eMMC module (raw writes to the eMMC user data area
# brick the device). Instead, U-Boot reads the flag from the FAT partition
# and calls saveenv itself.
set -euo pipefail

log() { echo "[first-boot] $*"; }

SENTINEL="/persist/.completed_first_boot"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

# ── Mark the boot slot as good ──
# Write a flag file to the boot FAT partition. U-Boot will detect this
# on next boot, restore BOOT_x_LEFT to 3, saveenv, and delete the file.
log "First boot detected — writing slot_good flag to /boot"
date -Iseconds >/boot/slot_good
sync

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
