#!/usr/bin/env bash
set -euo pipefail

log() { echo "[quadlet-sync] $*"; }

CONFIG_ROOT="/data/config"
QUADLET_CONFIG_DIR="$CONFIG_ROOT/quadlet"
QUADLET_ACTIVE_DIR="/etc/containers/systemd"

if [ ! -f "$CONFIG_ROOT/config.toml" ]; then
	log "No provisioned config present, skipping"
	exit 0
fi

mkdir -p "$QUADLET_ACTIVE_DIR"
first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR"
systemctl daemon-reload

for unit_file in "$QUADLET_CONFIG_DIR"/*.container "$QUADLET_CONFIG_DIR"/*.pod; do
	[ -e "$unit_file" ] || continue
	service_name="$(basename "$unit_file")"
	service_name="${service_name%.*}.service"
	log "Starting $service_name"
	systemctl start "$service_name"
done
