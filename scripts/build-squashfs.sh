#!/usr/bin/env bash
# Build a squashfs image from the NixOS system closure.
# Called from the Nix derivation — variables are substituted by Nix:
#   @systemClosure@ — path to NixOS system.build.toplevel
#   @closureInfo@   — path to closureInfo output (contains store-paths file)
#   @maxSize@       — maximum allowed image size in bytes
#   @out@           — Nix output path (set by Nix build environment)
# shellcheck disable=SC2154  # Variables are injected by Nix substitute
set -euo pipefail

mkdir -p "$out"

# Build a pseudo-filesystem root:
# /nix/store/... — all closure paths
# /sbin/init     — symlink to the NixOS system activation
PSEUDO_ROOT=$(mktemp -d)

# Copy all closure paths into the pseudo-root's /nix/store.
# Use cp -a to preserve all attributes (including +x on binaries).
# Cleanup of the read-only copies is handled by rm -rf as root in the sandbox.
mkdir -p "$PSEUDO_ROOT/nix/store"
while IFS= read -r path; do
	cp -a "$path" "$PSEUDO_ROOT/nix/store/"
done <"@closureInfo@/store-paths"

# Create /sbin/init pointing to the system toplevel
mkdir -p "$PSEUDO_ROOT/sbin"
ln -s "@systemClosure@/init" "$PSEUDO_ROOT/sbin/init"

# Build the squashfs image using zstd compression (best ratio on ARM)
mksquashfs "$PSEUDO_ROOT" "$out/rootfs.squashfs" \
	-comp zstd \
	-Xcompression-level 19 \
	-b 1048576 \
	-no-xattrs \
	-all-root \
	-progress

# Restore write permissions before cleanup — cp -a preserves read-only nix store perms
chmod -R u+w "$PSEUDO_ROOT"
rm -rf "$PSEUDO_ROOT"

# Size check — fail if image exceeds slot size
IMAGE_SIZE=$(stat -c%s "$out/rootfs.squashfs")
MAX_SIZE=@maxSize@

echo "Squashfs image size: $IMAGE_SIZE bytes ($((IMAGE_SIZE / 1024 / 1024)) MB)"
echo "Maximum allowed: $MAX_SIZE bytes ($((MAX_SIZE / 1024 / 1024)) MB)"

if [ "$IMAGE_SIZE" -gt "$MAX_SIZE" ]; then
	echo "ERROR: Squashfs image ($IMAGE_SIZE bytes) exceeds maximum slot size ($MAX_SIZE bytes)"
	echo "Reduce the system closure size or increase the partition layout."
	exit 1
fi

echo "Size check passed."
