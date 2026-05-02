#!/usr/bin/env bash
# First-boot initialization — runs once on initial device boot.
#
# On first boot there is no health manifest and container images have not
# been pulled yet, so the normal os-verification health check cannot pass.
# This script confirms the current boot slot via RAUC so U-Boot's RAUC
# bootmeth knows this slot is good and stops decrementing the try counter.
set -euo pipefail

log() { echo "[first-boot] $*"; }
CONFIG_ROOT="${ATOMIXOS_CONFIG_ROOT:-/data/config}"
CONFIG_TOML="$CONFIG_ROOT/config.toml"
QUADLET_ACTIVE_DIR="${ATOMIXOS_QUADLET_ACTIVE_DIR:-/etc/containers/systemd}"
BOOTSTRAP_PORT="${ATOMIXOS_BOOTSTRAP_PORT:-8080}"
BOOTSTRAP_HOST="${ATOMIXOS_BOOTSTRAP_HOST:-172.20.30.1}"
INITRD_MARKER="${ATOMIXOS_INITRD_MARKER:-/etc/atomixos/fresh-flash}"
BOOT_CONFIG_PATH="${ATOMIXOS_BOOT_CONFIG_PATH:-/boot/config.toml}"
APP_RUNTIME_QUADLET_DIR="${ATOMIXOS_ROOTLESS_QUADLET_DIR:-/var/lib/appsvc/.config/containers/systemd}"
RAUC_ENABLED="${ATOMIXOS_RAUC_ENABLE:-1}"
LAN_SETTINGS_FILE="$CONFIG_ROOT/lan-settings.json"

read_bootstrap_host() {
	if [ ! -f "$LAN_SETTINGS_FILE" ]; then
		printf '%s\n' "$BOOTSTRAP_HOST"
		return 0
	fi

	python3 - "$LAN_SETTINGS_FILE" "$BOOTSTRAP_HOST" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
default = sys.argv[2]
try:
    payload = json.loads(path.read_text())
except Exception:
    print(default)
    raise SystemExit(0)

print(payload.get("gateway_ip", default))
PY
}

enable_dev_ssh_on_wan() {
	local flag_file="$CONFIG_ROOT/ssh-wan-enabled"

	if [ "${ATOMIXOS_DEV_ENABLE_SSH_WAN:-}" != "1" ] || [ -f "$flag_file" ]; then
		return 0
	fi

	mkdir -p "$(dirname "$flag_file")"
	log "Enabling SSH on WAN for development image"
	: >"$flag_file"
}

write_dev_health_requirements() {
	local health_file="$CONFIG_ROOT/health-required.json"

	if [ "${ATOMIXOS_DEV_ENABLE_SSH_WAN:-}" != "1" ] || [ -f "$health_file" ]; then
		return 0
	fi

	mkdir -p "$CONFIG_ROOT"
	printf '%s\n' '[]' >"$health_file"
	chmod 600 "$health_file"
}

ensure_rauc_env() {
	if fw_printenv BOOT_ORDER >/dev/null 2>&1; then
		return 0
	fi

	log "Seeding missing SPI boot environment for RAUC"
	fw_setenv BOOT_ORDER "A B"
	fw_setenv BOOT_A_LEFT 3
	fw_setenv BOOT_B_LEFT 3
}

current_boot_slot() {
	local arg
	if [ -n "${ATOMIXOS_BOOT_SLOT:-}" ]; then
		printf '%s\n' "$ATOMIXOS_BOOT_SLOT"
		return 0
	fi
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

is_fresh_flash() {
	[ -f "$INITRD_MARKER" ]
}

find_usb_config() {
	local search_dir device mount_dir
	for search_dir in ${ATOMIXOS_USB_SEARCH_DIRS:-/dev/disk/by-label /dev/disk/by-partlabel}; do
		[ -d "$search_dir" ] || continue
		for device in "$search_dir"/*; do
			[ -e "$device" ] || continue
			case "$device" in
			*/boot-a | */boot-b | */data | */rootfs-a | */rootfs-b)
				continue
				;;
			esac
			mount_dir="$(mktemp -d /run/atomixos-usb-config.XXXXXX)"
			if mount -t vfat -o ro "$device" "$mount_dir" >/dev/null 2>&1; then
				if [ -f "$mount_dir/config.toml" ]; then
					printf '%s\n' "$mount_dir/config.toml"
					return 0
				fi
				umount "$mount_dir" >/dev/null 2>&1 || true
			fi
			rmdir "$mount_dir" >/dev/null 2>&1 || true
		done
	done
	return 1
}

cleanup_seed_source() {
	local source_path="$1"
	local mount_dir
	case "$source_path" in
	/run/atomixos-usb-config.*/config.toml)
		mount_dir="${source_path%/config.toml}"
		umount "$mount_dir" >/dev/null 2>&1 || true
		rmdir "$mount_dir" >/dev/null 2>&1 || true
		;;
	esac
}

