#!/usr/bin/env bash
set -euo pipefail

log() { echo "[quadlet-sync] $*"; }

CONFIG_ROOT="/data/config"
QUADLET_ACTIVE_DIR="/etc/containers/systemd"
APP_RUNTIME_USER="appsvc"
APP_RUNTIME_HOME="/var/lib/appsvc"
ROOTLESS_QUADLET_DIR="$APP_RUNTIME_HOME/.config/containers/systemd"
RUNTIME_METADATA_FILE="$CONFIG_ROOT/quadlet-runtime.json"
appsvc_uid() {
	id -u "$APP_RUNTIME_USER"
}

run_as_appsvc() {
	local uid
	uid="$(appsvc_uid)"
	local runtime_dir="/run/user/$uid"
	local bus_address="unix:path=$runtime_dir/bus"
	local path="/run/wrappers/bin:/run/current-system/sw/bin"
	if [ "${ATOMIXOS_ALLOW_UNSAFE_PATH:-0}" = "1" ] && [ -n "${PATH:-}" ]; then
		path="$PATH:$path"
	fi
	runuser -u "$APP_RUNTIME_USER" -- env \
		HOME="$APP_RUNTIME_HOME" \
		PATH="$path" \
		XDG_RUNTIME_DIR="$runtime_dir" \
		DBUS_SESSION_BUS_ADDRESS="$bus_address" \
		"$@"
}

has_rootless_units() {
	jq -e 'any(.units[]?; .mode == "rootless")' "$RUNTIME_METADATA_FILE" >/dev/null
}

prepare_rootless_runtime() {
	local uid
	uid="$(appsvc_uid)"
	mkdir -p "$ROOTLESS_QUADLET_DIR"
	chown -R "$APP_RUNTIME_USER:$APP_RUNTIME_USER" "$APP_RUNTIME_HOME"
	loginctl enable-linger "$APP_RUNTIME_USER"
	systemctl start "user@$uid.service"
	run_as_appsvc systemctl --user daemon-reload
}

list_units_by_mode() {
	local mode="$1"
	jq -r --arg mode "$mode" '.units[]? | select(.mode == $mode and (.service // "") != "") | .service' "$RUNTIME_METADATA_FILE"
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
	run_as_appsvc systemctl --user daemon-reload
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
		if ! run_as_appsvc systemctl --user start "$service_name"; then
			log "Failed to start rootless $service_name"
			failed_units+=("$service_name")
		fi
	done < <(list_units_by_mode rootless)
fi

if [ "${#failed_units[@]}" -gt 0 ]; then
	log "WARNING: units failed to start after sync: ${failed_units[*]}"
	log "WARNING: continuing so the provisioned system remains debuggable"
fi
