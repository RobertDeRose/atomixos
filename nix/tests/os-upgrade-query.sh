#!/usr/bin/env bash
set -euo pipefail

: "${OS_UPGRADE_SCRIPT:?OS_UPGRADE_SCRIPT must name scripts/os-upgrade.sh}"

work="${TMPDIR:-/tmp}/os-upgrade-query"
fake_bin="$work/fake-bin"
rm -rf "$work"
mkdir -p "$fake_bin"
export STUB_LOG="$work/calls.log"
export ATOMIXOS_OS_UPGRADE_CONFIG="$work/os-upgrade.json"
export ATOMIXOS_RAUC_BUNDLE_DIR="$work/bundles"
printf '{"server_url":"https://updates.example.test"}\n' >"$ATOMIXOS_OS_UPGRADE_CONFIG"

stub() {
	printf '#!%s\nset -euo pipefail\n' "$BASH" >"$fake_bin/$1"
	cat >>"$fake_bin/$1"
	chmod +x "$fake_bin/$1"
}

# Like RAUC, report slot_status (the installed bundle version) only with --detailed.
stub rauc <<'STUB'
printf 'rauc %s\n' "$*" >>"$STUB_LOG"
if [ "$1" = status ]; then
	case " $* " in
	*" --detailed "*) printf '%s\n' "$RAUC_STATUS" ;;
	*) printf '%s\n' "$RAUC_STATUS" | jq -c 'del(.slots[][].slot_status)' ;;
	esac
fi
STUB

# The first curl call is the update query (prints $SERVER_RESPONSE); any call
# with -o is a bundle download.
stub curl <<'STUB'
printf 'curl %s\n' "$*" >>"$STUB_LOG"
output=
previous=
for argument in "$@"; do
	[ "$previous" = -o ] && output=$argument
	previous=$argument
done
if [ -n "$output" ]; then
	printf 'bundle' >"$output"
else
	printf '%s\n' "$SERVER_RESPONSE"
fi
STUB

stub systemctl <<'STUB'
printf 'systemctl %s\n' "$*" >>"$STUB_LOG"
STUB

# RAUC's JSON shape: .booted is the rauc.slot= value and slots are keyed by name.
status_json() {
	jq -cn --arg compatible "$1" '{
		compatible: $compatible,
		booted: "boot.0",
		slots: [
			{"boot.0": {bootname: "A", boot_status: "good", slot_status: {bundle: {version: "1.0"}}}},
			{"boot.1": {bootname: "B", boot_status: "good"}},
			{"rootfs.0": {bootname: null, boot_status: null}}
		]
	} | if $compatible == "" then del(.compatible) else . end'
}

run_case() {
	local name=$1 expected_rc=$2
	: >"$STUB_LOG"
	set +e
	PATH="$fake_bin:$PATH" bash "$OS_UPGRADE_SCRIPT" >"$work/$name.out" 2>&1
	local rc=$?
	set -e
	if [ "$rc" -ne "$expected_rc" ]; then
		echo "FAIL $name: exit $rc, expected $expected_rc" >&2
		cat "$work/$name.out" "$STUB_LOG" >&2
		exit 1
	fi
}

expect_log() {
	if ! grep -qF -- "$2" "$STUB_LOG"; then
		echo "FAIL $1: expected call containing: $2" >&2
		cat "$STUB_LOG" >&2
		exit 1
	fi
}

reject_log() {
	if grep -qF -- "$2" "$STUB_LOG"; then
		echo "FAIL $1: unexpected call containing: $2" >&2
		cat "$STUB_LOG" >&2
		exit 1
	fi
}

bundle='https://updates.example.test/b.raucb'

# The query names the board, and a matching bundle installs.
export RAUC_STATUS SERVER_RESPONSE
RAUC_STATUS=$(status_json radxa-cm3-io)
SERVER_RESPONSE=$(jq -cn --arg url "$bundle" '{version: "2.0", bundle_url: $url, compatible: "radxa-cm3-io"}')
run_case matching 0
expect_log matching 'X-Compatible: radxa-cm3-io'
expect_log matching "-o $ATOMIXOS_RAUC_BUNDLE_DIR/update-2.0.raucb.tmp $bundle"
expect_log matching 'rauc install'
expect_log matching 'systemctl reboot'
grep -F 'Preparing install from unknown to boot.1' "$work/matching.out"

# The installed bundle version comes from rauc status --detailed, so an
# unchanged server version is not reinstalled.
SERVER_RESPONSE=$(jq -cn --arg url "$bundle" '{version: "1.0", bundle_url: $url, compatible: "radxa-cm3-io"}')
run_case current 0
grep -F 'Already on latest version (1.0)' "$work/current.out"
reject_log current ' -o '
reject_log current 'rauc install'

# Another board's bundle is skipped before download.
SERVER_RESPONSE=$(jq -cn --arg url "$bundle" '{version: "2.0", bundle_url: $url, compatible: "rock64"}')
run_case mismatch 0
expect_log mismatch 'X-Compatible: radxa-cm3-io'
reject_log mismatch ' -o '
reject_log mismatch 'rauc install'
reject_log mismatch 'systemctl reboot'

# A server that omits compatible keeps working; RAUC remains the final check.
RAUC_STATUS=$(status_json rock64)
SERVER_RESPONSE=$(jq -cn --arg url "$bundle" '{version: "2.0", bundle_url: $url}')
run_case legacy-server 0
expect_log legacy-server 'X-Compatible: rock64'
expect_log legacy-server 'rauc install'

# Without a compatible from rauc status, the server is never queried.
RAUC_STATUS=$(status_json '')
run_case no-compatible 1
reject_log no-compatible 'curl'

echo "os-upgrade query checks passed"
