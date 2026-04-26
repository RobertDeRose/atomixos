#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  forensics-initrd-log --event <event>
EOF
}

EVENT=""

while [ $# -gt 0 ]; do
	case "$1" in
	--event)
		EVENT="$2"
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

if [ -z "$EVENT" ]; then
	usage >&2
	exit 1
fi

slot="${ATOMIXOS_FORENSICS_SLOT:-}"
lower_device="${ATOMIXOS_FORENSICS_LOWERDEV:-}"

if [ -z "$slot" ] || [ -z "$lower_device" ]; then
	for arg in $(</proc/cmdline); do
		case "$arg" in
		rauc.slot=boot.*)
			if [ -z "$slot" ]; then
				slot="${arg#rauc.slot=}"
			fi
			;;
		atomixos.lowerdev=*)
			if [ -z "$lower_device" ]; then
				lower_device="${arg#atomixos.lowerdev=}"
			fi
			;;
		esac
	done
fi

if [ -z "$slot" ]; then
	slot="boot.0"
fi

case "$slot" in
boot.0)
	boot_device="${ATOMIXOS_FORENSICS_BOOT0:-}"
	;;
boot.1)
	boot_device="${ATOMIXOS_FORENSICS_BOOT1:-}"
	;;
*)
	boot_device=""
	;;
esac

mount_dir="${ATOMIXOS_FORENSICS_MOUNT:-/run/forensics-initrd}"
mount_override=0
if [ -n "${ATOMIXOS_FORENSICS_MOUNT:-}" ]; then
	mount_override=1
fi

if [ "$mount_override" -eq 0 ] && [ -z "$boot_device" ]; then
	printf 'forensics-initrd-log: missing boot device for slot %s\n' "$slot" >&2
	exit 1
fi

mounted_here=0

cleanup() {
	if [ "$mounted_here" -eq 1 ]; then
		umount "$mount_dir" >/dev/null 2>&1 || true
	fi
}

trap cleanup EXIT INT TERM
mkdir -p "$mount_dir"

if [ "$mount_override" -eq 0 ] && ! findmnt "$mount_dir" >/dev/null 2>&1 && [ -n "$boot_device" ]; then
	if ! mount -t vfat -o uid=0,gid=0,fmask=0133,dmask=0022 "$boot_device" "$mount_dir" >/dev/null 2>&1; then
		printf 'forensics-initrd-log: failed to mount %s at %s\n' "$boot_device" "$mount_dir" >&2
		exit 1
	fi
	mounted_here=1
fi

if [ "$EVENT" = "lowerdev-selected" ] && [ -z "$lower_device" ]; then
	printf 'forensics-initrd-log: missing lower device for %s\n' "$EVENT" >&2
	exit 1
fi

args=(--mount "$mount_dir" --slot "$slot" --stage initrd --event "$EVENT")
if [ -n "$lower_device" ]; then
	args+=(--device "$lower_device")
fi

forensic-log "${args[@]}"
