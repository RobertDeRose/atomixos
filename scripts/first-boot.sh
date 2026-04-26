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

write_dev_admin_password_hash
enable_dev_ssh_on_wan

# ── Write sentinel ──
log "Writing first-boot sentinel: $SENTINEL"
date -Iseconds >"$SENTINEL"

log "First boot initialization complete"
forensic --stage firstboot --event complete --slot "$BOOT_SLOT" --result ok
