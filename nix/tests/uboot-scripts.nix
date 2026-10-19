# Run the compiled boot.scr and the shared START_UMS PREBOOT in a U-Boot sandbox
# build. U-Boot only parses scripts at boot time, so a syntax error here would
# otherwise first show up as a board that no longer boots.
{
  pkgs,
  self,
  ...
}:
let
  inherit (pkgs) lib;
  sandbox = pkgs.callPackage ../uboot-sandbox.nix {
    uboot = self.packages.${pkgs.stdenv.hostPlatform.system}.cm3.uboot;
  };
  bootScript = pkgs.callPackage ../boot-script.nix {
    nixosConfig = {
      atomixos.board = "test";
      boot.kernelParams = [
        "root=fstab"
        "lsm=bpf"
      ];
    };
    systemClosure = "/nix/store/00000000000000000000000000000000-system";
    dtbPath = "rockchip/test.dtb";
    rootfsPathA = "/dev/mmcblk0p2";
    rootfsPathB = "/dev/mmcblk0p4";
    bootargsBase = "console=ttyS2,1500000";
    recoveryButtonPin = "";
    ramdiskAddr = "";
  };
  preboot = builtins.head (
    builtins.match ''.*CONFIG_PREBOOT="([^"]*)".*'' (
      lib.replaceStrings [ "\n" ] [ " " ] (import ../uboot-start-ums.nix)
    )
  );
in
pkgs.runCommand "uboot-scripts-check" { } ''
  # The sandbox relaunches itself on `reset`; stop reading at the first one.
  run() {
    { timeout 60 ${sandbox}/u-boot -c "$1" 2>&1 || true; } | sed '/resetting \.\.\./q' >"$2"
    cat "$2"
  }

  # boot.cmd parses, and a failed fatload (the sandbox has no boot partition)
  # resets, naming the first file, instead of reaching booti.
  cp ${bootScript}/boot.scr boot.scr
  run "host load hostfs - 0x1000000 $PWD/boot.scr; source 0x1000000; echo SCRIPT-RETURNED" boot.out
  grep -F 'ERROR: cannot load Image from mmc 0:1; resetting' boot.out
  ! grep -F 'booti failed' boot.out
  ! grep -F 'SCRIPT-RETURNED' boot.out

  # The sandbox can't reach booti, so check the source: a failed booti resets
  # for U-Boot builds whose boot command doesn't.
  sed -n '/^booti /,$p' ${../../scripts/boot.cmd} | grep -qx 'reset'

  # boot.cmd still honours START_UMS for U-Boot builds without the PREBOOT.
  run "setenv START_UMS 1; host load hostfs - 0x1000000 $PWD/boot.scr; source 0x1000000" boot-ums.out
  grep -F 'START_UMS=1 requested, entering USB mass storage mode' boot-ums.out
  grep -F 'USB mass storage exited, resetting...' boot-ums.out
  ! grep -F 'cannot load' boot-ums.out

  # PREBOOT is inert without START_UMS and takes the UMS path with it.
  run 'setenv START_UMS; ${preboot}; echo PREBOOT-PASSED' unset.out
  grep -F 'PREBOOT-PASSED' unset.out
  ! grep -F 'START_UMS=1 requested' unset.out
  run 'setenv START_UMS 1; ${preboot}; echo AFTER-RESET' set.out
  grep -F 'START_UMS=1 requested, entering USB mass storage mode' set.out
  grep -F 'Write a new image over the OTG USB cable' set.out
  grep -F 'resetting ...' set.out
  ! grep -F 'AFTER-RESET' set.out

  mkdir -p $out
  cp *.out $out/
''
