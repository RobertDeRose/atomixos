#!/usr/bin/env bash
set -euo pipefail

SEGMENT_COUNT="${ATOMIXOS_FORENSICS_SEGMENT_COUNT:-7}"
SEGMENT_SIZE="${ATOMIXOS_FORENSICS_SEGMENT_SIZE:-$((4 * 1024 * 1024))}"
FORMAT_VERSION="v1"

usage() {
	cat <<'EOF'
Usage:
  forensic-log --stage <stage> --event <event> [options]
  forensic-log read [--slot <boot.0|boot.1>]

Options:
  --stage <stage>
  --event <event>
  --result <value>
  --target-slot <value>
  --reason <value>
  --version <value>
  --device <value>
  --service <value>
	--attempt <value>
	--detail <value>
	--slot <boot.0|boot.1>
	--mount <path>
EOF
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

forensics_mount_for_slot() {
	local slot="$1"
	"/etc/atomixos/current-boot-forensics-mount" "$slot"
}

slot_letter() {
	case "$1" in
	boot.0)
		printf 'A\n'
		;;
	boot.1)
		printf 'B\n'
		;;
	*)
		printf 'A\n'
		;;
	esac
}

sanitize_value() {
	printf '%s' "$1" | tr '\n\r\t ' '____'
}

boot_id_path() {
	printf '%s/.boot-id\n' "$1"
}

ensure_boot_id() {
	local _dir="$1"
	local slot="$2"
	local kernel_boot_id
	kernel_boot_id="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
	if [ -z "$kernel_boot_id" ]; then
		kernel_boot_id="$(date -u +%Y%m%dT%H%M%SZ)"
	fi
	local value
	value="${kernel_boot_id}-$(slot_letter "$slot")"
	printf '%s\n' "$value"
}

meta_path() {
	printf '%s/forensics/meta\n' "$1"
}

segment_path() {
	local dir="$1"
	local index="$2"
	printf '%s/forensics/segment-%s.log\n' "$dir" "$index"
}

ensure_layout() {
	local dir="$1"
	mkdir -p "$dir/forensics"
	local idx
	for idx in $(seq 0 $((SEGMENT_COUNT - 1))); do
		if [ ! -f "$(segment_path "$dir" "$idx")" ]; then
			: >"$(segment_path "$dir" "$idx")"
		fi
	done
	if [ ! -f "$(meta_path "$dir")" ]; then
		cat >"$(meta_path "$dir")" <<EOF
format=$FORMAT_VERSION
active_segment=0
next_seq=1
active_boot_id=
EOF
		sync "$(meta_path "$dir")" 2>/dev/null || true
	fi
}

read_meta() {
	local path="$1"
	ACTIVE_SEGMENT=0
	NEXT_SEQ=1
	ACTIVE_BOOT_ID=""
	while IFS='=' read -r key value; do
		case "$key" in
		active_segment)
			ACTIVE_SEGMENT="$value"
			;;
		next_seq)
			NEXT_SEQ="$value"
			;;
		active_boot_id)
			ACTIVE_BOOT_ID="$value"
			;;
		esac
	done <"$path"
}

write_meta() {
	local path="$1"
	local tmp_path
	tmp_path="$path.tmp.$$"
	cat >"$tmp_path" <<EOF
format=$FORMAT_VERSION
active_segment=$ACTIVE_SEGMENT
next_seq=$NEXT_SEQ
active_boot_id=$ACTIVE_BOOT_ID
EOF
	sync "$tmp_path" 2>/dev/null || true
	mv "$tmp_path" "$path"
	sync "$path" 2>/dev/null || true
}

acquire_lock() {
	LOCK_DIR="$1/.forensics-lock"
	while ! mkdir "$LOCK_DIR" 2>/dev/null; do
		sleep 0.1
	done
	trap 'release_lock' EXIT INT TERM
}

release_lock() {
	if [ -n "${LOCK_DIR:-}" ] && [ -d "$LOCK_DIR" ]; then
		rmdir "$LOCK_DIR"
	fi
	trap - EXIT INT TERM
}

rotate_segment_if_needed() {
	local dir="$1"
	local incoming_size="$2"
	local current
	current="$(segment_path "$dir" "$ACTIVE_SEGMENT")"

	if [ ! -f "$current" ]; then
		: >"$current"
	fi

	local size=0
	size=$(wc -c <"$current" 2>/dev/null || printf '0')
	if [ $((size + incoming_size)) -le "$SEGMENT_SIZE" ]; then
		return 0
	fi

	ACTIVE_SEGMENT=$(((ACTIVE_SEGMENT + 1) % SEGMENT_COUNT))
	: >"$(segment_path "$dir" "$ACTIVE_SEGMENT")"
}

