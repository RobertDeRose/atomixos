#!/usr/bin/env bash
# OS verification — post-update health-check service.
# Validates device-local services before committing the RAUC slot as "good".
set -euo pipefail

# Dependencies (must be on PATH): rauc, jq, systemctl, ip

SUSTAIN_DURATION="${ATOMIXOS_VERIFICATION_SUSTAIN_DURATION:-60}"
CHECK_INTERVAL="${ATOMIXOS_VERIFICATION_CHECK_INTERVAL:-5}"
FORENSICS_STATE_DIR="${ATOMIXOS_FORENSICS_RAUC_STATE_DIR:-/data/rauc/forensics}"

log() { echo "[os-verification] $*"; }

forensic() {
	if command -v forensic-log >/dev/null 2>&1; then
		forensic-log "$@" || true
	fi
}

clear_pending_slot_state() {
	rm -f \
		"$FORENSICS_STATE_DIR/pending-source-slot" \
		"$FORENSICS_STATE_DIR/pending-target-slot" \
		"$FORENSICS_STATE_DIR/pending-target-version" \
		"$FORENSICS_STATE_DIR/pending-target-booted"
}

current_boot_slot() {
	local arg
	for arg in $(</proc/cmdline); do
		case "$arg" in
		rauc.slot=boot.*)
			printf '%s\n' "${arg#rauc.slot=}"
			return 0
			;;
		esac
	done
	return 1
}

# ── Step 1: Check if slot is already committed ──
RAUC_STATUS_JSON="$(rauc status --output-format=json 2>/dev/null || true)"
SLOT_STATUS=$(printf '%s\n' "$RAUC_STATUS_JSON" | jq -r '.booted // empty' 2>/dev/null || true)
if [ -z "$SLOT_STATUS" ]; then
	log "Could not determine RAUC slot status"
	# On first boot or non-RAUC system, fall back to the explicit boot slot.
	BOOT_SLOT="$(current_boot_slot || true)"
	if [ -z "$BOOT_SLOT" ]; then
		log "Could not determine boot slot from /proc/cmdline"
		forensic --stage verify --event failed --reason missing-boot-slot
		exit 1
	fi
	log "Assuming first boot, marking good: $BOOT_SLOT"
	forensic --stage verify --event start --slot "$BOOT_SLOT"
	forensic --stage rauc --event mark-good-start --slot "$BOOT_SLOT"
	if rauc status mark-good "$BOOT_SLOT"; then
		forensic --stage rauc --event mark-good-complete --slot "$BOOT_SLOT" --result ok
		clear_pending_slot_state
		forensic --stage verify --event complete --slot "$BOOT_SLOT" --result ok
		exit 0
	fi
	forensic --stage rauc --event mark-good-failed --slot "$BOOT_SLOT" --reason initial-boot
	forensic --stage verify --event failed --slot "$BOOT_SLOT" --reason mark-good-failed
	exit 1
fi

BOOT_GOOD=$(printf '%s\n' "$RAUC_STATUS_JSON" | jq -r '
	.booted as $booted
	| .slots[]
	| to_entries[]
	| select(.key == $booted)
	| .value.boot_status // "unknown"
' 2>/dev/null || true)
if [ "$BOOT_GOOD" = "good" ]; then
	log "Slot already marked good, nothing to do"
	forensic --stage verify --event complete --result already-good
	exit 0
fi

log "Slot is pending confirmation, running health checks..."
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	forensic --stage verify --event failed --reason missing-boot-slot
	exit 1
fi
forensic --stage verify --event start --slot "$BOOT_SLOT"

# ── Step 2: System health checks ──
check_service() {
	local svc="$1"
	if systemctl is-active --quiet "$svc" 2>/dev/null; then
		log "  OK $svc is active"
		return 0
	else
		log "  FAIL $svc is NOT active"
		return 1
	fi
}

log "Checking system services..."
SYSTEM_OK=true

check_service "dnsmasq.service" || SYSTEM_OK=false
check_service "chronyd.service" || SYSTEM_OK=false

# Check eth0 has an IP (WAN)
ETH0_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
if [ -n "$ETH0_IP" ]; then
	log "  OK eth0 has WAN address: $ETH0_IP"
else
	log "  FAIL eth0 has no WAN address"
	SYSTEM_OK=false
fi

# Check eth1 is 172.20.30.1 (LAN)
ETH1_IP=$(ip -4 addr show eth1 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
if [ "$ETH1_IP" = "172.20.30.1" ]; then
	log "  OK eth1 is 172.20.30.1"
else
	log "  FAIL eth1 is not 172.20.30.1 (got: $ETH1_IP)"
	SYSTEM_OK=false
fi

if [ "$SYSTEM_OK" != "true" ]; then
	log "FAIL: System health checks failed"
	forensic --stage verify --event failed --slot "$BOOT_SLOT" --reason system-health
	exit 1
fi

log "System health checks passed"

# ── Step 3: Sustained health check (60s) ──
log "Starting sustained health check (${SUSTAIN_DURATION}s)..."

ELAPSED=0
while [ "$ELAPSED" -lt "$SUSTAIN_DURATION" ]; do
	sleep "$CHECK_INTERVAL"
	ELAPSED=$((ELAPSED + CHECK_INTERVAL))

	# Check system services still up
	if ! systemctl is-active --quiet "dnsmasq.service" 2>/dev/null; then
		log "FAIL: dnsmasq stopped during sustained check"
		forensic --stage verify --event failed --slot "$BOOT_SLOT" --reason sustained-check
		exit 1
	fi
done

log "Sustained health check passed (${SUSTAIN_DURATION}s)"

# ── Step 4: Commit the slot ──
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	log "Could not determine boot slot from /proc/cmdline"
	forensic --stage verify --event failed --reason missing-boot-slot
	exit 1
fi

log "All checks passed, marking slot as good: $BOOT_SLOT"
forensic --stage rauc --event mark-good-start --slot "$BOOT_SLOT"
if rauc status mark-good "$BOOT_SLOT"; then
	forensic --stage rauc --event mark-good-complete --slot "$BOOT_SLOT" --result ok
	clear_pending_slot_state
	forensic --stage verify --event complete --slot "$BOOT_SLOT" --result ok
	log "Slot committed successfully"
	exit 0
fi

forensic --stage rauc --event mark-good-failed --slot "$BOOT_SLOT" --reason health-check
forensic --stage verify --event failed --slot "$BOOT_SLOT" --reason mark-good-failed
exit 1
