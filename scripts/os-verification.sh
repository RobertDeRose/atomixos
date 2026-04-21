#!/usr/bin/env bash
# OS verification — post-update health-check service.
# Validates system services and manifest-defined containers
# before committing the RAUC slot as "good".
#
# Dependencies (must be on PATH): rauc, podman, jq, systemctl, ip
set -euo pipefail

MANIFEST="/persist/config/health-manifest.yaml"
CONTAINER_TIMEOUT=300 # 5 minutes
SUSTAIN_DURATION=60   # 60 seconds
CHECK_INTERVAL=5      # check every 5s during sustain

log() { echo "[os-verification] $*"; }

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
SLOT_STATUS=$(rauc status --output-format=json 2>/dev/null | jq -r '.booted // empty')
if [ -z "$SLOT_STATUS" ]; then
	log "Could not determine RAUC slot status"
	# On first boot or non-RAUC system, fall back to the explicit boot slot.
	BOOT_SLOT="$(current_boot_slot || true)"
	if [ -z "$BOOT_SLOT" ]; then
		log "Could not determine boot slot from /proc/cmdline"
		exit 1
	fi
	log "Assuming first boot, marking good: $BOOT_SLOT"
	rauc status mark-good "$BOOT_SLOT" || true
	exit 0
fi

BOOT_GOOD=$(rauc status --output-format=json 2>/dev/null | jq -r '.slots[] | select(.state.booted == "booted") | .state.boot_status // "unknown"')
if [ "$BOOT_GOOD" = "good" ]; then
	log "Slot already marked good, nothing to do"
	exit 0
fi

log "Slot is pending confirmation, running health checks..."

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
	exit 1
fi

log "System health checks passed"

# ── Step 3: Container health checks (manifest-driven) ──
if [ ! -f "$MANIFEST" ]; then
	log "No health manifest at $MANIFEST, skipping container checks"
else
	log "Reading health manifest..."

	# Parse YAML manifest — extract container names
	# Simple YAML parsing: look for "- name: <value>" lines under "containers:"
	CONTAINERS=$(grep -A1 '^\s*-\s*name:' "$MANIFEST" 2>/dev/null | grep 'name:' | sed 's/.*name:\s*//' | tr -d ' "'"'" || true)

	if [ -z "$CONTAINERS" ]; then
		log "No containers defined in manifest"
	else
		log "Waiting for containers to reach running state (timeout: ${CONTAINER_TIMEOUT}s)..."

		ELAPSED=0
		while [ $ELAPSED -lt $CONTAINER_TIMEOUT ]; do
			ALL_RUNNING=true
			for CONTAINER in $CONTAINERS; do
				STATE=$(podman inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
				if [ "$STATE" != "running" ]; then
					ALL_RUNNING=false
					break
				fi
			done

			if [ "$ALL_RUNNING" = "true" ]; then
				log "All manifest containers are running"
				break
			fi

			sleep 10
			ELAPSED=$((ELAPSED + 10))
		done

		if [ "$ALL_RUNNING" != "true" ]; then
			log "FAIL: Not all containers reached running state within ${CONTAINER_TIMEOUT}s"
			for CONTAINER in $CONTAINERS; do
				STATE=$(podman inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
				log "  $CONTAINER: $STATE"
			done
			exit 1
		fi
	fi
fi

# ── Step 4: Sustained health check (60s) ──
log "Starting sustained health check (${SUSTAIN_DURATION}s)..."

# Record initial restart counts for containers
declare -A INITIAL_RESTARTS
if [ -f "$MANIFEST" ]; then
	CONTAINERS=$(grep -A1 '^\s*-\s*name:' "$MANIFEST" 2>/dev/null | grep 'name:' | sed 's/.*name:\s*//' | tr -d ' "'"'" || true)
	for CONTAINER in $CONTAINERS; do
		INITIAL_RESTARTS[$CONTAINER]=$(podman inspect --format '{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo "0")
	done
fi

ELAPSED=0
while [ $ELAPSED -lt $SUSTAIN_DURATION ]; do
	sleep $CHECK_INTERVAL
	ELAPSED=$((ELAPSED + CHECK_INTERVAL))

	# Check system services still up
	if ! systemctl is-active --quiet "dnsmasq.service" 2>/dev/null; then
		log "FAIL: dnsmasq stopped during sustained check"
		exit 1
	fi

	# Check containers still running and no restarts
	if [ -f "$MANIFEST" ] && [ -n "${CONTAINERS:-}" ]; then
		for CONTAINER in $CONTAINERS; do
			STATE=$(podman inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "not_found")
			if [ "$STATE" != "running" ]; then
				log "FAIL: Container $CONTAINER stopped during sustained check (state: $STATE)"
				exit 1
			fi

			CURRENT_RESTARTS=$(podman inspect --format '{{.RestartCount}}' "$CONTAINER" 2>/dev/null || echo "0")
			if [ "$CURRENT_RESTARTS" != "${INITIAL_RESTARTS[$CONTAINER]:-0}" ]; then
				log "FAIL: Container $CONTAINER restarted during sustained check"
				exit 1
			fi
		done
	fi
done

log "Sustained health check passed (${SUSTAIN_DURATION}s)"

# ── Step 5: Commit the slot ──
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	log "Could not determine boot slot from /proc/cmdline"
	exit 1
fi

log "All checks passed, marking slot as good: $BOOT_SLOT"
rauc status mark-good "$BOOT_SLOT"
log "Slot committed successfully"
