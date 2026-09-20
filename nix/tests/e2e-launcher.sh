#!/usr/bin/env bash
set -euo pipefail

: "${TEST_REPO:?TEST_REPO must name the isolated test repository}"
fake_bin="$TEST_REPO/fake-bin"
log="$TEST_REPO/e2e.log"
mkdir -p "$fake_bin"
: >"$log"

printf '#!%s\n' "$BASH" >"$fake_bin/uname"
cat >>"$fake_bin/uname" <<'EOF'
printf '%s\n' "${TEST_UNAME:-Linux}"
EOF

printf '#!%s\n' "$BASH" >"$fake_bin/nix"
cat >>"$fake_bin/nix" <<'EOF'
set -euo pipefail
printf 'nix %s\n' "$*" >>"${E2E_LOG:?}"
printf '%s\n' 'SQLite database cache is busy' >&2
printf '%s\n' 'visible build diagnostic' >&2

output=
previous=
for argument in "$@"; do
	if [[ "$previous" == -o ]]; then
		output=$argument
		break
	fi
	previous=$argument
done

if [[ -n "$output" ]]; then
	mkdir -p "$output/bin"
	printf '#!%s\n' "$BASH" >"$output/bin/nixos-test-driver"
	cat >>"$output/bin/nixos-test-driver" <<'DRIVER'
printf 'driver %s\n' "$*" >>"${E2E_LOG:?}"
DRIVER
	chmod +x "$output/bin/nixos-test-driver"
fi
EOF

printf '#!%s\n' "$BASH" >"$fake_bin/limactl"
cat >>"$fake_bin/limactl" <<'EOF'
set -euo pipefail
printf 'limactl %s\n' "$*" >>"${E2E_LOG:?}"
if [[ "${1:-}" == start ]]; then
	exit 0
fi
while (($#)) && [[ "$1" != -- ]]; do
	shift
done
shift
exec "$@"
EOF

chmod +x "$fake_bin/uname" "$fake_bin/nix" "$fake_bin/limactl"
export E2E_LOG="$log"
export PATH="$fake_bin:$PATH"
cd "$TEST_REPO"

if ./scripts/run-e2e-check.sh >missing.out 2>missing.err; then
	echo "missing arguments unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'Usage: run-e2e-check.sh' missing.err

if ./scripts/run-e2e-check.sh arbitrary 'unsafe check' >invalid.out 2>invalid.err; then
	echo "unsupported check unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'ERROR: unsupported E2E check: arbitrary' invalid.err

if ./scripts/run-e2e-check.sh firewall $'two\nlines' >invalid.out 2>invalid.err; then
	echo "multiline description unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'ERROR: description must be one non-empty line' invalid.err

: >"$log"
TEST_UNAME=Darwin ./scripts/run-e2e-check.sh firewall 'Firewall contract' \
	>darwin.out 2>darwin.err
grep -F 'Running E2E test: firewall (aarch64-darwin)' darwin.out
grep -F '  Firewall contract' darwin.out
grep -F 'PASS: firewall' darwin.out
grep -F 'nix build .#checks.aarch64-darwin.firewall --no-link --print-build-logs' "$log"
grep -F 'visible build diagnostic' darwin.err
if grep -F 'SQLite database' darwin.err; then
	echo "expected SQLite contention diagnostic to be filtered" >&2
	exit 1
fi

: >"$log"
TEST_UNAME=Darwin usage_lima=true usage_vm=test-vm \
	./scripts/run-e2e-check.sh rauc-slots 'Slot contract' >lima.out 2>lima.err
grep -F 'Running E2E test: rauc-slots (aarch64-linux)' lima.out
grep -F 'limactl start test-vm' "$log"
grep -F 'limactl shell test-vm -- nix build .#checks.aarch64-linux.rauc-slots --no-link --print-build-logs' "$log"
grep -F 'nix build .#checks.aarch64-linux.rauc-slots --no-link --print-build-logs' "$log"

: >"$log"
TEST_UNAME=Linux ./scripts/run-e2e-check.sh --interactive --keep rauc-update \
	'Interactive contract' >interactive.out 2>interactive.err
grep -F 'Building interactive test driver for: rauc-update (aarch64-linux)' interactive.out
grep -F 'nix build .#checks.aarch64-linux.rauc-update.driverInteractive -o result-e2e-rauc-update' "$log"
grep -F 'driver --interactive --keep-vm-state' "$log"

if ./scripts/run-e2e-check.sh --keep firewall 'Invalid keep' >invalid.out 2>invalid.err; then
	echo "non-interactive --keep unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'ERROR: --keep requires --interactive' invalid.err
