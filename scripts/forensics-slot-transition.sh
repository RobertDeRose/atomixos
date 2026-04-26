#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${ATOMIXOS_FORENSICS_RAUC_STATE_DIR:-/data/rauc/forensics}"
SOURCE_FILE="$STATE_DIR/pending-source-slot"
TARGET_FILE="$STATE_DIR/pending-target-slot"
VERSION_FILE="$STATE_DIR/pending-target-version"
BOOTED_FILE="$STATE_DIR/pending-target-booted"

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

read_optional() {
	local path="$1"
	if [ -f "$path" ]; then
		tr -d '\n' <"$path"
	fi
}

SOURCE_SLOT="$(read_optional "$SOURCE_FILE")"
TARGET_SLOT="$(read_optional "$TARGET_FILE")"
TARGET_VERSION="$(read_optional "$VERSION_FILE")"
CURRENT_SLOT="${ATOMIXOS_FORENSICS_SLOT:-$(current_boot_slot || true)}"

if [ -z "$SOURCE_SLOT" ] || [ -z "$TARGET_SLOT" ] || [ -z "$CURRENT_SLOT" ]; then
	exit 0
fi

version_args=()
if [ -n "$TARGET_VERSION" ]; then
	version_args=(--version "$TARGET_VERSION")
fi

if [ "$CURRENT_SLOT" = "$TARGET_SLOT" ] && [ ! -f "$BOOTED_FILE" ]; then
	forensic-log \
		--stage rauc \
		--event slot-switch \
		--slot "$CURRENT_SLOT" \
		--target-slot "$TARGET_SLOT" \
		--result ok \
		"${version_args[@]}"
	: >"$BOOTED_FILE"
	exit 0
fi

if [ "$CURRENT_SLOT" = "$SOURCE_SLOT" ] && [ -f "$BOOTED_FILE" ]; then
	forensic-log \
		--stage rollback \
		--event detected \
		--slot "$TARGET_SLOT" \
		--target-slot "$SOURCE_SLOT" \
		--reason slot-fallback \
		"${version_args[@]}"
	forensic-log \
		--stage rollback \
		--event slot-fallback \
		--slot "$TARGET_SLOT" \
		--target-slot "$SOURCE_SLOT" \
		--result ok \
		"${version_args[@]}"
	rm -f "$SOURCE_FILE" "$TARGET_FILE" "$VERSION_FILE" "$BOOTED_FILE"
fi
