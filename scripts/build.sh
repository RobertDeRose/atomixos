#!/usr/bin/env bash
# shellcheck disable=SC2016 # Remote sh snippets expand their positional parameters.
# Build retained AtomixOS artifacts without discarding the previous good roots.
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
BOARD=${usage_board:-rock64}
case "$BOARD" in
rock64)
	UBOOT_OUTPUT=uboot
	UBOOT_ENV_TOOLS_OUTPUT=uboot-env-tools
	;;
cm3)
	UBOOT_OUTPUT=uboot-cm3
	UBOOT_ENV_TOOLS_OUTPUT=uboot-env-tools-cm3
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
IMGROOT="$GCROOTS/images"
BUNDLEROOT="$GCROOTS/bundles"
IMAGE_ROOT="$IMGROOT/image-$BOARD"
BUNDLE_ROOT="$BUNDLEROOT/rauc-bundle-$BOARD"
NIX=./scripts/nix-with-build-config.sh

# Validate the effective configuration before creating or replacing any output link.
"${cmd[@]}" "$NIX" eval .#lib.effectiveBuildConfiguration.policySHA256 --raw >/dev/null

"${cmd[@]}" mkdir -p "$IMGROOT" "$BUNDLEROOT"

temporary_links=(
	"$GCROOTS/kernel-$BOARD.new"
	"$GCROOTS/toplevel-$BOARD.new"
	"$GCROOTS/uboot-$BOARD.new"
	"$GCROOTS/uboot-env-tools-$BOARD.new"
	"$IMAGE_ROOT.1.new"
	"$BUNDLE_ROOT.1.new"
)
cleanup() {
	"${cmd[@]}" rm -f "${temporary_links[@]}" || true
}
atomic_replace() {
	"${cmd[@]}" sh -c '
    if mv --help 2>&1 | grep -q -- "--no-target-directory"; then
      exec mv -Tf -- "$1" "$2"
    fi
    exec mv -fh "$1" "$2"
  ' _ "$1" "$2"
}
trap cleanup EXIT
cleanup

# Build every replacement first. Existing retained links remain untouched on failure.
"${cmd[@]}" "$NIX" build ".#nixosConfigurations.$BOARD.config.system.build.kernel" \
	-o "$GCROOTS/kernel-$BOARD.new"
"${cmd[@]}" "$NIX" build ".#nixosConfigurations.$BOARD.config.system.build.toplevel" \
	-o "$GCROOTS/toplevel-$BOARD.new"
"${cmd[@]}" "$NIX" build ".#$UBOOT_OUTPUT" -o "$GCROOTS/uboot-$BOARD.new"
"${cmd[@]}" "$NIX" build ".#$UBOOT_ENV_TOOLS_OUTPUT" -o "$GCROOTS/uboot-env-tools-$BOARD.new"
"${cmd[@]}" "$NIX" build ".#image-$BOARD" -o "$IMAGE_ROOT.1.new"
"${cmd[@]}" "$NIX" build ".#rauc-bundle-$BOARD" -o "$BUNDLE_ROOT.1.new"

# One-time migration of pre-board ROCK64 roots, only after every build succeeds.
# This also preserves the previous .1/.2 images across the naming transition.
if [[ "$BOARD" == rock64 ]]; then
	for root in kernel toplevel uboot uboot-env-tools; do
		if [[ -L "$GCROOTS/$root" && ! -e "$GCROOTS/$root-rock64" && ! -L "$GCROOTS/$root-rock64" ]]; then
			atomic_replace "$GCROOTS/$root" "$GCROOTS/$root-rock64"
		fi
	done
	for generation in 1 2; do
		if [[ -L "$IMGROOT/image.$generation" && ! -e "$IMAGE_ROOT.$generation" && ! -L "$IMAGE_ROOT.$generation" ]]; then
			atomic_replace "$IMGROOT/image.$generation" "$IMAGE_ROOT.$generation"
		fi
		if [[ -L "$BUNDLEROOT/rauc-bundle.$generation" && ! -e "$BUNDLE_ROOT.$generation" && ! -L "$BUNDLE_ROOT.$generation" ]]; then
			atomic_replace "$BUNDLEROOT/rauc-bundle.$generation" "$BUNDLE_ROOT.$generation"
		fi
	done
fi

prev_image_target=
if [[ -L "$IMAGE_ROOT.1" ]]; then
	prev_image_target=$(readlink "$IMAGE_ROOT.1")
fi
new_image_target=$(readlink "$IMAGE_ROOT.1.new")

prev_bundle_target=
if [[ -L "$BUNDLE_ROOT.1" ]]; then
	prev_bundle_target=$(readlink "$BUNDLE_ROOT.1")
fi
new_bundle_target=$(readlink "$BUNDLE_ROOT.1.new")

# All builds succeeded. Rename prepared links over retained links as the commit point.
for root in kernel toplevel uboot uboot-env-tools; do
	atomic_replace "$GCROOTS/$root-$BOARD.new" "$GCROOTS/$root-$BOARD"
done

if [[ -n "$prev_image_target" && "$prev_image_target" != "$new_image_target" ]]; then
	atomic_replace "$IMAGE_ROOT.1" "$IMAGE_ROOT.2"
fi
atomic_replace "$IMAGE_ROOT.1.new" "$IMAGE_ROOT.1"

if [[ -n "$prev_bundle_target" && "$prev_bundle_target" != "$new_bundle_target" ]]; then
	atomic_replace "$BUNDLE_ROOT.1" "$BUNDLE_ROOT.2"
fi
atomic_replace "$BUNDLE_ROOT.1.new" "$BUNDLE_ROOT.1"

trap - EXIT

IMG=$("${cmd[@]}" sh -c 'set -- "$1"/*.img; [ -e "$1" ] && printf "%s\n" "$1"' _ "$IMAGE_ROOT.1")

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
