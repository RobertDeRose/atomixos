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
BOOTSTRAP_HOST="${ATOMIXOS_BOOTSTRAP_HOST:-172.20.30.1}"
INITRD_MARKER="${ATOMIXOS_INITRD_MARKER:-/etc/atomixos/fresh-flash}"
BOOT_CONFIG_PATH="${ATOMIXOS_BOOT_CONFIG_PATH:-/boot/config.toml}"
APP_RUNTIME_QUADLET_DIR="${ATOMIXOS_ROOTLESS_QUADLET_DIR:-/var/lib/appsvc/.config/containers/systemd}"
RAUC_ENABLED="${ATOMIXOS_RAUC_ENABLE:-1}"
LAN_SETTINGS_FILE="$CONFIG_ROOT/lan-settings.json"
APPLY_USERS_SCRIPT="${ATOMIXOS_APPLY_USERS_SCRIPT:-./scripts/apply-users.py}"

read_bootstrap_host() {
	if [ ! -f "$LAN_SETTINGS_FILE" ]; then
		printf '%s\n' "$BOOTSTRAP_HOST"
		return 0
	fi

	jq -er '
		.gateway_ip
		| select(
			type == "string"
			and test("^(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})(\\.(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}$")
		)
	' "$LAN_SETTINGS_FILE" 2>/dev/null || printf '%s\n' "$BOOTSTRAP_HOST"
}

has_required_units() {
	local health_file="$CONFIG_ROOT/health-required.json"

	[ -f "$health_file" ] || return 1
	jq -e 'type == "array" and length > 0' "$health_file" >/dev/null 2>&1
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
	log "Waiting for provisioning via bootstrap web console"
	while true; do
		if has_valid_provisioning; then
			return 0
		fi
		sleep 1
	done
}

sync_quadlet_units() {
	if command -v systemctl >/dev/null 2>&1; then
		if ! systemctl restart quadlet-sync.service; then
			if has_required_units; then
				log "ERROR: quadlet-sync.service failed with required provisioned units"
				return 1
			fi
			log "WARNING: quadlet-sync.service failed with no required provisioned units"
		fi
		if systemctl list-unit-files lan-gateway-apply.service >/dev/null 2>&1; then
			if ! systemctl restart lan-gateway-apply.service; then
				log "ERROR: lan-gateway-apply.service failed"
				return 1
			fi
		fi
		if systemctl list-unit-files provisioned-firewall-inbound.service >/dev/null 2>&1; then
			if ! systemctl restart provisioned-firewall-inbound.service; then
				log "ERROR: provisioned-firewall-inbound.service failed"
				return 1
			fi
		fi
	else
		mkdir -p "$QUADLET_ACTIVE_DIR"
		if ! first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$APP_RUNTIME_QUADLET_DIR"; then
			if has_required_units; then
				log "ERROR: quadlet sync failed with required provisioned units"
				return 1
			fi
			log "WARNING: quadlet sync failed with no required provisioned units"
		fi
	fi
}

apply_managed_users() {
	if command -v systemctl >/dev/null 2>&1; then
		systemctl start atomixos-apply-users.service
		return 0
	fi

	log "WARNING: systemctl unavailable; applying managed users directly"
	ATOMIXOS_USERS_JSON="$CONFIG_ROOT/users.json" \
		ATOMIXOS_MANAGED_STATE="$CONFIG_ROOT/managed-users.json" \
		ATOMIXOS_SSH_KEYS_DIR="$CONFIG_ROOT/ssh-authorized-keys" \
		python3 "$APPLY_USERS_SCRIPT"
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
	apply_managed_users
	sync_quadlet_units
}

has_valid_provisioning() {
	[ -f "$CONFIG_TOML" ] && first-boot-provision validate "$CONFIG_TOML" >/dev/null 2>&1
}

discover_and_import_provisioning() {
	local seed_path usb_path
	if has_valid_provisioning; then
		log "Using existing provisioned config from $CONFIG_TOML"
		apply_managed_users
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
	apply_managed_users
	sync_quadlet_units
}

SENTINEL="${ATOMIXOS_FIRST_BOOT_SENTINEL:-/data/.completed_first_boot}"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

BOOT_SLOT="$(current_boot_slot || true)"

if ! discover_and_import_provisioning; then
	log "ERROR: provisioning seed not found"
	exit 1
fi

if ! has_valid_provisioning; then
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
