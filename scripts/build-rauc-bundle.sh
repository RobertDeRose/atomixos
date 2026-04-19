#!/usr/bin/env bash
# Build a RAUC bundle containing boot partition image and rootfs.
# Called from the Nix derivation — variables are substituted by Nix:
#   @kernel@      — path to kernel package (contains Image and dtbs/)
#   @initrd@      — path to initrd package (contains initrd)
#   @dtbPath@     — relative DTB path (e.g. rockchip/rk3328-rock64.dtb)
#   @squashfs@    — path to the squashfs image directory
#   @bootScript@  — path to boot-script directory (contains boot.scr)
#   @signingCert@ — path to signing certificate (empty = unsigned)
#   @signingKey@  — path to signing key (empty = unsigned)
#   @version@     — bundle version string
set -euo pipefail

mkdir -p bundle

# ── Create boot partition image (vfat with kernel + initrd + DTB + boot.scr) ──
# 128 MiB vfat image (aarch64 kernel Image is ~63 MB uncompressed)
dd if=/dev/zero of=bundle/boot.vfat bs=1M count=128
mkfs.vfat -n "BOOT" bundle/boot.vfat

# Copy boot artifacts into the vfat image
mmd -i bundle/boot.vfat ::dtbs
mmd -i bundle/boot.vfat ::dtbs/rockchip
mcopy -i bundle/boot.vfat "@kernel@/Image" ::Image
mcopy -i bundle/boot.vfat "@initrd@/initrd" ::initrd
mcopy -i bundle/boot.vfat "@kernel@/dtbs/@dtbPath@" "::dtbs/rockchip/rk3328-rock64.dtb"
mcopy -i bundle/boot.vfat "@bootScript@/boot.scr" ::boot.scr

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
