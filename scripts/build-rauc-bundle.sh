#!/usr/bin/env bash
# Build a RAUC bundle containing boot partition image and rootfs.
# Called from the Nix derivation — variables are substituted by Nix:
#   @kernel@      — path to kernel package (contains Image and dtbs/)
#   @dtbPath@     — relative DTB path (e.g. rockchip/rk3328-rock64.dtb)
#   @squashfs@    — path to the squashfs image directory
#   @signingCert@ — path to signing certificate (empty = unsigned)
#   @signingKey@  — path to signing key (empty = unsigned)
#   @version@     — bundle version string
set -euo pipefail

mkdir -p bundle

# ── Create boot partition image (vfat with kernel + DTB) ──
# 32 MiB vfat image
dd if=/dev/zero of=bundle/boot.vfat bs=1M count=32
mkfs.vfat -n "BOOT" bundle/boot.vfat

# Copy kernel and DTB into the vfat image
mmd -i bundle/boot.vfat ::dtbs
mmd -i bundle/boot.vfat ::dtbs/rockchip
mcopy -i bundle/boot.vfat "@kernel@/Image" ::Image
mcopy -i bundle/boot.vfat "@kernel@/dtbs/@dtbPath@" "::dtbs/rockchip/rk3328-rock64.dtb"

# ── Copy squashfs rootfs image ──
cp "@squashfs@/rootfs.squashfs" bundle/rootfs.squashfs

# ── Create RAUC manifest ──
cat >bundle/manifest.raucm <<EOF
[update]
compatible=rock64
version=@version@

[image.boot]
filename=boot.vfat
type=raw

[image.rootfs]
filename=rootfs.squashfs
type=raw
EOF

# ── Sign and create the bundle ──
# @signingKey@ is substituted by Nix at build time
# shellcheck disable=SC2157
if [ -n "@signingKey@" ]; then
	rauc bundle \
		--cert="@signingCert@" \
		--key="@signingKey@" \
		bundle/ \
		rock64.raucb
else
	echo "WARNING: No signing key provided. Creating unsigned bundle for development."
	echo "Pass signingKeyPath to create a signed production bundle."
	rauc bundle \
		--no-verify \
		bundle/ \
		rock64.raucb
fi
