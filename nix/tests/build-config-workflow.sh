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
  target="$TEST_REPO/fake-output-$(basename "$output" .new)${FAKE_GENERATION:+-$FAKE_GENERATION}"
  mkdir -p "$target"
  board=rock64
  [[ "$output" == *-cm3* ]] && board=cm3
  case "$output" in
    *image*) touch "$target/atomixos-$board-26.05.img" ;;
    *rauc-bundle*) touch "$target/$board.raucb" ;;
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
# Start with pre-board ROCK64 roots to verify successful one-time migration.
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
	test ! -L "$TEST_REPO/.gcroots/$root-rock64"
done
test "$(readlink "$TEST_REPO/.gcroots/images/image.1")" = "$TEST_REPO/old/image"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle.1")" = "$TEST_REPO/old/bundle"

# A successful default ROCK64 build migrates old links and rotates the old image to .2.
: >"$log"
(cd "$TEST_REPO" && ./scripts/build.sh)
for root in kernel toplevel uboot uboot-env-tools; do
	test "$(readlink "$TEST_REPO/.gcroots/$root-rock64")" != "$TEST_REPO/old/$root"
	test ! -L "$TEST_REPO/.gcroots/$root"
	test ! -e "$TEST_REPO/.gcroots/$root-rock64.new"
done
test -f "$TEST_REPO/.gcroots/images/image-rock64.1/atomixos-rock64-26.05.img"
test "$(readlink "$TEST_REPO/.gcroots/images/image-rock64.2")" = "$TEST_REPO/old/image"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-rock64.2")" = "$TEST_REPO/old/bundle"
test ! -L "$TEST_REPO/.gcroots/images/image.1"
test ! -L "$TEST_REPO/.gcroots/bundles/rauc-bundle.1"
test ! -e "$TEST_REPO/.gcroots/images/image-rock64.1.new"
test ! -e "$TEST_REPO/.gcroots/bundles/rauc-bundle-rock64.1.new"
grep -F 'args=build .#image-rock64 -o .gcroots/images/image-rock64.1.new' "$log"
grep -F 'args=build .#rauc-bundle-rock64 -o .gcroots/bundles/rauc-bundle-rock64.1.new' "$log"

# Invalid boards are rejected before any evaluation or retained-root mutation.
rock64_image_target=$(readlink "$TEST_REPO/.gcroots/images/image-rock64.1")
rock64_bundle_target=$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-rock64.1")
: >"$log"
if (cd "$TEST_REPO" && usage_board=unknown ./scripts/build.sh) \
	>"$TEST_REPO/invalid-board.out" 2>"$TEST_REPO/invalid-board.err"; then
	echo "unknown board unexpectedly succeeded" >&2
	exit 1
fi
grep -F "ERROR: unsupported board 'unknown'" "$TEST_REPO/invalid-board.err"
test ! -s "$log"

# A failed CM3 build leaves ROCK64 roots intact and does not install CM3 roots.
: >"$log"
if (cd "$TEST_REPO" && usage_board=cm3 NIX_FAIL_MATCH='.#rauc-bundle-cm3' ./scripts/build.sh); then
	echo "failed CM3 build unexpectedly succeeded" >&2
	exit 1
fi
test "$(readlink "$TEST_REPO/.gcroots/images/image-rock64.1")" = "$rock64_image_target"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-rock64.1")" = "$rock64_bundle_target"
test ! -L "$TEST_REPO/.gcroots/images/image-cm3.1"
test ! -e "$TEST_REPO/.gcroots/images/image-cm3.1.new"
test ! -e "$TEST_REPO/.gcroots/bundles/rauc-bundle-cm3.1.new"

# CM3 builds all hardware-specific outputs without replacing the ROCK64 artifacts.
: >"$log"
(cd "$TEST_REPO" && usage_board=cm3 ./scripts/build.sh)
grep -F 'args=build .#nixosConfigurations.cm3.config.system.build.kernel' "$log"
grep -F 'args=build .#uboot-cm3 ' "$log"
grep -F 'args=build .#uboot-env-tools-cm3 ' "$log"
grep -F 'args=build .#image-cm3 -o .gcroots/images/image-cm3.1.new' "$log"
grep -F 'args=build .#rauc-bundle-cm3 -o .gcroots/bundles/rauc-bundle-cm3.1.new' "$log"
test -f "$TEST_REPO/.gcroots/images/image-cm3.1/atomixos-cm3-26.05.img"
test -f "$TEST_REPO/.gcroots/bundles/rauc-bundle-cm3.1/cm3.raucb"
test "$(readlink "$TEST_REPO/.gcroots/images/image-rock64.1")" = "$rock64_image_target"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-rock64.1")" = "$rock64_bundle_target"

# A later CM3 revision rotates only its own two image and bundle generations.
cm3_image_target=$(readlink "$TEST_REPO/.gcroots/images/image-cm3.1")
cm3_bundle_target=$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-cm3.1")
(cd "$TEST_REPO" && usage_board=cm3 FAKE_GENERATION=next ./scripts/build.sh)
test "$(readlink "$TEST_REPO/.gcroots/images/image-cm3.2")" = "$cm3_image_target"
test "$(readlink "$TEST_REPO/.gcroots/bundles/rauc-bundle-cm3.2")" = "$cm3_bundle_target"
test "$(readlink "$TEST_REPO/.gcroots/images/image-cm3.1")" != "$cm3_image_target"
test "$(readlink "$TEST_REPO/.gcroots/images/image-rock64.1")" = "$rock64_image_target"

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
(cd "$TEST_REPO" && usage_board=cm3 usage_lima=true usage_vm=test-vm ./scripts/build.sh) \
	>"$TEST_REPO/lima.out" 2>"$TEST_REPO/lima.err"
grep -F 'WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.' \
	"$TEST_REPO/lima.err"
grep -F "dev=$TEST_REPO/build.dev.toml args=eval .#lib.effectiveBuildConfiguration.policySHA256 --raw --impure" \
	"$log"
grep -F 'args=build .#image-cm3 -o .gcroots/images/image-cm3.1.new --impure' "$log"
rm "$TEST_REPO/build.dev.toml"

# The supported task matrix routes only configuration-bearing project commands.
grep -F '[tasks.check]' "$TEST_REPO/mise.toml"
grep -F 'run = "hk check -a"' "$TEST_REPO/mise.toml"
if grep -F '[tasks."nix:check"]' "$TEST_REPO/mise.toml"; then
	echo "unexpected duplicate nix:check task in mise configuration" >&2
	exit 1
fi
grep -F './scripts/nix-with-build-config.sh build .#squashfs' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#rauc-bundle' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#boot-script' "$TEST_REPO/mise.toml"
grep -F './scripts/nix-with-build-config.sh build .#nixosConfigurations.bundle-test-vm' \
	"$TEST_REPO/mise.toml"
grep -F 'run = "./scripts/build.sh"' "$TEST_REPO/mise.toml"
grep -F 'flag "--board <board>" help="Target board" default="rock64"' "$TEST_REPO/mise.toml"
grep -F 'choices "rock64" "cm3"' "$TEST_REPO/mise.toml"
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
