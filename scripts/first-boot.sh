#!/usr/bin/env bash
# First-boot initialization — runs once on initial device boot.
#
# On first boot there is no health manifest and container images have not
# been pulled yet, so the normal os-verification health check cannot pass.
# This script confirms the current boot slot via RAUC so U-Boot's RAUC
# bootmeth knows this slot is good and stops decrementing the try counter.
set -euo pipefail

log() { echo "[first-boot] $*"; }

SENTINEL="/persist/.completed_first_boot"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

# ── Confirm the boot slot via RAUC ──
log "Marking current slot as good via RAUC"
rauc status mark-good

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
