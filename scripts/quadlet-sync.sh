#!/usr/bin/env bash
set -euo pipefail

log() { echo "[quadlet-sync] $*" >&2; }

invalid_runtime_metadata() {
	log "Invalid runtime metadata: $RUNTIME_METADATA_FILE"
	exit 1
}

validate_runtime_metadata() {
	if ! jq -e '
		type == "object"
		and (.units | type == "array")
		and all(.units[];
			type == "object"
			and (.mode | type == "string")
			and ((.service // "") | type == "string")
		)
	' "$RUNTIME_METADATA_FILE" >/dev/null 2>&1; then
		invalid_runtime_metadata
	fi
	return 0
}

runtime_metadata_query() {
	local filter="$1"
	shift
	validate_runtime_metadata
	if ! jq -r "$@" "$filter" "$RUNTIME_METADATA_FILE"; then
		invalid_runtime_metadata
	fi
}

CONFIG_ROOT="/data/config"
QUADLET_ACTIVE_DIR="/etc/containers/systemd"
APP_RUNTIME_USER="appsvc"
APP_RUNTIME_HOME="/var/lib/appsvc"
ROOTLESS_QUADLET_DIR="$APP_RUNTIME_HOME/.config/containers/systemd"
RUNTIME_METADATA_FILE="$CONFIG_ROOT/quadlet-runtime.json"
MANAGED_QUADLET_MANIFEST=".atomixos-managed-quadlets.json"
CHRONY_WAIT_TIMEOUT_SECONDS="${ATOMIXOS_CHRONY_WAIT_TIMEOUT_SECONDS:-10}"
CHRONY_WAIT_ATTEMPTS="${ATOMIXOS_CHRONY_WAIT_ATTEMPTS:-3}"
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
		path="$path:$PATH"
	fi
	runuser -u "$APP_RUNTIME_USER" -- env \
		HOME="$APP_RUNTIME_HOME" \
		PATH="$path" \
		XDG_RUNTIME_DIR="$runtime_dir" \
		DBUS_SESSION_BUS_ADDRESS="$bus_address" \
		"$@"
}

wait_for_clock_sync() {
	if ! command -v chronyc >/dev/null 2>&1; then
		log "chronyc not available, skipping clock sync wait"
		return 0
	fi

	local tracking
	tracking="$(chronyc tracking 2>/dev/null || true)"
	if printf '%s\n' "$tracking" | grep -q '^Leap status[[:space:]]*:[[:space:]]*Normal$'; then
		log "Clock is already synchronized"
		return 0
	fi

	local attempt=1
	while [ "$attempt" -le "$CHRONY_WAIT_ATTEMPTS" ]; do
		log "Waiting for clock synchronization (${attempt}/${CHRONY_WAIT_ATTEMPTS})"
		if timeout "$CHRONY_WAIT_TIMEOUT_SECONDS" chronyc waitsync 1 1; then
			log "Clock synchronized"
			return 0
		fi
		attempt=$((attempt + 1))
	done

	log "WARNING: clock did not synchronize after bounded wait; continuing"
}

has_rootless_units() {
	[ "$(runtime_metadata_query 'any(.units[]; .mode == "rootless")')" = "true" ]
}

prepare_rootless_runtime() {
	local uid
	uid="$(appsvc_uid)"
	install -d -o "$APP_RUNTIME_USER" -g "$APP_RUNTIME_USER" -m 0750 "$APP_RUNTIME_HOME"
	install -d -o "$APP_RUNTIME_USER" -g "$APP_RUNTIME_USER" -m 0700 "$APP_RUNTIME_HOME/.config"
	install -d -o "$APP_RUNTIME_USER" -g "$APP_RUNTIME_USER" -m 0700 "$APP_RUNTIME_HOME/.config/containers"
	install -d -o "$APP_RUNTIME_USER" -g "$APP_RUNTIME_USER" -m 0700 "$ROOTLESS_QUADLET_DIR"
	loginctl enable-linger "$APP_RUNTIME_USER"
	systemctl start "user@$uid.service"
	run_as_appsvc systemctl --user daemon-reload
}

list_units_by_mode() {
	local mode="$1"
	# shellcheck disable=SC2016
	local filter='.units[] | select(.mode == $mode and (.service // "") != "") | .service'
	runtime_metadata_query "$filter" --arg mode "$mode"
}

list_build_units_by_mode() {
	local mode="$1"
	# shellcheck disable=SC2016
	local filter='.units[] | select(.mode == $mode and (.service // "") != "" and (.filename // "" | endswith(".build"))) | .service'
	runtime_metadata_query "$filter" --arg mode "$mode"
}

list_non_build_units_by_mode() {
	local mode="$1"
	# shellcheck disable=SC2016
	local filter='.units[] | select(.mode == $mode and (.service // "") != "" and ((.filename // "" | endswith(".build")) | not)) | .service'
	runtime_metadata_query "$filter" --arg mode "$mode"
}

list_active_quadlet_services() {
	local target_dir="$1"
	local manifest="$target_dir/$MANAGED_QUADLET_MANIFEST"
	local filename
	[ -f "$manifest" ] || return 0
	while IFS= read -r filename; do
		case "$filename" in
		*.container) printf '%s.service\n' "${filename%.container}" ;;
		*.volume) printf '%s-volume.service\n' "${filename%.volume}" ;;
		*.network) printf '%s-network.service\n' "${filename%.network}" ;;
		*.build) printf '%s-build.service\n' "${filename%.build}" ;;
		esac
	done < <(jq -r '.[]' "$manifest")
}

