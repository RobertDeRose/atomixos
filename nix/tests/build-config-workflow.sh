#!/usr/bin/env bash
set -euo pipefail

: "${TEST_REPO:?TEST_REPO must name the isolated test repository}"
TEST_REPO=$(cd -- "$TEST_REPO" && pwd -P)
export TEST_REPO

fake_bin="$TEST_REPO/fake-bin"
log="$TEST_REPO/nix.log"
mkdir -p "$fake_bin" "$TEST_REPO/scripts"
: >"$log"

printf '#!%s\n' "$BASH" >"$fake_bin/nix"
cat >>"$fake_bin/nix" <<'EOF'
set -euo pipefail
printf 'dev=%s args=%s\n' "${ATOMIXOS_BUILD_DEV_CONFIG:-<unset>}" "$*" >>"${NIX_LOG:?}"

if [[ "${NIX_FAIL_MATCH:-}" && "$*" == *"$NIX_FAIL_MATCH"* ]]; then
  exit 23
fi

if [[ "${1:-}" == eval ]]; then
  printf '%s\n' 0123456789abcdef
  exit 0
fi

output=
previous=
for argument in "$@"; do
  if [[ "$previous" == -o ]]; then
    output=$argument
    break
  fi
  previous=$argument
done

if [[ "$output" ]]; then
  target="$TEST_REPO/fake-output-$(basename "$output" .new)"
  mkdir -p "$target"
  case "$output" in
    *image*) touch "$target/atomixos-26.05.img" ;;
    *rauc-bundle*) touch "$target/rock64.raucb" ;;
  esac
  rm -f "$output"
  ln -s "$target" "$output"
