#!/usr/bin/env bash
# shellcheck disable=SC2016 # Remote sh snippets expand their positional parameters.
# Build retained AtomixOS artifacts without discarding the previous good roots.
set -euo pipefail

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
NIX=./scripts/nix-with-build-config.sh

# Validate the effective configuration before creating or replacing any output link.
"${cmd[@]}" "$NIX" eval .#lib.effectiveBuildConfiguration.policySHA256 --raw >/dev/null

"${cmd[@]}" mkdir -p "$IMGROOT" "$BUNDLEROOT"

temporary_links=(
	"$GCROOTS/kernel.new"
	"$GCROOTS/toplevel.new"
	"$GCROOTS/uboot.new"
	"$GCROOTS/uboot-env-tools.new"
	"$IMGROOT/image.1.new"
	"$BUNDLEROOT/rauc-bundle.1.new"
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
"${cmd[@]}" "$NIX" build .#nixosConfigurations.rock64.config.system.build.kernel \
	-o "$GCROOTS/kernel.new"
"${cmd[@]}" "$NIX" build .#nixosConfigurations.rock64.config.system.build.toplevel \
	-o "$GCROOTS/toplevel.new"
"${cmd[@]}" "$NIX" build .#uboot -o "$GCROOTS/uboot.new"
"${cmd[@]}" "$NIX" build .#uboot-env-tools -o "$GCROOTS/uboot-env-tools.new"
"${cmd[@]}" "$NIX" build .#image -o "$IMGROOT/image.1.new"
"${cmd[@]}" "$NIX" build .#rauc-bundle -o "$BUNDLEROOT/rauc-bundle.1.new"

prev_image_target=
if [[ -L "$IMGROOT/image.1" ]]; then
	prev_image_target=$(readlink "$IMGROOT/image.1")
fi
new_image_target=$(readlink "$IMGROOT/image.1.new")

prev_bundle_target=
if [[ -L "$BUNDLEROOT/rauc-bundle.1" ]]; then
	prev_bundle_target=$(readlink "$BUNDLEROOT/rauc-bundle.1")
fi
new_bundle_target=$(readlink "$BUNDLEROOT/rauc-bundle.1.new")

# All builds succeeded. Rename prepared links over retained links as the commit point.
for root in kernel toplevel uboot uboot-env-tools; do
	atomic_replace "$GCROOTS/$root.new" "$GCROOTS/$root"
done

if [[ -n "$prev_image_target" && "$prev_image_target" != "$new_image_target" ]]; then
	atomic_replace "$IMGROOT/image.1" "$IMGROOT/image.2"
fi
atomic_replace "$IMGROOT/image.1.new" "$IMGROOT/image.1"

if [[ -n "$prev_bundle_target" && "$prev_bundle_target" != "$new_bundle_target" ]]; then
	atomic_replace "$BUNDLEROOT/rauc-bundle.1" "$BUNDLEROOT/rauc-bundle.2"
fi
atomic_replace "$BUNDLEROOT/rauc-bundle.1.new" "$BUNDLEROOT/rauc-bundle.1"

trap - EXIT

IMG=$("${cmd[@]}" sh -c 'set -- "$1"/*.img; [ -e "$1" ] && printf "%s\n" "$1"' _ "$IMGROOT/image.1")

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
