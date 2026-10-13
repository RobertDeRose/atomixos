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

# The trailing space lets a pattern match a whole final argument.
if [[ "${NIX_FAIL_MATCH:-}" && "$* " == *"$NIX_FAIL_MATCH"* ]]; then
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
  installable=${2:-}
  if [[ "$installable" == /* ]]; then
    # Building an existing store path only (re)links it as a GC root.
    target=$installable
  else
    name=${installable#.#}
    target="$TEST_REPO/fake-output-${name//\//-}${FAKE_GENERATION:+-$FAKE_GENERATION}"
    mkdir -p "$target"
    case "$name" in
      rock64 | cm3)
        mkdir -p "$target/image" "$target/rauc-bundle" "$target/uboot"
        touch "$target/image/atomixos-$name-26.05.img" "$target/rauc-bundle/$name.raucb"
        ;;
    esac
  fi
  printf '%s\n' "$output" >>"$TEST_REPO/retained.log"
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
	"$TEST_REPO/scripts/nix-with-build-config.sh" build .#rock64.image --no-link \
	>"$TEST_REPO/default.out" 2>"$TEST_REPO/default.err"
test ! -s "$TEST_REPO/default.err"
grep -Fx 'dev=<unset> args=build .#rock64.image --no-link' "$log"

# A repository-root overlay is selected automatically, warned about first, and evaluated impurely.
printf '%s\n' '[watchdog]' 'enable_hardware = true' >"$TEST_REPO/build.dev.toml"
: >"$log"
"$TEST_REPO/scripts/nix-with-build-config.sh" flake check \
	>"$TEST_REPO/override.out" 2>"$TEST_REPO/override.err"
grep -Fx 'WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.' \
	"$TEST_REPO/override.err"
grep -Fx "dev=$TEST_REPO/build.dev.toml args=flake check --impure" "$log"
rm "$TEST_REPO/build.dev.toml"

# Full-build validation happens before retained links change; a failure at either build step publishes nothing.
for failing in toplevel '.#rock64 -o'; do
	: >"$log"
	if (cd "$TEST_REPO" && NIX_FAIL_MATCH=$failing ./scripts/build.sh); then
		echo "full build unexpectedly succeeded" >&2
		exit 1
	fi
	head -n 1 "$log" | grep -F 'args=eval .#lib.effectiveBuildConfiguration.policySHA256 --raw'
	for link in current previous toplevel current.new toplevel.new; do
		test ! -e "$TEST_REPO/.gcroots/rock64/$link"
		test ! -L "$TEST_REPO/.gcroots/rock64/$link"
	done
done

# A successful default ROCK64 build publishes its board folder.
: >"$log"
: >"$TEST_REPO/retained.log"
(cd "$TEST_REPO" && ./scripts/build.sh) >"$TEST_REPO/rock64.out"
grep -F 'args=build .#nixosConfigurations.rock64.config.system.build.toplevel -o .gcroots/rock64/toplevel.new' "$log"
grep -F 'args=build .#rock64 -o .gcroots/rock64/current.new' "$log"
test -f "$TEST_REPO/.gcroots/rock64/current/image/atomixos-rock64-26.05.img"
test -f "$TEST_REPO/.gcroots/rock64/current/rauc-bundle/rock64.raucb"
test -d "$TEST_REPO/.gcroots/rock64/toplevel"
test ! -L "$TEST_REPO/.gcroots/rock64/previous"
test ! -e "$TEST_REPO/.gcroots/rock64/current.new"
test ! -e "$TEST_REPO/.gcroots/rock64/toplevel.new"
# Final links are written by nix build itself, so Nix registers them as GC roots.
grep -Fx '.gcroots/rock64/current' "$TEST_REPO/retained.log"
grep -Fx '.gcroots/rock64/toplevel' "$TEST_REPO/retained.log"
grep -F "Image: .gcroots/rock64/current/image/atomixos-rock64-26.05.img" "$TEST_REPO/rock64.out"

# Invalid boards are rejected before any evaluation or retained-root mutation.
rock64_target=$(readlink "$TEST_REPO/.gcroots/rock64/current")
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
if (cd "$TEST_REPO" && usage_board=cm3 NIX_FAIL_MATCH='.#cm3 -o' ./scripts/build.sh); then
	echo "failed CM3 build unexpectedly succeeded" >&2
	exit 1
fi
test "$(readlink "$TEST_REPO/.gcroots/rock64/current")" = "$rock64_target"
test ! -L "$TEST_REPO/.gcroots/cm3/current"
test ! -e "$TEST_REPO/.gcroots/cm3/current.new"
test ! -e "$TEST_REPO/.gcroots/cm3/toplevel.new"

# CM3 builds its own board folder without touching ROCK64.
: >"$log"
(cd "$TEST_REPO" && usage_board=cm3 ./scripts/build.sh)
grep -F 'args=build .#nixosConfigurations.cm3.config.system.build.toplevel -o .gcroots/cm3/toplevel.new' "$log"
grep -F 'args=build .#cm3 -o .gcroots/cm3/current.new' "$log"
test -f "$TEST_REPO/.gcroots/cm3/current/image/atomixos-cm3-26.05.img"
test -f "$TEST_REPO/.gcroots/cm3/current/rauc-bundle/cm3.raucb"
test "$(readlink "$TEST_REPO/.gcroots/rock64/current")" = "$rock64_target"

# Rebuilding an unchanged CM3 keeps no duplicate previous; a new revision rotates only CM3.
cm3_target=$(readlink "$TEST_REPO/.gcroots/cm3/current")
(cd "$TEST_REPO" && usage_board=cm3 ./scripts/build.sh)
test ! -L "$TEST_REPO/.gcroots/cm3/previous"
test "$(readlink "$TEST_REPO/.gcroots/cm3/current")" = "$cm3_target"
: >"$TEST_REPO/retained.log"
(cd "$TEST_REPO" && usage_board=cm3 FAKE_GENERATION=next ./scripts/build.sh)
test "$(readlink "$TEST_REPO/.gcroots/cm3/previous")" = "$cm3_target"
test "$(readlink "$TEST_REPO/.gcroots/cm3/current")" != "$cm3_target"
grep -Fx '.gcroots/cm3/previous' "$TEST_REPO/retained.log"
test ! -e "$TEST_REPO/.gcroots/cm3/previous.new"
test "$(readlink "$TEST_REPO/.gcroots/rock64/current")" = "$rock64_target"

# An interrupted publish keeps the .new links, which are GC roots, so no build loses its root.
cm3_next_target=$(readlink "$TEST_REPO/.gcroots/cm3/current")
if (cd "$TEST_REPO" && usage_board=cm3 FAKE_GENERATION=third NIX_FAIL_MATCH='-o .gcroots/cm3/toplevel ' ./scripts/build.sh) \
	2>"$TEST_REPO/interrupted.err"; then
	echo "interrupted publish unexpectedly succeeded" >&2
	exit 1
fi
grep -F 'ERROR: publishing .gcroots/cm3 was interrupted' "$TEST_REPO/interrupted.err"
test "$(readlink "$TEST_REPO/.gcroots/cm3/previous.new")" = "$cm3_next_target"
test "$(readlink "$TEST_REPO/.gcroots/cm3/current")" = "$(readlink "$TEST_REPO/.gcroots/cm3/current.new")"
test -L "$TEST_REPO/.gcroots/cm3/toplevel.new"
test "$(readlink "$TEST_REPO/.gcroots/cm3/previous")" = "$cm3_target"
# The next build finishes the interrupted publish before building.
(cd "$TEST_REPO" && usage_board=cm3 FAKE_GENERATION=third ./scripts/build.sh)
test "$(readlink "$TEST_REPO/.gcroots/cm3/previous")" = "$cm3_next_target"
test "$(readlink "$TEST_REPO/.gcroots/cm3/current")" != "$cm3_next_target"
test ! -e "$TEST_REPO/.gcroots/cm3/previous.new"
test ! -e "$TEST_REPO/.gcroots/cm3/current.new"

# A dangling current link (its store path collected) is replaced without becoming previous.
rm "$TEST_REPO/.gcroots/rock64/current"
ln -s "$TEST_REPO/collected-store-path" "$TEST_REPO/.gcroots/rock64/current"
rm -f "$TEST_REPO/.gcroots/rock64/previous"
(cd "$TEST_REPO" && ./scripts/build.sh)
test "$(readlink "$TEST_REPO/.gcroots/rock64/current")" = "$rock64_target"
test ! -L "$TEST_REPO/.gcroots/rock64/previous"

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
grep -F 'args=build .#cm3 -o .gcroots/cm3/current.new --impure' "$log"
rm "$TEST_REPO/build.dev.toml"

# The supported task matrix routes only configuration-bearing project commands.
grep -F '[tasks.check]' "$TEST_REPO/mise.toml"
grep -F 'run = "hk check -a"' "$TEST_REPO/mise.toml"
if grep -F '[tasks."nix:check"]' "$TEST_REPO/mise.toml"; then
	echo "unexpected duplicate nix:check task in mise configuration" >&2
	exit 1
fi
# shellcheck disable=SC2016 # mise.toml holds the literal task variable.
grep -F './scripts/nix-with-build-config.sh build ".#$board.squashfs"' "$TEST_REPO/mise.toml"
# shellcheck disable=SC2016 # mise.toml holds the literal task variable.
grep -F './scripts/nix-with-build-config.sh build ".#$board.rauc-bundle"' "$TEST_REPO/mise.toml"
# shellcheck disable=SC2016 # mise.toml holds the literal task variable.
grep -F './scripts/nix-with-build-config.sh build ".#$board.boot-script"' "$TEST_REPO/mise.toml"
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
