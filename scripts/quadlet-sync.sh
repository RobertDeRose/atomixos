#!/usr/bin/env bash
set -euo pipefail

log() { echo "[quadlet-sync] $*"; }

CONFIG_ROOT="/data/config"
QUADLET_ACTIVE_DIR="/etc/containers/systemd"
APP_RUNTIME_USER="appsvc"
APP_RUNTIME_HOME="/var/lib/appsvc"
ROOTLESS_QUADLET_DIR="$APP_RUNTIME_HOME/.config/containers/systemd"
RUNTIME_METADATA_FILE="$CONFIG_ROOT/quadlet-runtime.json"
APP_RUNTIME_SHELL="/run/current-system/sw/bin/sh"

appsvc_uid() {
	id -u "$APP_RUNTIME_USER"
}

run_as_appsvc() {
	local uid
	uid="$(appsvc_uid)"
	local runtime_dir="/run/user/$uid"
	local bus_address="unix:path=$runtime_dir/bus"
	local path="$PATH:/run/wrappers/bin:/run/current-system/sw/bin"
	runuser -u "$APP_RUNTIME_USER" -- "$APP_RUNTIME_SHELL" -c "HOME=\"$APP_RUNTIME_HOME\" PATH=\"$path\" XDG_RUNTIME_DIR=\"$runtime_dir\" DBUS_SESSION_BUS_ADDRESS=\"$bus_address\" $*"
}

has_rootless_units() {
	python3 - <<'PY'
import json
from pathlib import Path

path = Path("/data/config/quadlet-runtime.json")
data = json.loads(path.read_text())
for unit in data.get("units", []):
    if unit.get("mode") == "rootless":
        raise SystemExit(0)
raise SystemExit(1)
PY
}

prepare_rootless_runtime() {
	local uid
	uid="$(appsvc_uid)"
	mkdir -p "$ROOTLESS_QUADLET_DIR"
	chown -R "$APP_RUNTIME_USER:$APP_RUNTIME_USER" "$APP_RUNTIME_HOME"
	loginctl enable-linger "$APP_RUNTIME_USER"
	systemctl start "user@$uid.service"
	run_as_appsvc "systemctl --user daemon-reload"
}

list_units_by_mode() {
	local mode="$1"
	python3 - "$mode" <<'PY'
import json
import sys
from pathlib import Path

mode = sys.argv[1]
path = Path("/data/config/quadlet-runtime.json")
data = json.loads(path.read_text())
for unit in data.get("units", []):
    if unit.get("mode") == mode and unit.get("service"):
        print(unit["service"])
PY
}

if [ ! -f "$CONFIG_ROOT/config.toml" ]; then
	log "No provisioned config present, skipping"
	exit 0
fi

mkdir -p "$QUADLET_ACTIVE_DIR"
if [ ! -f "$RUNTIME_METADATA_FILE" ]; then
	log "Missing runtime metadata, skipping"
	exit 1
fi

if has_rootless_units; then
	prepare_rootless_runtime
	first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$ROOTLESS_QUADLET_DIR"
	run_as_appsvc "systemctl --user daemon-reload"
else
	first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$ROOTLESS_QUADLET_DIR"
fi

systemctl daemon-reload

failed_units=()

while IFS= read -r service_name; do
	[ -n "$service_name" ] || continue
	log "Starting $service_name"
	if ! systemctl start "$service_name"; then
		log "Failed to start $service_name"
		failed_units+=("$service_name")
	fi
done < <(list_units_by_mode rootful)

if has_rootless_units; then
	while IFS= read -r service_name; do
		[ -n "$service_name" ] || continue
		log "Starting rootless $service_name"
		if ! run_as_appsvc "systemctl --user start '$service_name'"; then
			log "Failed to start rootless $service_name"
			failed_units+=("$service_name")
		fi
	done < <(list_units_by_mode rootless)
fi

if [ "${#failed_units[@]}" -gt 0 ]; then
	log "WARNING: units failed to start after sync: ${failed_units[*]}"
	log "WARNING: continuing so the provisioned system remains debuggable"
fi
