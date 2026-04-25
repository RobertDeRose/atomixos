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
CURRENT_VERSION=$(rauc status --output-format=json 2>/dev/null | jq -r '.slots[] | select(.state.booted == "booted") | .slot_status.bundle.version // "unknown"' || echo "unknown")

log() { echo "[os-upgrade] $*"; }

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

# Download the bundle
mkdir -p "$BUNDLE_DIR"
BUNDLE_PATH="$BUNDLE_DIR/update-$LATEST_VERSION.raucb"

log "Downloading bundle to $BUNDLE_PATH..."
if ! curl -f -m 600 -o "$BUNDLE_PATH.tmp" "$BUNDLE_URL"; then
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
