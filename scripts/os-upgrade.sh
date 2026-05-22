#!/usr/bin/env bash
# OS upgrade polling service — checks for new RAUC bundles and installs them.
# Designed to be run periodically by a systemd timer.
#
# Environment:
#   ATOMIXOS_OS_UPGRADE_CONFIG — provisioned JSON config with server_url
#
# Dependencies (must be on PATH): rauc, curl, jq, systemctl
set -euo pipefail

OS_UPGRADE_CONFIG="${ATOMIXOS_OS_UPGRADE_CONFIG:-/data/config/os-upgrade.json}"
UPDATE_URL=""
DEVICE_ID=$(cat /sys/class/net/eth0/address 2>/dev/null | tr -d ':' || echo "unknown")
BUNDLE_DIR="${ATOMIXOS_RAUC_BUNDLE_DIR:-/data/rauc/bundles}"

log() { echo "[os-upgrade] $*"; }

if [ -f "$OS_UPGRADE_CONFIG" ]; then
	UPDATE_URL="$(jq -r '.server_url // empty' "$OS_UPGRADE_CONFIG" 2>/dev/null || true)"
fi

if [ -z "$UPDATE_URL" ]; then
	log "No update server configured; skipping"
	exit 0
fi

RAUC_STATUS_JSON="$(rauc status --output-format=json 2>/dev/null || true)"
BOOT_STATUS=$(printf '%s\n' "$RAUC_STATUS_JSON" | jq -r '
  .booted as $booted
  | .slots[]
  | to_entries[]
  | select(.key == $booted)
  | .value.boot_status // empty
' 2>/dev/null || true)
if [ "$BOOT_STATUS" != "good" ]; then
	log "Current slot is not marked good (boot_status=${BOOT_STATUS:-unknown}); skipping update"
	exit 0
fi

CURRENT_VERSION=$(printf '%s\n' "$RAUC_STATUS_JSON" | jq -r '
  .booted as $booted
  | .slots[]
  | to_entries[]
  | select(.key == $booted)
  | .value.slot_status.bundle.version // empty
' 2>/dev/null || true)
if [ -z "$CURRENT_VERSION" ] && [ -r /etc/os-release ]; then
	CURRENT_VERSION="$(. /etc/os-release && printf '%s\n' "${VERSION_ID:-}")"
fi

if [ -z "$CURRENT_VERSION" ]; then
	log "ERROR: cannot determine current version from rauc status"
	exit 1
fi

if [[ ! "$CURRENT_VERSION" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
	log "ERROR: invalid current version from rauc status"
	exit 1
fi

case "$UPDATE_URL" in
https://*) ;;
*)
	log "ERROR: update server URL must use HTTPS: $UPDATE_URL"
	exit 1
	;;
esac

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
RESPONSE=$(curl -sfL -m 30 --proto '=https' --proto-redir '=https' \
	-H "X-Device-ID: $DEVICE_ID" \
	-H "X-Current-Version: $CURRENT_VERSION" \
	"$UPDATE_URL/api/v1/updates/latest" 2>/dev/null) || {
	log "Failed to reach update server at $UPDATE_URL"
	exit 0 # Not an error — we'll try again next interval
}

if ! printf '%s\n' "$RESPONSE" | jq -e 'type == "object"' >/dev/null 2>&1; then
	log "Invalid update server response from $UPDATE_URL"
	exit 0
fi

LATEST_VERSION=$(echo "$RESPONSE" | jq -r '.version // empty')
BUNDLE_URL=$(echo "$RESPONSE" | jq -r '.bundle_url // empty')

if [ -z "$LATEST_VERSION" ] || [ -z "$BUNDLE_URL" ]; then
	log "No update available or invalid response"
	exit 0
fi

if [[ ! "$LATEST_VERSION" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
	log "Invalid update version from server: $LATEST_VERSION"
	exit 1
fi

# Validate BUNDLE_URL is HTTPS
case "$BUNDLE_URL" in
https://*) ;;
*)
	log "Rejecting non-HTTPS bundle URL: $BUNDLE_URL"
	exit 1
	;;
esac

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
log "Preparing install from ${BOOT_SLOT:-unknown} to $TARGET_BOOT_SLOT"

# Download the bundle
mkdir -p "$BUNDLE_DIR"
BUNDLE_PATH="$BUNDLE_DIR/update-$LATEST_VERSION.raucb"

log "Downloading bundle to $BUNDLE_PATH..."
if ! curl -f -m 600 --proto '=https' --proto-redir '=https' -o "$BUNDLE_PATH.tmp" "$BUNDLE_URL"; then
	log "Download failed, cleaning up"
	rm -f "$BUNDLE_PATH.tmp"
	exit 0 # Will retry next interval
fi

mv "$BUNDLE_PATH.tmp" "$BUNDLE_PATH"
log "Download complete"

# Install the bundle
log "Installing bundle..."
if rauc install "$BUNDLE_PATH"; then
	log "Bundle installed successfully, cleaning up"
	rm -f "$BUNDLE_PATH"
	log "Rebooting into new slot..."
	systemctl reboot
else
	log "Bundle installation failed"
	rm -f "$BUNDLE_PATH"
	exit 1
fi
