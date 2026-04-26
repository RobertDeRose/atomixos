{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-mount-selection";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      boot.kernelParams = [ "rauc.slot=boot.0" ];
      environment.systemPackages = [ pkgs.util-linux ];
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          set -euo pipefail
          slot="''${1:-}"
          if [ -z "$slot" ]; then
            slot="boot.0"
          fi

          case "$slot" in
            boot.0)
              if ${pkgs.util-linux}/bin/findmnt /run/forensics/boot.0 >/dev/null 2>&1; then
                printf '%s\n' /run/forensics/boot.0
              else
                printf '%s\n' /boot
              fi
              ;;
            *)
              printf '%s\n' /boot
              ;;
          esac
        '';
      systemd.tmpfiles.rules = [
        "d /run/forensics 0755 root root -"
        "d /run/forensics/boot.0 0755 root root -"
        "d /boot 0755 root root -"
      ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("test -d /run/forensics/boot.0")
    machine.fail("findmnt /run/forensics/boot.0")
    machine.succeed("test \"$(/etc/atomixos/current-boot-forensics-mount boot.0)\" = /boot")
  '';
}
