#!/usr/bin/env bash
# First-boot initialization — runs once on initial device boot.
#
# On first boot there is no health manifest and container images have not
# been pulled yet, so the normal os-verification health check cannot pass.
# This script confirms the current boot slot via RAUC so U-Boot's RAUC
# bootmeth knows this slot is good and stops decrementing the try counter.
set -euo pipefail

log() { echo "[first-boot] $*"; }
FORENSICS_STATE_DIR="${ATOMIXOS_FORENSICS_RAUC_STATE_DIR:-/data/rauc/forensics}"
CONFIG_ROOT="/data/config"
CONFIG_TOML="$CONFIG_ROOT/config.toml"
QUADLET_ACTIVE_DIR="/etc/containers/systemd"
BOOTSTRAP_PORT="${ATOMIXOS_BOOTSTRAP_PORT:-8080}"
BOOTSTRAP_HOST="${ATOMIXOS_BOOTSTRAP_HOST:-172.20.30.1}"
INITRD_MARKER="/etc/atomixos/fresh-flash"
BOOT_CONFIG_PATH="/boot/config.toml"

forensic() {
	if command -v forensic-log >/dev/null 2>&1; then
		forensic-log "$@" || true
	fi
}

write_dev_admin_password_hash() {
	local hash_file="/data/config/admin-password-hash"
	local hash_value="${ATOMIXOS_DEV_ADMIN_PASSWORD_HASH:-}"

	if [ -z "$hash_value" ] || [ -f "$hash_file" ]; then
		return 0
	fi

	mkdir -p "$(dirname "$hash_file")"
	log "Writing development admin password hash"
	printf '%s\n' "$hash_value" >"$hash_file"
	chmod 600 "$hash_file"
}

enable_dev_ssh_on_wan() {
	local flag_file="/data/config/ssh-wan-enabled"

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
	local device mount_dir
	for device in /dev/disk/by-label/* /dev/disk/by-partlabel/*; do
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
	temp_config="$(mktemp /run/atomixos-bootstrap-config.XXXXXX.toml)"
	log "Starting bootstrap web console on $BOOTSTRAP_HOST:$BOOTSTRAP_PORT"
	forensic --stage firstboot --event bootstrap-console --result start
	first-boot-provision serve "$CONFIG_ROOT" "$temp_config" --host "$BOOTSTRAP_HOST" --port "$BOOTSTRAP_PORT" &
	local server_pid=$!
	while kill -0 "$server_pid" >/dev/null 2>&1; do
		if [ -f "$CONFIG_TOML" ]; then
			kill "$server_pid" >/dev/null 2>&1 || true
			wait "$server_pid" 2>/dev/null || true
			rm -f "$temp_config"
			forensic --stage firstboot --event bootstrap-console --result ok
			return 0
		fi
		sleep 1
	done
	rm -f "$temp_config"
	forensic --stage firstboot --event failed --reason bootstrap-console-exited
	return 1
}

sync_quadlet_units() {
	if command -v systemctl >/dev/null 2>&1; then
		systemctl restart quadlet-sync.service
	else
		mkdir -p "$QUADLET_ACTIVE_DIR"
		first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR"
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

	bootstrap_web_console
	sync_quadlet_units
}

should_allow_dev_fallback() {
	[ -n "${ATOMIXOS_DEV_ADMIN_PASSWORD_HASH:-}" ] || [ "${ATOMIXOS_DEV_ENABLE_SSH_WAN:-}" = "1" ]
}

SENTINEL="/data/.completed_first_boot"

# Guard (belt-and-suspenders alongside systemd ConditionPathExists)
if [ -f "$SENTINEL" ]; then
	log "Sentinel exists, skipping (not first boot)"
	forensic --stage firstboot --event failed --reason sentinel-exists
	exit 0
fi

# ── Confirm the boot slot via RAUC ──
BOOT_SLOT="$(current_boot_slot || true)"
if [ -z "$BOOT_SLOT" ]; then
	log "ERROR: could not determine boot slot from /proc/cmdline"
	forensic --stage firstboot --event failed --reason missing-boot-slot
	exit 1
fi

forensic --stage firstboot --event start --slot "$BOOT_SLOT"

mkdir -p "$FORENSICS_STATE_DIR"

used_dev_fallback=false

if ! discover_and_import_provisioning; then
	if should_allow_dev_fallback; then
		log "Provisioning seed not found; using development fallback"
		write_dev_admin_password_hash
		enable_dev_ssh_on_wan
		write_dev_health_requirements
		used_dev_fallback=true
	else
		forensic --stage firstboot --event failed --slot "$BOOT_SLOT" --reason provisioning-missing
		exit 1
	fi
	if [ "$used_dev_fallback" != true ] && ! has_valid_provisioning; then
		forensic --stage firstboot --event failed --slot "$BOOT_SLOT" --reason invalid-provisioning
		exit 1
	fi
fi

if [ "$used_dev_fallback" != true ] && ! has_valid_provisioning; then
	forensic --stage firstboot --event failed --slot "$BOOT_SLOT" --reason invalid-provisioning
	exit 1
fi

ensure_rauc_env

log "Marking current slot as good via RAUC: $BOOT_SLOT"
if ! rauc status mark-good "$BOOT_SLOT"; then
	forensic --stage rauc --event mark-good-failed --slot "$BOOT_SLOT" --reason first-boot
	exit 1
fi
forensic --stage rauc --event mark-good-complete --slot "$BOOT_SLOT" --result ok
rm -f \
	"$FORENSICS_STATE_DIR/pending-source-slot" \
	"$FORENSICS_STATE_DIR/pending-target-slot" \
	"$FORENSICS_STATE_DIR/pending-target-version" \
	"$FORENSICS_STATE_DIR/pending-target-booted"

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
forensic --stage firstboot --event complete --slot "$BOOT_SLOT" --result ok
