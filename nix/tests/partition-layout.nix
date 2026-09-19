{ pkgs, self, ... }:

let
  layout = import ../partition-layout.nix;
  systemConfig = self.nixosConfigurations.rock64.config;
  repart = systemConfig.systemd.repart.partitions;
  bootSize = "${toString layout.boot.sizeMiB}M";
  rootfsSize = "${toString layout.rootfs.sizeMiB}M";
in
assert repart."10-boot-a".Label == layout.boot.labels.a;
assert repart."10-boot-a".SizeMinBytes == bootSize;
assert repart."30-boot-b".SizeMinBytes == bootSize;
assert repart."20-rootfs-a".Label == layout.rootfs.labels.a;
assert repart."20-rootfs-a".SizeMinBytes == rootfsSize;
assert repart."40-rootfs-b".SizeMinBytes == rootfsSize;
assert self.packages.aarch64-linux.squashfs.drvPath != "";
assert self.packages.aarch64-linux.boot-partition.drvPath != "";
pkgs.runCommandNoCC "partition-layout-contract" { } ''
  test "$(grep -c 'mkfs.vfat' ${../../nix/boot-partition.nix})" -eq 1
  ! grep -q 'mkfs.vfat\|mcopy\|mmd' ${../../scripts/build-image.sh}
  ! grep -q 'mkfs.vfat\|mcopy\|mmd' ${../../scripts/build-rauc-bundle.sh}
  grep -q '@bootPartition@/boot.vfat' ${../../scripts/build-image.sh}
  grep -q '@bootPartition@/boot.vfat' ${../../scripts/build-rauc-bundle.sh}
  touch "$out"
''
