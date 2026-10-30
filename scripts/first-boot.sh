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
PROMOTION_MARKER="$CONFIG_ROOT.atomixos-promotion-pending"
QUADLET_ACTIVE_DIR="${ATOMIXOS_QUADLET_ACTIVE_DIR:-/etc/containers/systemd}"
LAN_DEFAULTS_FILE="${ATOMIXOS_LAN_DEFAULTS_FILE:-/etc/atomixos/lan-defaults.json}"
INITRD_MARKER="${ATOMIXOS_INITRD_MARKER:-/etc/atomixos/fresh-flash}"
BOOT_CONFIG_PATH="${ATOMIXOS_BOOT_CONFIG_PATH:-/boot/config.toml}"
APP_RUNTIME_QUADLET_DIR="${ATOMIXOS_ROOTLESS_QUADLET_DIR:-/var/lib/appsvc/.config/containers/systemd}"
RAUC_ENABLED="${ATOMIXOS_RAUC_ENABLE:-1}"
BOOTSTRAP_TRANSPORT="${ATOMIXOS_BOOTSTRAP_TRANSPORT:-network}"
LAN_SETTINGS_FILE="$CONFIG_ROOT/lan-settings.json"
APPLY_USERS_SCRIPT="${ATOMIXOS_APPLY_USERS_SCRIPT:-./scripts/apply-users.py}"