bootstrap_web_console() {
	local temp_config
	local host
	temp_config="$(mktemp /run/atomixos-bootstrap-config.XXXXXX.toml)"
	rm -f "$temp_config"
	host="$(read_bootstrap_host)"
	log "Starting bootstrap web console on $host:$BOOTSTRAP_PORT"
	first-boot-provision serve "$CONFIG_ROOT" "$temp_config" --host "$host" --port "$BOOTSTRAP_PORT" &
	local server_pid=$!
	while kill -0 "$server_pid" >/dev/null 2>&1; do
		if [ -f "$temp_config" ]; then
			kill "$server_pid" >/dev/null 2>&1 || true
			wait "$server_pid" 2>/dev/null || true
			rm -f "$temp_config"
			return 0
		fi
		sleep 1
	done
	rm -f "$temp_config"
	return 1
}

sync_quadlet_units() {
	if command -v systemctl >/dev/null 2>&1; then
		if ! systemctl restart quadlet-sync.service; then
			log "WARNING: quadlet-sync.service failed; continuing first boot for debugging access"
		fi
		if systemctl list-unit-files lan-gateway-apply.service >/dev/null 2>&1; then
			if ! systemctl restart lan-gateway-apply.service; then
				log "WARNING: lan-gateway-apply.service failed; continuing first boot for debugging access"
			fi
		fi
		if systemctl list-unit-files provisioned-firewall-inbound.service >/dev/null 2>&1; then
			if ! systemctl restart provisioned-firewall-inbound.service; then
				log "WARNING: provisioned-firewall-inbound.service failed; continuing first boot for debugging access"
			fi
		fi
	else
		mkdir -p "$QUADLET_ACTIVE_DIR"
		if ! first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$APP_RUNTIME_QUADLET_DIR"; then
			log "WARNING: quadlet sync failed; continuing first boot for debugging access"
		fi
	fi
}

import_seed_config() {
	local source_path="$1"
	local status=0
	log "Importing provisioning config from $source_path"
	if first-boot-provision import "$source_path" "$CONFIG_ROOT"; then
		status=0
	else
		status=$?
	fi
	cleanup_seed_source "$source_path"
	if [ "$status" -ne 0 ]; then
		return "$status"
	fi
	sync_quadlet_units
}

has_valid_provisioning() {
	[ -f "$CONFIG_TOML" ] && first-boot-provision validate "$CONFIG_TOML" >/dev/null 2>&1
}

discover_and_import_provisioning() {
	local seed_path usb_path
	if has_valid_provisioning; then
		log "Using existing provisioned config from $CONFIG_TOML"
		sync_quadlet_units
		return 0
	fi

	if is_fresh_flash && [ -f "$BOOT_CONFIG_PATH" ]; then
		seed_path="$BOOT_CONFIG_PATH"
	elif usb_path="$(find_usb_config)"; then
		seed_path="$usb_path"
	else
		seed_path=""
	fi

	if [ -n "$seed_path" ]; then
		import_seed_config "$seed_path"
		return $?
	fi

	if ! bootstrap_web_console; then
		return 1
	fi
	sync_quadlet_units
}

should_allow_dev_fallback() {
	[ "${ATOMIXOS_DEV_ENABLE_SSH_WAN:-}" = "1" ]
}

SENTINEL="${ATOMIXOS_FIRST_BOOT_SENTINEL:-/data/.completed_first_boot}"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

BOOT_SLOT="$(current_boot_slot || true)"

used_dev_fallback=false

if ! discover_and_import_provisioning; then
	if should_allow_dev_fallback; then
		log "Provisioning seed not found; using development fallback"
		enable_dev_ssh_on_wan
		write_dev_health_requirements
		used_dev_fallback=true
	else
		log "ERROR: provisioning seed not found"
		exit 1
	fi
	if [ "$used_dev_fallback" != true ] && ! has_valid_provisioning; then
		log "ERROR: imported provisioning is invalid"
		exit 1
	fi
fi

if [ "$used_dev_fallback" != true ] && ! has_valid_provisioning; then
	log "ERROR: resulting provisioning is invalid"
	exit 1
fi

if [ "$RAUC_ENABLED" = "1" ]; then
	if [ -z "$BOOT_SLOT" ]; then
		log "ERROR: could not determine boot slot from /proc/cmdline"
		exit 1
	fi

	ensure_rauc_env

	log "Marking current slot as good via RAUC: $BOOT_SLOT"
	if ! rauc status mark-good "$BOOT_SLOT"; then
		log "ERROR: failed to mark current slot good via RAUC"
		exit 1
	fi
else
	log "RAUC disabled; skipping slot confirmation"
fi

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
