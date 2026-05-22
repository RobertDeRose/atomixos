#!/usr/bin/env bash
# OS verification — post-update health-check service.
# Validates device-local services before committing the RAUC slot as "good".
set -euo pipefail

# Dependencies (must be on PATH): rauc, jq, systemctl, ip

SUSTAIN_DURATION="${ATOMIXOS_VERIFICATION_SUSTAIN_DURATION:-60}"
CHECK_INTERVAL="${ATOMIXOS_VERIFICATION_CHECK_INTERVAL:-5}"
HEALTH_REQUIRED_FILE="/data/config/health-required.json"
LAN_SETTINGS_FILE="/data/config/lan-settings.json"
RUNTIME_METADATA_FILE="/data/config/quadlet-runtime.json"
APP_RUNTIME_USER="${ATOMIXOS_APP_RUNTIME_USER:-appsvc}"

log() { echo "[os-verification] $*" >&2; }

read_gateway_ip() {
	if [ ! -f "$LAN_SETTINGS_FILE" ]; then
		printf '%s\n' '172.20.30.1'
		return 0
	fi
	jq -er '
		.gateway_ip
		| select(
			type == "string"
			and test("^(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})(\\.(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}$")
		)
	' "$LAN_SETTINGS_FILE" 2>/dev/null || printf '%s\n' '172.20.30.1'
}

read_required_units() {
	if [ ! -f "$HEALTH_REQUIRED_FILE" ]; then
		return 0
	fi
	if ! jq -e 'type == "array"' "$HEALTH_REQUIRED_FILE" >/dev/null 2>&1; then
		log "Invalid required unit manifest: $HEALTH_REQUIRED_FILE"
		return 1
	fi
	if ! jq -e 'all(.[]; type == "string" and length > 0)' "$HEALTH_REQUIRED_FILE" >/dev/null 2>&1; then
		log "Invalid required unit manifest: $HEALTH_REQUIRED_FILE"
		return 1
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
	log "Refusing to mark slot good without a parseable RAUC status"
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
	log "Slot already marked good, running health checks without marking slot"
else
	log "Slot is pending confirmation, running health checks..."
fi

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

check_interface_ipv4() {
	local iface="$1"
	local description="$2"
	local ip_addr
	ip_addr=$(ip -4 addr show "$iface" 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
	if [ -n "$ip_addr" ]; then
		log "  OK $description: $ip_addr"
		return 0
	else
		log "  FAIL $description"
		return 1
	fi
}

check_lan_gateway_ip() {
	local expected_ip eth1_ip
	expected_ip="$(read_gateway_ip)"
	eth1_ip=$(ip -4 addr show eth1 2>/dev/null | grep -oP 'inet \K[\d.]+' || true)
	if [ "$eth1_ip" = "$expected_ip" ]; then
		log "  OK eth1 is $expected_ip"
		return 0
	else
		log "  FAIL eth1 is not $expected_ip (got: $eth1_ip)"
		return 1
	fi
}

check_apply_unit() {
	local unit="$1"
	if systemctl is-failed --quiet "$unit" 2>/dev/null; then
		log "  FAIL $unit failed"
		return 1
	fi
	if systemctl is-active --quiet "$unit" 2>/dev/null; then
		log "  OK $unit active"
		return 0
	fi
	if systemctl show -P ActiveState "$unit" 2>/dev/null | grep -qx inactive; then
		log "  OK $unit completed"
		return 0
	fi
	log "  FAIL $unit did not complete successfully"
	return 1
}

check_required_units() {
	local required_units="$1"
	local required_unit service mode uid runtime_dir
	while IFS= read -r required_unit; do
		[ -n "$required_unit" ] || continue
		service="${required_unit}.service"
		mode="$(unit_mode "$service")"
		if [ "$mode" = "rootless" ]; then
			uid="$(id -u "$APP_RUNTIME_USER" 2>/dev/null || true)"
			if [ -z "$uid" ]; then
				log "  FAIL $service rootless user $APP_RUNTIME_USER does not exist"
				return 1
			fi
			runtime_dir="/run/user/$uid"
			if runuser -u "$APP_RUNTIME_USER" -- env \
				"XDG_RUNTIME_DIR=$runtime_dir" \
				"DBUS_SESSION_BUS_ADDRESS=unix:path=$runtime_dir/bus" \
				systemctl --user is-active --quiet "$service" 2>/dev/null; then
				log "  OK $service is active ($mode)"
			else
				log "  FAIL $service is NOT active ($mode)"
				return 1
			fi
		elif systemctl is-active --quiet "$service" 2>/dev/null; then
			log "  OK $service is active ($mode)"
		else
			log "  FAIL $service is NOT active ($mode)"
			return 1
		fi
	done <<<"$required_units"
}

unit_mode() {
	local service="$1"
	if [ ! -f "$RUNTIME_METADATA_FILE" ]; then
		printf '%s\n' rootful
		return 0
	fi
	jq -r --arg service "$service" '
		(.units // [])
		| map(select(.service == $service))
		| .[0].mode // "rootful"
	' "$RUNTIME_METADATA_FILE" 2>/dev/null || printf '%s\n' rootful
}

run_health_checks() {
	local required_units="$1"
	local system_ok=true

	check_service "dnsmasq.service" || system_ok=false
	check_service "chronyd.service" || system_ok=false
	check_apply_unit "lan-gateway-apply.service" || system_ok=false
	check_apply_unit "provisioned-firewall-inbound.service" || system_ok=false
	check_interface_ipv4 "eth0" "eth0 has WAN address" || log "  WARN eth0 has no WAN address"
	check_lan_gateway_ip || system_ok=false
	check_required_units "$required_units" || system_ok=false

	[ "$system_ok" = "true" ]
}

log "Checking system services..."
REQUIRED_UNITS="$(read_required_units)"

if ! run_health_checks "$REQUIRED_UNITS"; then
	log "FAIL: System health checks failed"
	exit 1
fi

log "System health checks passed"

# ── Step 3: Sustained health check (60s) ──
log "Starting sustained health check (${SUSTAIN_DURATION}s)..."

ELAPSED=0
while [ "$ELAPSED" -lt "$SUSTAIN_DURATION" ]; do
	sleep "$CHECK_INTERVAL"
	ELAPSED=$((ELAPSED + CHECK_INTERVAL))

	if ! run_health_checks "$REQUIRED_UNITS"; then
		log "FAIL: System health regressed during sustained check"
		exit 1
	fi
done

log "Sustained health check passed (${SUSTAIN_DURATION}s)"

if [ "$BOOT_GOOD" = "good" ]; then
	log "Slot was already good; health verification complete"
	exit 0
fi

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
