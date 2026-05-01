#!/usr/bin/env bash
set -euo pipefail

RAUC_BOOTLOADER="${ATOMIXOS_RAUC_BOOTLOADER:-unknown}"
STATE_DIR="${ATOMIXOS_RAUC_STATE_DIR:-/var/lib/rauc}"

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

handle_custom_backend() {
	local primary count count_file new_count failed_slot target_slot

	mkdir -p "$STATE_DIR"
	primary=$(cat "$STATE_DIR/primary" 2>/dev/null || echo "A")
	count_file="$STATE_DIR/boot-count.$primary"

	if [ ! -f "$count_file" ]; then
		exit 0
	fi

	count=$(tr -d '\n' <"$count_file")
	case "$count" in
	"" | *[!0-9-]*)
		exit 0
		;;
	esac

	new_count=$((count - 1))
	echo "[watchdog-boot-count] boot-count decremented: $primary:$new_count"

	if [ "$new_count" -le 0 ]; then
		case "$primary" in
		A)
			failed_slot="boot.0"
			target_slot="boot.1"
			echo "B" >"$STATE_DIR/primary"
			;;
		B)
			failed_slot="boot.1"
			target_slot="boot.0"
			echo "A" >"$STATE_DIR/primary"
			;;
		*)
			exit 0
			;;
		esac

		echo "[watchdog-boot-count] rollback triggered: failed=$failed_slot target=$target_slot reason=boot-count-exhausted"
		echo "bad" >"$STATE_DIR/state.$primary"
		rm -f "$count_file"
		echo "[watchdog-boot-count] rollback complete: failed=$failed_slot target=$target_slot result=ok"
	else
		printf '%s\n' "$new_count" >"$count_file"
	fi
}

handle_uboot_backend() {
	local boot_slot boot_var boot_letter attempts_left

	if ! command -v fw_printenv >/dev/null 2>&1; then
		exit 0
	fi

	boot_slot="$(current_boot_slot || true)"
	case "$boot_slot" in
	boot.0)
		boot_letter="A"
		boot_var="BOOT_A_LEFT"
		;;
	boot.1)
		boot_letter="B"
		boot_var="BOOT_B_LEFT"
		;;
	*)
		exit 0
		;;
	esac

	attempts_left=$(fw_printenv -n "$boot_var" 2>/dev/null || true)
	case "$attempts_left" in
	"" | *[!0-9-]*)
		exit 0
		;;
	esac

	# U-Boot decrements BOOT_*_LEFT before Linux starts; record the observed post-boot value.
	echo "[watchdog-boot-count] boot-count observed: slot=$boot_slot detail=$boot_letter:$attempts_left"
}

case "$RAUC_BOOTLOADER" in
custom)
	handle_custom_backend
	;;
uboot)
	handle_uboot_backend
	;;
*)
	exit 0
	;;
esac
