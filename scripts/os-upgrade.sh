#!/usr/bin/env bash
# OS upgrade polling service — checks for new RAUC bundles and installs them.
# Designed to be run periodically by a systemd timer.
#
# Environment:
#   OS_UPGRADE_URL — base URL of the update server (default: http://localhost/updates)
#
# Dependencies (must be on PATH): rauc, curl, jq, systemctl
set -euo pipefail

UPDATE_URL="${OS_UPGRADE_URL:-http://localhost/updates}"
DEVICE_ID=$(cat /sys/class/net/eth0/address 2>/dev/null | tr -d ':' || echo "unknown")
BUNDLE_DIR="/data/config/bundles"
FORENSICS_STATE_DIR="${ATOMIXOS_FORENSICS_RAUC_STATE_DIR:-/data/rauc/forensics}"
CURRENT_VERSION=$(rauc status --output-format=json 2>/dev/null | jq -r '
  .booted as $booted
  | .slots[]
  | to_entries[]
  | select(.key == $booted)
  | .value.slot_status.bundle.version // "unknown"
' || echo "unknown")

log() { echo "[os-upgrade] $*"; }

forensic() {
	if command -v forensic-log >/dev/null 2>&1; then
		forensic-log "$@" || true
	fi
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

slot_letter_to_boot_slot() {
	case "$1" in
	A) printf 'boot.0\n' ;;
	B) printf 'boot.1\n' ;;
	*) return 1 ;;
	esac
}

target_boot_slot_from_status() {
	local current_letter target_letter
	current_letter="$(rauc status --output-format=json 2>/dev/null | jq -r '.booted // empty' 2>/dev/null || true)"
	if [ -z "$current_letter" ]; then
		return 1
	fi
	case "$current_letter" in
	A) target_letter="B" ;;
	B) target_letter="A" ;;
	*) return 1 ;;
	esac
	slot_letter_to_boot_slot "$target_letter"
}

log "Checking for updates (current version: $CURRENT_VERSION, device: $DEVICE_ID)..."

# Query update server for latest version
RESPONSE=$(curl -sf -m 30 \
	-H "X-Device-ID: $DEVICE_ID" \
	-H "X-Current-Version: $CURRENT_VERSION" \
	"$UPDATE_URL/api/v1/updates/latest" 2>/dev/null) || {
	log "Failed to reach update server at $UPDATE_URL"
	exit 0 # Not an error — we'll try again next interval
}

LATEST_VERSION=$(echo "$RESPONSE" | jq -r '.version // empty')
BUNDLE_URL=$(echo "$RESPONSE" | jq -r '.bundle_url // empty')

if [ -z "$LATEST_VERSION" ] || [ -z "$BUNDLE_URL" ]; then
	log "No update available or invalid response"
	exit 0
fi

if [ "$LATEST_VERSION" = "$CURRENT_VERSION" ]; then
	log "Already on latest version ($CURRENT_VERSION)"
	exit 0
fi

log "New version available: $LATEST_VERSION (current: $CURRENT_VERSION)"
BOOT_SLOT="$(current_boot_slot || true)"
TARGET_BOOT_SLOT="$(target_boot_slot_from_status || true)"
if [ -z "$TARGET_BOOT_SLOT" ]; then
	TARGET_BOOT_SLOT="unknown"
fi
forensic --stage rauc --event install-start --slot "$BOOT_SLOT" --target-slot "$TARGET_BOOT_SLOT" --version "$LATEST_VERSION"

# Download the bundle
mkdir -p "$BUNDLE_DIR"
BUNDLE_PATH="$BUNDLE_DIR/update-$LATEST_VERSION.raucb"

log "Downloading bundle to $BUNDLE_PATH..."
if ! curl -f -m 600 -o "$BUNDLE_PATH.tmp" "$BUNDLE_URL"; then
	log "Download failed, cleaning up"
	forensic --stage rauc --event install-failed --version "$LATEST_VERSION" --reason download-failed
	rm -f "$BUNDLE_PATH.tmp"
	exit 0 # Will retry next interval
fi

mv "$BUNDLE_PATH.tmp" "$BUNDLE_PATH"
log "Download complete"

# Install the bundle
log "Installing bundle..."
if rauc install "$BUNDLE_PATH"; then
	log "Bundle installed successfully, cleaning up"
	mkdir -p "$FORENSICS_STATE_DIR"
	if [ -n "$BOOT_SLOT" ]; then
		printf '%s\n' "$BOOT_SLOT" >"$FORENSICS_STATE_DIR/pending-source-slot"
	fi
	if [ "$TARGET_BOOT_SLOT" != "unknown" ]; then
		printf '%s\n' "$TARGET_BOOT_SLOT" >"$FORENSICS_STATE_DIR/pending-target-slot"
	else
		rm -f "$FORENSICS_STATE_DIR/pending-target-slot"
	fi
	printf '%s\n' "$LATEST_VERSION" >"$FORENSICS_STATE_DIR/pending-target-version"
	rm -f "$FORENSICS_STATE_DIR/pending-target-booted"
	forensic --stage rauc --event install-complete --slot "$TARGET_BOOT_SLOT" --target-slot "$TARGET_BOOT_SLOT" --version "$LATEST_VERSION" --result ok
	rm -f "$BUNDLE_PATH"
	log "Rebooting into new slot..."
	forensic --stage shutdown --event reboot-requested --result ok --detail os-upgrade
	systemctl reboot
else
	log "Bundle installation failed"
	forensic --stage rauc --event install-failed --version "$LATEST_VERSION" --reason install-failed
	rm -f "$BUNDLE_PATH"
	exit 1
fi
