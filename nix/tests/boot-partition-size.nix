# boot-partition.nix fails with a size breakdown, not mtools' "Disk full", when
# the kernel, initrd, DTB, and boot.scr outgrow the boot slot.
{
  pkgs,
  ...
}:
let
  stub =
    name: script:
    pkgs.runCommand name { } ''
      mkdir -p $out
      ${script}
    '';
  nixosConfig = {
    atomixos.board = "test";
    boot.kernelPackages.kernel = stub "stub-kernel" "truncate -s 3M $out/Image";
    system.build.initialRamdisk = stub "stub-initrd" "truncate -s 2M $out/initrd";
    hardware.deviceTree = {
      name = "rockchip/test.dtb";
      package = stub "stub-dtbs" "mkdir -p $out/rockchip && echo dtb >$out/rockchip/test.dtb";
    };
  };
  bootPartition =
    sizeMiB:
    pkgs.callPackage ../boot-partition.nix {
      inherit nixosConfig;
      bootScript = stub "stub-boot-script" "echo scr >$out/boot.scr";
      partitionLayout.boot.sizeMiB = sizeMiB;
    };
  # 5 MiB of payload plus the 4 MiB FAT reserve does not fit in 8 MiB.
  overflow = pkgs.testers.testBuildFailure (bootPartition 8);
  fits = bootPartition 16;
in
pkgs.runCommand "boot-partition-size-check" { } ''
  grep -F 'boot partition overflow: payload 5 MiB + 4 MiB FAT reserve exceeds the 8 MiB boot slot' ${overflow}/testBuildFailure.log
  grep -F 'grow boot.sizeMiB in nix/partition-layout.nix' ${overflow}/testBuildFailure.log
  test -s ${fits}/boot.vfat
  touch $out
''
