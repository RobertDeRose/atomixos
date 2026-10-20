#!/usr/bin/env bash
# shellcheck disable=SC2016 # Remote sh snippets expand their positional parameters.
# Build retained AtomixOS artifacts without discarding the previous good roots.
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
# Never guess the board: a ROCK64 image on a CM3 (or the reverse) writes the wrong bootloader.
BOARD=${usage_board:-}
case "$BOARD" in
rock64 | cm3) ;;
"")
	echo "ERROR: choose a board with --board rock64|cm3" >&2
	exit 1
	;;
*)
	echo "ERROR: unsupported board '$BOARD' (expected rock64 or cm3)" >&2
	exit 1
	;;
esac

if [[ -n "${usage_output:-}" && -f "$REPO_ROOT/build.dev.toml" ]]; then
	output_name=${usage_output%/}
	output_name=${output_name##*/}
	case "$output_name" in
	*-dev | *-dev.*) ;;
	*)
		echo "ERROR: local override output filename must include -dev: $output_name" >&2
		exit 1
		;;
	esac
fi

cmd=()
using_lima=false
if [[ "${usage_lima:-false}" == true ]]; then
	mise run _lima "${usage_vm:-default}"
	cmd+=(limactl shell "${usage_vm:-default}" --)
	using_lima=true
fi

GCROOTS=.gcroots
# Each board keeps its retained roots in its own folder:
#   current   the board package (image/, rauc-bundle/, uboot/, ...) of the last build
#   previous  the last distinct earlier build
#   toplevel  the system closure, so rebuilds reuse the kernel and packages
BOARD_DIR="$GCROOTS/$BOARD"
CURRENT="$BOARD_DIR/current"
PREVIOUS="$BOARD_DIR/previous"
TOPLEVEL="$BOARD_DIR/toplevel"
NIX=./scripts/nix-with-build-config.sh

# Validate the effective configuration before creating or replacing any output link.
"${cmd[@]}" "$NIX" eval .#lib.effectiveBuildConfiguration.policySHA256 --raw >/dev/null

"${cmd[@]}" mkdir -p "$BOARD_DIR"

publishing=false
cleanup() {
	if [[ "$publishing" == true ]]; then
		# Every .new link is a GC root, so keeping them preserves both builds.
		echo "ERROR: publishing $BOARD_DIR was interrupted; its .new links still hold every build. Rerun the build." >&2
		return
	fi
	"${cmd[@]}" rm -f "$CURRENT.new" "$TOPLEVEL.new" "$PREVIOUS.new" || true
}
# Point a retained link at a store path through nix build, which replaces the
# link atomically and registers it as a GC root. A link renamed with mv would
# leave Nix tracking the old path, so the store path could be collected.
retain() {
	"${cmd[@]}" "$NIX" build "$2" -o "$1"
}
# Finish an interrupted publish first: previous.new holds the build that was
# current when it stopped.
if [[ -L "$PREVIOUS.new" ]] && "${cmd[@]}" test -e "$PREVIOUS.new"; then
	retain "$PREVIOUS" "$(readlink "$PREVIOUS.new")"
fi
trap cleanup EXIT
cleanup

# Build every replacement first. Existing retained links remain untouched on failure.
"${cmd[@]}" "$NIX" build ".#nixosConfigurations.$BOARD.config.system.build.toplevel" -o "$TOPLEVEL.new"
"${cmd[@]}" "$NIX" build ".#$BOARD" -o "$CURRENT.new"

# A current link whose store path is gone (for example after the checkout moved
# and its GC root went stale) has nothing left to keep as previous.
prev_target=
if [[ -L "$CURRENT" ]] && "${cmd[@]}" test -e "$CURRENT"; then
	prev_target=$(readlink "$CURRENT")
fi
new_target=$(readlink "$CURRENT.new")
toplevel_target=$(readlink "$TOPLEVEL.new")

# Root the outgoing build under previous.new before current changes, so an
# interrupted publish cannot leave it unrooted.
rotate=false
if [[ -n "$prev_target" && "$prev_target" != "$new_target" ]]; then
	retain "$PREVIOUS.new" "$prev_target"
	rotate=true
fi

# All builds succeeded. Publish the retained links as the commit point.
publishing=true
retain "$CURRENT" "$new_target"
retain "$TOPLEVEL" "$toplevel_target"
if [[ "$rotate" == true ]]; then
	retain "$PREVIOUS" "$prev_target"
fi
publishing=false

cleanup
trap - EXIT

IMG=$("${cmd[@]}" sh -c 'set -- "$1"/*.img; [ -e "$1" ] && printf "%s\n" "$1"' _ "$CURRENT/image")

if [[ -n "${usage_output:-}" ]]; then
	DEST=$usage_output
	if [[ "${DEST#/}" != "$DEST" ]]; then
		DEST_PATH=$DEST
	else
		DEST_PATH="$PWD/$DEST"
	fi
	if [[ "$using_lima" == true ]]; then
		"${cmd[@]}" sh -c 'cat "$1"' _ "$IMG" >"$DEST_PATH"
	else
		cp "$IMG" "$DEST_PATH"
	fi
	chmod u+w "$DEST_PATH"
	SIZE=$(stat -c%s "$DEST_PATH" 2>/dev/null || stat -f%z "$DEST_PATH")
	echo ""
	echo "Image: $DEST_PATH ($((SIZE / 1024 / 1024)) MiB)"
else
	if [[ "$using_lima" == true ]]; then
		SIZE=$("${cmd[@]}" sh -c 'stat -c%s "$1" 2>/dev/null || stat -f%z "$1"' _ "$IMG")
	else
		SIZE=$(stat -c%s "$IMG" 2>/dev/null || stat -f%z "$IMG")
	fi
	echo ""
	echo "Image: $IMG ($((SIZE / 1024 / 1024)) MiB)"
fi