list_stale_services_by_mode() {
	local mode="$1"
	local target_dir="$2"
	comm -23 \
		<(list_active_quadlet_services "$target_dir" | sort -u) \
		<(list_units_by_mode "$mode" | sort -u)
}

if [ ! -f "$CONFIG_ROOT/config.toml" ]; then
	log "No provisioned config present, skipping"
	exit 0
fi

wait_for_clock_sync

mkdir -p "$QUADLET_ACTIVE_DIR"
if [ ! -f "$RUNTIME_METADATA_FILE" ]; then
	log "Missing runtime metadata, skipping"
	exit 1
fi

mapfile -t stale_rootful_services < <(list_stale_services_by_mode rootful "$QUADLET_ACTIVE_DIR")
stale_rootless_services=()
if [ -d "$ROOTLESS_QUADLET_DIR" ]; then
	mapfile -t stale_rootless_services < <(list_stale_services_by_mode rootless "$ROOTLESS_QUADLET_DIR")
fi

if has_rootless_units || [ "${#stale_rootless_services[@]}" -gt 0 ]; then
	prepare_rootless_runtime
	first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$ROOTLESS_QUADLET_DIR"
	run_as_appsvc systemctl --user daemon-reload
else
	first-boot-provision sync-quadlet "$CONFIG_ROOT" "$QUADLET_ACTIVE_DIR" "$ROOTLESS_QUADLET_DIR"
fi

systemctl daemon-reload

for service_name in "${stale_rootful_services[@]}"; do
	[ -n "$service_name" ] || continue
	log "Stopping stale $service_name"
	if ! systemctl stop "$service_name"; then
		log "WARNING: failed to stop stale $service_name"
	fi
done

if has_rootless_units || [ "${#stale_rootless_services[@]}" -gt 0 ]; then
	for service_name in "${stale_rootless_services[@]}"; do
		[ -n "$service_name" ] || continue
		log "Stopping stale rootless $service_name"
		if ! run_as_appsvc systemctl --user stop "$service_name"; then
			log "WARNING: failed to stop stale rootless $service_name"
		fi
	done
fi

failed_units=()

while IFS= read -r service_name; do
	[ -n "$service_name" ] || continue
	log "Running build $service_name"
	if ! systemctl restart "$service_name"; then
		log "Failed to run build $service_name"
		failed_units+=("$service_name")
	fi
done < <(list_build_units_by_mode rootful)

while IFS= read -r service_name; do
	[ -n "$service_name" ] || continue
	log "Restarting $service_name"
	if ! systemctl restart "$service_name"; then
		log "Failed to restart $service_name"
		failed_units+=("$service_name")
	fi
done < <(list_non_build_units_by_mode rootful)

if has_rootless_units; then
	while IFS= read -r service_name; do
		[ -n "$service_name" ] || continue
		log "Building rootless $service_name"
		if ! run_as_appsvc systemctl --user restart "$service_name"; then
			log "Failed to build rootless $service_name"
			failed_units+=("$service_name")
		fi
	done < <(list_build_units_by_mode rootless)

	while IFS= read -r service_name; do
		[ -n "$service_name" ] || continue
		log "Restarting rootless $service_name"
		if ! run_as_appsvc systemctl --user restart "$service_name"; then
			log "Failed to restart rootless $service_name"
			failed_units+=("$service_name")
		fi
	done < <(list_non_build_units_by_mode rootless)
fi

if [ "${#failed_units[@]}" -gt 0 ]; then
	log "WARNING: units failed to start after sync: ${failed_units[*]}"
	log "WARNING: continuing so the provisioned system remains debuggable"
fi