fi
EOF
printf '#!%s\n' "$BASH" >"$fake_bin/mise"
cat >>"$fake_bin/mise" <<'EOF'
exit 0
EOF
printf '#!%s\n' "$BASH" >"$fake_bin/limactl"
cat >>"$fake_bin/limactl" <<'EOF'
set -euo pipefail
while (($#)) && [[ "$1" != -- ]]; do
  shift
done
shift
exec "$@"
EOF
chmod +x "$fake_bin/nix" "$fake_bin/mise" "$fake_bin/limactl"

export NIX_LOG="$log"
export PATH="$fake_bin:$PATH"

# Caller-selected transport is removed when the repository has no local overlay.
: >"$log"
ATOMIXOS_BUILD_DEV_CONFIG=/tmp/untrusted \
	"$TEST_REPO/scripts/nix-with-build-config.sh" build .#image --no-link \
	>"$TEST_REPO/default.out" 2>"$TEST_REPO/default.err"
test ! -s "$TEST_REPO/default.err"
grep -Fx 'dev=<unset> args=build .#image --no-link' "$log"

# A repository-root overlay is selected automatically, warned about first, and evaluated impurely.
printf '%s\n' '[watchdog]' 'enable_hardware = true' >"$TEST_REPO/build.dev.toml"
: >"$log"
"$TEST_REPO/scripts/nix-with-build-config.sh" flake check \
	>"$TEST_REPO/override.out" 2>"$TEST_REPO/override.err"
grep -Fx 'WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.' \
	"$TEST_REPO/override.err"
grep -Fx "dev=$TEST_REPO/build.dev.toml args=flake check --impure" "$log"
rm "$TEST_REPO/build.dev.toml"

# Full-build validation happens before retained links change; a later failure preserves every prior root.
mkdir -p "$TEST_REPO/.gcroots/images" "$TEST_REPO/.gcroots/bundles" "$TEST_REPO/old"
for root in kernel toplevel uboot uboot-env-tools; do
	mkdir -p "$TEST_REPO/old/$root"
	ln -s "$TEST_REPO/old/$root" "$TEST_REPO/.gcroots/$root"
done
mkdir -p "$TEST_REPO/old/image" "$TEST_REPO/old/bundle"
touch "$TEST_REPO/old/image/atomixos-old.img" "$TEST_REPO/old/bundle/rock64-old.raucb"
ln -s "$TEST_REPO/old/image" "$TEST_REPO/.gcroots/images/image.1"
ln -s "$TEST_REPO/old/bundle" "$TEST_REPO/.gcroots/bundles/rauc-bundle.1"

: >"$log"
if (cd "$TEST_REPO" && NIX_FAIL_MATCH=toplevel ./scripts/build.sh); then
	echo "full build unexpectedly succeeded" >&2
	exit 1
fi
head -n 1 "$log" | grep -F 'args=eval .#lib.effectiveBuildConfiguration.policySHA256 --raw'
for root in kernel toplevel uboot uboot-env-tools; do
	test "$(readlink "$TEST_REPO/.gcroots/$root")" = "$TEST_REPO/old/$root"
done
test "$(readlink "$TEST_REPO/.gcroots/images/image.1")" = "$TEST_REPO/old/image"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle.1")" = "$TEST_REPO/old/bundle"

# A successful full build atomically replaces retained roots and leaves no temporary links.
: >"$log"
(cd "$TEST_REPO" && ./scripts/build.sh)
for root in kernel toplevel uboot uboot-env-tools; do
	test "$(readlink "$TEST_REPO/.gcroots/$root")" != "$TEST_REPO/old/$root"
	test ! -e "$TEST_REPO/.gcroots/$root.new"
done
test "$(readlink "$TEST_REPO/.gcroots/images/image.1")" != "$TEST_REPO/old/image"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle.1")" != "$TEST_REPO/old/bundle"
test ! -e "$TEST_REPO/.gcroots/images/image.1.new"
test ! -e "$TEST_REPO/.gcroots/bundles/rauc-bundle.1.new"

# Local-override exports cannot discard durable -dev filename identity.
printf '%s\n' '[watchdog]' 'enable_hardware = true' >"$TEST_REPO/build.dev.toml"
: >"$log"
if (cd "$TEST_REPO" && usage_output="$TEST_REPO/atomixos.img" ./scripts/build.sh) \
	>"$TEST_REPO/export.out" 2>"$TEST_REPO/export.err"; then
	echo "local override export without -dev unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'ERROR: local override output filename must include -dev: atomixos.img' \
	"$TEST_REPO/export.err"
test ! -e "$TEST_REPO/atomixos.img"
test ! -s "$log"
(cd "$TEST_REPO" && usage_output="$TEST_REPO/atomixos-dev.img" ./scripts/build.sh) \
	>"$TEST_REPO/export-dev.out" 2>"$TEST_REPO/export-dev.err"
test -f "$TEST_REPO/atomixos-dev.img"

# Lima executes the same fixed-path wrapper inside the mounted repository.
: >"$log"
(cd "$TEST_REPO" && usage_lima=true usage_vm=test-vm ./scripts/build.sh) \
	>"$TEST_REPO/lima.out" 2>"$TEST_REPO/lima.err"
grep -F 'WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.' \
	"$TEST_REPO/lima.err"
grep -F "dev=$TEST_REPO/build.dev.toml args=eval .#lib.effectiveBuildConfiguration.policySHA256 --raw --impure" \
	"$log"
rm "$TEST_REPO/build.dev.toml"

# The supported task matrix routes only configuration-bearing project commands.
grep -F 'depends = ["nix:check"]' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh flake check --all-systems --no-build' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh flake check' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#squashfs' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#rauc-bundle' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#boot-script' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#nixosConfigurations.bundle-test-vm' \
	"$TEST_REPO/mise.toml"
grep -F 'run = "./scripts/build.sh"' "$TEST_REPO/mise.toml"
if grep -R -F 'nix-with-build-config.sh' "$TEST_REPO/.mise/tasks/e2e" "$TEST_REPO/.mise/tasks/serial"; then
	echo "excluded e2e or serial task unexpectedly uses local build policy" >&2
	exit 1
fi
for excluded_header in '[tasks._lima]' '[tasks.gc]'; do
	if awk -v header="$excluded_header" '
    $0 == header { inside = 1; next }
    inside && /^\[tasks\./ { exit }
    inside { print }
  ' "$TEST_REPO/mise.toml" | grep -F 'nix-with-build-config.sh'; then
		echo "excluded $excluded_header task unexpectedly uses local build policy" >&2
		exit 1
	fi
done
