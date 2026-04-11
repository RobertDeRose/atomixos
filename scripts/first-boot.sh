#!/usr/bin/env bash
# First-boot initialization — runs once on initial device boot.
#
# On first boot there is no health manifest and container images have not
# been pulled yet, so the normal os-verification health check cannot pass.
# This script unconditionally marks the RAUC slot as good and writes a
# sentinel file so it never runs again.
#
# Dependencies (must be on PATH): rauc
set -euo pipefail

log() { echo "[first-boot] $*"; }

SENTINEL="/persist/.completed_first_boot"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

# ── Mark the RAUC slot as good ──
# On first boot the slot is pending confirmation. Mark it good immediately
# so the boot-count doesn't decrement and trigger a rollback.
log "First boot detected — marking RAUC slot as good"
rauc status mark-good 2>/dev/null || {
	log "rauc mark-good failed (expected if no RAUC on this platform)"
}

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
