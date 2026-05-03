#!/usr/bin/env bash
# OS verification — post-update health-check service.
# Validates device-local services before committing the RAUC slot as "good".
set -euo pipefail

# Dependencies (must be on PATH): rauc, jq, systemctl, ip

SUSTAIN_DURATION="${ATOMIXOS_VERIFICATION_SUSTAIN_DURATION:-60}"
CHECK_INTERVAL="${ATOMIXOS_VERIFICATION_CHECK_INTERVAL:-5}"
HEALTH_REQUIRED_FILE="/data/config/health-required.json"
LAN_SETTINGS_FILE="/data/config/lan-settings.json"

log() { echo "[os-verification] $*"; }

read_gateway_ip() {
	if [ ! -f "$LAN_SETTINGS_FILE" ]; then
		printf '%s\n' '172.20.30.1'
		return 0
	fi
	jq -er '.gateway_ip // "172.20.30.1"' "$LAN_SETTINGS_FILE" 2>/dev/null || printf '%s\n' '172.20.30.1'
}

read_required_units() {
	if [ ! -f "$HEALTH_REQUIRED_FILE" ]; then
		return 0
	fi
	jq -r '.[]' "$HEALTH_REQUIRED_FILE"
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
		exit 1
	fi
	log "Assuming first boot, marking good: $BOOT_SLOT"
	if rauc status mark-good "$BOOT_SLOT"; then
		log "Slot marked good during fallback verification path"
		exit 0
	fi
	log "Failed to mark slot good during fallback verification path"
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
	exit 0
fi

log "Slot is pending confirmation, running health checks..."
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	log "Could not determine boot slot from /proc/cmdline"
	exit 1
fi

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

# Check eth1 is the configured LAN gateway IP
EXPECTED_ETH1_IP="$(read_gateway_ip)"
ETH1_IP=$(ip -4 addr show eth1 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
if [ "$ETH1_IP" = "$EXPECTED_ETH1_IP" ]; then
	log "  OK eth1 is $EXPECTED_ETH1_IP"
else
	log "  FAIL eth1 is not $EXPECTED_ETH1_IP (got: $ETH1_IP)"
	SYSTEM_OK=false
fi

if [ "$SYSTEM_OK" != "true" ]; then
	log "FAIL: System health checks failed"
	exit 1
fi

log "System health checks passed"

log "Checking required provisioned units..."
while IFS= read -r required_unit; do
	[ -n "$required_unit" ] || continue
	if systemctl is-active --quiet "${required_unit}.service" 2>/dev/null; then
		log "  OK ${required_unit}.service is active"
	else
		log "  FAIL ${required_unit}.service is NOT active"
		exit 1
	fi
done < <(read_required_units)

# ── Step 3: Sustained health check (60s) ──
log "Starting sustained health check (${SUSTAIN_DURATION}s)..."

ELAPSED=0
while [ "$ELAPSED" -lt "$SUSTAIN_DURATION" ]; do
	sleep "$CHECK_INTERVAL"
	ELAPSED=$((ELAPSED + CHECK_INTERVAL))

	# Check system services still up
	if ! systemctl is-active --quiet "dnsmasq.service" 2>/dev/null; then
		log "FAIL: dnsmasq stopped during sustained check"
		exit 1
	fi

	while IFS= read -r required_unit; do
		[ -n "$required_unit" ] || continue
		if ! systemctl is-active --quiet "${required_unit}.service" 2>/dev/null; then
			log "FAIL: ${required_unit}.service stopped during sustained check"
			exit 1
		fi
	done < <(read_required_units)
done

log "Sustained health check passed (${SUSTAIN_DURATION}s)"

# ── Step 4: Commit the slot ──
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	log "Could not determine boot slot from /proc/cmdline"
	exit 1
fi

log "All checks passed, marking slot as good: $BOOT_SLOT"
if rauc status mark-good "$BOOT_SLOT"; then
	log "Slot committed successfully"
	exit 0
fi

log "Failed to mark slot good after successful health checks"
exit 1
