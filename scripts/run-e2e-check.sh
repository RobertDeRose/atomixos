#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat >&2 <<'EOF'
Usage: run-e2e-check.sh [--interactive] [--keep] <check-name> <description>
EOF
}

interactive=false
keep=false
while (($#)); do
	case "$1" in
	--interactive)
		interactive=true
		shift
		;;
	--keep)
		keep=true
		shift
		;;
	--)
		shift
		break
		;;
	-*)
		echo "ERROR: unknown option: $1" >&2
		usage
		exit 2
		;;
	*) break ;;
	esac
done

if (($# != 2)); then
	usage
	exit 2
fi

check_name=$1
description=$2

case "$check_name" in
rauc-slots | rauc-update | rauc-rollback | rauc-confirm | rauc-power-loss | rauc-watchdog | firewall | network-isolation | ssh-wan-toggle) ;;
*)
	echo "ERROR: unsupported E2E check: $check_name" >&2
	exit 2
	;;
esac

if [[ -z "$description" || "$description" == *$'\n'* || "$description" == *$'\r'* ]]; then
	echo "ERROR: description must be one non-empty line" >&2
	exit 2
fi

if [[ "$keep" == true && "$interactive" != true ]]; then
	echo "ERROR: --keep requires --interactive" >&2
	exit 2
fi

command_prefix=()
if [[ "${usage_lima:-false}" == true ]]; then
	if ! command -v limactl >/dev/null 2>&1; then
		echo "ERROR: limactl not found. Install Lima: https://lima-vm.io/" >&2
		exit 1
	fi
	limactl start "${usage_vm:-default}" 2>/dev/null || true
	command_prefix=(limactl shell "${usage_vm:-default}" --)
fi

architecture=aarch64-linux
if [[ "${usage_lima:-false}" != true && "$(uname -s)" == Darwin ]]; then
	architecture=aarch64-darwin
fi

if [[ "$interactive" == true ]]; then
	echo "Building interactive test driver for: $check_name ($architecture)"
	echo
	"${command_prefix[@]}" nix build \
		".#checks.${architecture}.${check_name}.driverInteractive" \
		-o "result-e2e-${check_name}"

	driver="./result-e2e-${check_name}/bin/nixos-test-driver"
	if [[ ! -x "$driver" ]]; then
		echo "ERROR: Test driver not found at $driver" >&2
		exit 1
	fi

	driver_args=(--interactive)
	if [[ "$keep" == true ]]; then
		driver_args+=(--keep-vm-state)
	fi

	echo
	echo "Starting interactive test driver..."
	echo
	echo "  Available commands in the Python REPL:"
	echo "    gateway.start()                 # boot the VM"
	echo '    gateway.wait_for_unit("multi-user.target")'
	echo '    gateway.succeed("rauc status") # run a command'
	echo "    gateway.shell_interact()        # drop into a root shell"
	echo '    gateway.screenshot("name")     # save a screenshot'
	echo
	echo "  Press Ctrl+D to exit the REPL and shut down the VM."
	echo
	exec "$driver" "${driver_args[@]}"
fi

echo "Running E2E test: $check_name ($architecture)"
echo "  $description"
echo
"${command_prefix[@]}" nix build ".#checks.${architecture}.${check_name}" \
	--no-link --print-build-logs \
	2> >(grep -v 'SQLite database.*is busy' >&2)
echo
echo "PASS: $check_name"
