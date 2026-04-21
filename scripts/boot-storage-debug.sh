#!/usr/bin/env bash
# Dump boot-storage state to stdout/journal for debugging early boot issues.
set -euo pipefail

section() {
	printf '\n===== %s =====\n' "$1"
}

capture() {
	local title="$1"
	shift
	section "$title"
	if ! "$@"; then
		printf '[command failed: %s]\n' "$*"
	fi
}

dump_region() {
	local title="$1"
	local src="$2"
	local skip_bytes="$3"
	local count_bytes="$4"

	section "$title"
	if [ ! -e "$src" ]; then
		printf '[missing device: %s]\n' "$src"
		return 0
	fi

	dd if="$src" bs=1 skip="$skip_bytes" count="$count_bytes" status=none | hexdump -C || true
}

hash_region() {
	local title="$1"
	local src="$2"
	local skip_bytes="$3"
	local count_bytes="$4"

	section "$title"
	if [ ! -e "$src" ]; then
		printf '[missing device: %s]\n' "$src"
		return 0
	fi

	dd if="$src" bs=1 skip="$skip_bytes" count="$count_bytes" status=none | sha256sum || true
}

capture "date" date -u
capture "uname" uname -a
capture "cmdline" cat /proc/cmdline
capture "mtd" cat /proc/mtd
capture "lsblk" lsblk -o NAME,SIZE,TYPE,LABEL,MOUNTPOINT
capture "mounts" findmnt -R /
capture "fw_env.config" cat /etc/fw_env.config
capture "fw_printenv" fw_printenv
capture "rauc status" rauc status
capture "systemctl status rauc" systemctl status rauc --no-pager
capture "systemctl status first-boot" systemctl status first-boot --no-pager
capture "systemctl status create-persist" systemctl status create-persist --no-pager
capture "systemctl status os-verification" systemctl status os-verification --no-pager
capture "journalctl -b -u rauc" journalctl -b -u rauc --no-pager
capture "journalctl -b -u first-boot" journalctl -b -u first-boot --no-pager
capture "journalctl -b -u create-persist" journalctl -b -u create-persist --no-pager
capture "journalctl -b -u os-verification" journalctl -b -u os-verification --no-pager
capture "journalctl -b -k watchdog" journalctl -b -k --grep watchdog --no-pager
capture "sfdisk -d /dev/mmcblk1" sfdisk -d /dev/mmcblk1

dump_region "SPI env @ 0x140000 (0x4000 bytes)" /dev/mtd0 $((0x140000)) $((0x4000))
dump_region "eMMC idbloader @ 0x8000 (0x400 bytes)" /dev/mmcblk1 $((0x8000)) $((0x400))
dump_region "eMMC u-boot.itb @ 0x800000 (0x400 bytes)" /dev/mmcblk1 $((0x800000)) $((0x400))
dump_region "eMMC GPT head (0x10000 bytes)" /dev/mmcblk1 0 $((0x10000))

hash_region "SPI env sha256" /dev/mtd0 $((0x140000)) $((0x4000))
hash_region "eMMC idbloader sha256" /dev/mmcblk1 $((0x8000)) $((0x40000))
hash_region "eMMC u-boot.itb sha256" /dev/mmcblk1 $((0x800000)) $((0x200000))