read_bootstrap_host() {
	local default_host
	if [ -n "${ATOMIXOS_BOOTSTRAP_HOST:-}" ]; then
		default_host="$ATOMIXOS_BOOTSTRAP_HOST"
	else
		default_host="$(jq -er '.gateway_ip | select(type == "string" and length > 0)' "$LAN_DEFAULTS_FILE")"
	fi
	if [ ! -f "$LAN_SETTINGS_FILE" ]; then
		printf '%s\n' "$default_host"
		return 0
	fi

	jq -er '
		.gateway_ip
		| select(
			type == "string"
			and test("^(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})(\\.(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}$")
		)
	' "$LAN_SETTINGS_FILE" 2>/dev/null || printf '%s\n' "$default_host"
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

	log "Seeding missing persistent U-Boot environment for RAUC"
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
	# Colon-separated list; avoids word-splitting issues with spaces in paths.
	local IFS=':'
	for search_dir in ${ATOMIXOS_USB_SEARCH_DIRS:-/dev/disk/by-label:/dev/disk/by-partlabel}; do
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

# /boot is boot slot A, which RAUC overwrites while slot B runs, so it is never
# mounted at runtime. Mount it read-only from its fstab entry only to read the
# fresh-flash seed. Where /boot is already mounted or has no fstab entry, read
# the path as it is.
BOOT_SEED_MOUNTED=0

# Returns 0 with a seed, 1 without one, and 2 when the configured /boot cannot
# be mounted. A fresh flash is seen only once, so a seed hidden by a failed
# mount must stop discovery instead of falling through to another source.
open_boot_seed() {
	local boot_dir="${BOOT_CONFIG_PATH%/*}"
	local attempt
	if ! mountpoint -q "$boot_dir" && findmnt --fstab -n "$boot_dir" >/dev/null 2>&1; then
		for attempt in 1 2 3; do
			if mount -o ro "$boot_dir"; then
				BOOT_SEED_MOUNTED=1
				break
			fi
			[ "$attempt" -lt 3 ] && sleep 1
		done
		if [ "$BOOT_SEED_MOUNTED" != 1 ]; then
			log "ERROR: could not mount $boot_dir to read the fresh-flash seed"
			return 2
		fi
	fi
	[ -f "$BOOT_CONFIG_PATH" ]
}

# Keeps BOOT_SEED_MOUNTED set when the unmount fails, so the exit handler tries
# again.
close_boot_seed() {
	if [ "$BOOT_SEED_MOUNTED" = 1 ]; then
		if umount "${BOOT_CONFIG_PATH%/*}"; then
			BOOT_SEED_MOUNTED=0
		else
			log "WARNING: could not unmount ${BOOT_CONFIG_PATH%/*}"
		fi
	fi
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
	"$BOOT_CONFIG_PATH")
		close_boot_seed
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
		if systemctl cat lan-gateway-apply.service >/dev/null 2>&1; then
			if ! systemctl restart lan-gateway-apply.service; then
				log "ERROR: lan-gateway-apply.service failed"
				return 1
			fi
		fi
		if systemctl cat provisioned-firewall-inbound.service >/dev/null 2>&1; then
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

check_required_health() {
	if ! has_required_units; then
		return 0
	fi
	if ! first-boot-provision check-health "$CONFIG_ROOT"; then
		log "ERROR: required provisioned services are not healthy"
		return 1
	fi
}

apply_managed_users() {
	if command -v systemctl >/dev/null 2>&1; then
		systemctl start atomixos-apply-users.service
		return 0
	fi

	log "WARNING: systemctl unavailable; applying managed users directly"
	ATOMIXOS_PROVISION_WORKER_ACTIVE=1 \
		ATOMIXOS_USERS_JSON="$CONFIG_ROOT/users.json" \
		ATOMIXOS_MANAGED_STATE="$CONFIG_ROOT/managed-users.json" \
		ATOMIXOS_SSH_KEYS_DIR="$CONFIG_ROOT/ssh-authorized-keys" \
		"$APPLY_USERS_SCRIPT"
}

import_seed_config() {
	local source_path="$1"
	local status=0
	log "Importing provisioning config from $source_path"
	if ATOMIXOS_PROVISION_WORKER_ACTIVE=1 ATOMIXOS_KEEP_INITIAL_PROMOTION_PENDING=1 first-boot-provision import "$source_path" "$CONFIG_ROOT"; then
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
	check_required_health
	ATOMIXOS_PROVISION_WORKER_ACTIVE=1 first-boot-provision complete-initial "$CONFIG_ROOT"
}

has_valid_provisioning() {
	[ ! -f "$PROMOTION_MARKER" ] && [ -f "$CONFIG_TOML" ] && first-boot-provision validate "$CONFIG_TOML" >/dev/null 2>&1
}

discover_and_import_provisioning() {
	local seed_path="" usb_path boot_status
	if has_valid_provisioning; then
		log "Using existing provisioned config from $CONFIG_TOML"
		apply_managed_users
		sync_quadlet_units
		check_required_health
		return 0
	fi

	if is_fresh_flash; then
		if open_boot_seed; then
			seed_path="$BOOT_CONFIG_PATH"
		else
			boot_status=$?
			close_boot_seed
			if [ "$boot_status" -eq 2 ]; then
				return 1
			fi
		fi
	fi
	if [ -z "$seed_path" ] && usb_path="$(find_usb_config)"; then
		seed_path="$usb_path"
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
	check_required_health
}

SENTINEL="${ATOMIXOS_FIRST_BOOT_SENTINEL:-/data/.completed_first_boot}"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	exit 0
fi

trap close_boot_seed EXIT

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

if command -v systemctl >/dev/null 2>&1 && [ "$BOOTSTRAP_TRANSPORT" = "network" ]; then
	systemctl restart bootstrap-wan-toggle.service >/dev/null 2>&1 || true
	if command -v systemd-run >/dev/null 2>&1; then
		systemd-run \
			--unit=atomixos-bootstrap-final-rebind \
			--on-active=60s \
			--property=Type=oneshot \
			/bin/sh -c 'systemctl restart atomixos-bootstrap-rebind.service && systemctl stop atomixos-bootstrap.service && systemctl restart atomixos-bootstrap.socket && systemctl start atomixos-bootstrap.service' \
			>/dev/null 2>&1 || true
	else
		systemctl restart atomixos-bootstrap-rebind.service >/dev/null 2>&1 || true
		systemctl stop atomixos-bootstrap.service >/dev/null 2>&1 || true
		systemctl restart atomixos-bootstrap.socket >/dev/null 2>&1 || true
		systemctl start atomixos-bootstrap.service >/dev/null 2>&1 || true
	fi
fi

log "First boot initialization complete"