append_record() {
	local dir="$1"
	local record="$2"
	local incoming_size
	incoming_size=$(($(printf '%s\n' "$record" | wc -c)))
	rotate_segment_if_needed "$dir" "$incoming_size"
	local target
	target="$(segment_path "$dir" "$ACTIVE_SEGMENT")"
	printf '%s\n' "$record" >>"$target"
	sync "$target" 2>/dev/null || true
}

emit_complete_lines() {
	local path="$1"
	[ -f "$path" ] || return 0
	perl -ne 'print if /\n\z/' "$path"
}

read_records() {
	local dir="$1"
	local meta="$2"
	read_meta "$meta"
	local start=$(((ACTIVE_SEGMENT + 1) % SEGMENT_COUNT))
	local idx
	for idx in $(seq 0 $((SEGMENT_COUNT - 1))); do
		local segment=$(((start + idx) % SEGMENT_COUNT))
		emit_complete_lines "$(segment_path "$dir" "$segment")"
	done
}

MODE="write"

STAGE=""
EVENT=""
RESULT=""
TARGET_SLOT=""
REASON=""
VERSION=""
DEVICE=""
SERVICE=""
ATTEMPT=""
DETAIL=""
SLOT=""
MOUNT_PATH=""

while [ $# -gt 0 ]; do
	case "$1" in
	read)
		MODE="read"
		shift
		;;
	--stage)
		STAGE="$2"
		shift 2
		;;
	--event)
		EVENT="$2"
		shift 2
		;;
	--result)
		RESULT="$2"
		shift 2
		;;
	--target-slot)
		TARGET_SLOT="$2"
		shift 2
		;;
	--reason)
		REASON="$2"
		shift 2
		;;
	--version)
		VERSION="$2"
		shift 2
		;;
	--device)
		DEVICE="$2"
		shift 2
		;;
	--service)
		SERVICE="$2"
		shift 2
		;;
	--attempt)
		ATTEMPT="$2"
		shift 2
		;;
	--detail)
		DETAIL="$2"
		shift 2
		;;
	--slot)
		SLOT="$2"
		shift 2
		;;
	--mount)
		MOUNT_PATH="$2"
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		printf 'Unknown argument: %s\n' "$1" >&2
		usage >&2
		exit 1
		;;
	esac
done

if [ "$MODE" = "write" ] && { [ -z "$STAGE" ] || [ -z "$EVENT" ]; }; then
	usage >&2
	exit 1
fi

if [ -z "$SLOT" ]; then
	SLOT="$(current_boot_slot || true)"
fi
if [ -z "$SLOT" ]; then
	SLOT="boot.0"
fi

if [ -n "$MOUNT_PATH" ]; then
	FORENSICS_MOUNT="$MOUNT_PATH"
else
	FORENSICS_MOUNT="$(forensics_mount_for_slot "$SLOT")"
fi
mkdir -p "$FORENSICS_MOUNT"
acquire_lock "$FORENSICS_MOUNT"
ensure_layout "$FORENSICS_MOUNT"

META_PATH="$(meta_path "$FORENSICS_MOUNT")"

if [ "$MODE" = "read" ]; then
	read_records "$FORENSICS_MOUNT" "$META_PATH"
	release_lock
	exit 0
fi

read_meta "$META_PATH"

BOOT_ID="$(ensure_boot_id "$FORENSICS_MOUNT" "$SLOT")"
if [ "$ACTIVE_BOOT_ID" != "$BOOT_ID" ]; then
	ACTIVE_BOOT_ID="$BOOT_ID"
	NEXT_SEQ=1
	write_meta "$META_PATH"
fi

RECORD="boot_id=$(sanitize_value "$BOOT_ID") seq=$NEXT_SEQ ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) slot=$(sanitize_value "$SLOT") stage=$(sanitize_value "$STAGE") event=$(sanitize_value "$EVENT")"

if [ -n "$RESULT" ]; then
	RECORD="$RECORD result=$(sanitize_value "$RESULT")"
fi
if [ -n "$TARGET_SLOT" ]; then
	RECORD="$RECORD target_slot=$(sanitize_value "$TARGET_SLOT")"
fi
if [ -n "$REASON" ]; then
	RECORD="$RECORD reason=$(sanitize_value "$REASON")"
fi
if [ -n "$VERSION" ]; then
	RECORD="$RECORD version=$(sanitize_value "$VERSION")"
fi
if [ -n "$DEVICE" ]; then
	RECORD="$RECORD device=$(sanitize_value "$DEVICE")"
fi
if [ -n "$SERVICE" ]; then
	RECORD="$RECORD service=$(sanitize_value "$SERVICE")"
fi
if [ -n "$ATTEMPT" ]; then
	RECORD="$RECORD attempt=$(sanitize_value "$ATTEMPT")"
fi
if [ -n "$DETAIL" ]; then
	RECORD="$RECORD detail=$(sanitize_value "$DETAIL")"
fi

append_record "$FORENSICS_MOUNT" "$RECORD"
NEXT_SEQ=$((NEXT_SEQ + 1))
write_meta "$META_PATH"
release_lock
