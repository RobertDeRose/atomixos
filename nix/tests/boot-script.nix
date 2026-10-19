# Keep the rootfs partition derived from the selected boot slot, and check the
# compiled script carries the NixOS kernel parameters.
{
  pkgs,
  ...
}:
let
  bootScript = pkgs.callPackage ../boot-script.nix {
    nixosConfig = {
      atomixos.board = "test";
      boot.kernelParams = [
        "root=fstab"
        "lsm=bpf"
        "net.ifnames=0"
      ];
    };
    systemClosure = "/nix/store/00000000000000000000000000000000-system";
    dtbPath = "rockchip/test.dtb";
    rootfsPathA = "/dev/mmcblk0p2";
    rootfsPathB = "/dev/mmcblk0p4";
    bootargsBase = "console=ttyS2,1500000 loglevel=7";
    recoveryButtonPin = "";
    ramdiskAddr = "";
  };
in
pkgs.runCommand "test-boot-script" { } ''
  script=${../../scripts/boot.cmd}

  grep -F 'if test "''${distro_bootpart}" = "1"; then' "$script"
  grep -F 'setenv distro_rootpart 2' "$script"
  grep -F 'elif test "''${distro_bootpart}" = "3"; then' "$script"
  grep -F 'setenv distro_rootpart 4' "$script"
  ! grep -F 'if test -z "''${distro_rootpart}"' "$script"

  # NixOS parameters precede the board base (so its console and loglevel win);
  # boot.cmd supplies root= itself, and every placeholder is substituted.
  compiled=${bootScript}/boot.cmd
  grep -F 'setenv bootargs "lsm=bpf net.ifnames=0 ''${bootargs_base} root=fstab rw' "$compiled"
  test "$(grep -o 'root=fstab' "$compiled" | wc -l)" -eq 1
  ! grep -E '@[A-Za-z]+@' "$compiled"
  test -s ${bootScript}/boot.scr

  touch "$out"
''
