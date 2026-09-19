#!/usr/bin/env bash
# Build a RAUC bundle containing boot partition image and rootfs.
# Called from the Nix derivation — variables are substituted by Nix:
#   @bootPartition@ — path to the shared boot partition image
#   @squashfs@    — path to the squashfs image directory
#   @signingCert@ — path to signing certificate (empty = unsigned)
#   @signingKey@  — path to signing key (empty = unsigned)
#   @version@     — bundle version string
set -euo pipefail

mkdir -p bundle

# ── Reuse the shared boot partition image ──
cp "@bootPartition@/boot.vfat" bundle/boot.vfat

# ── Copy squashfs rootfs image ──
cp "@squashfs@/rootfs.squashfs" bundle/rootfs.squashfs

# ── Create RAUC manifest ──
cat >bundle/manifest.raucm <<EOF
[update]
compatible=rock64
version=@version@

[bundle]
format=verity

[image.boot]
filename=boot.vfat
type=raw

[image.rootfs]
filename=rootfs.squashfs
type=raw
EOF

# ── Sign and create the bundle ──
rauc bundle \
	--cert="@signingCert@" \
	--key="@signingKey@" \
	bundle/ \
	rock64.raucb
